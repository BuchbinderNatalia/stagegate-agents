#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Success-rate evaluation: run the stagegate agents on small, well-defined tasks.

Each run works in a fresh copy of examples/sample-app with stagegate installed and
no git remote, and makes three separate Claude Code sessions:
  1. backend-builder  implements the task's brief          (--agent backend-builder)
  2. implementation-validator checks it against the ACs   (--agent implementation-validator)
  3. pr-reviewer      reviews the branch diff              (--agent pr-reviewer)
A run PASSES only if all of these hold:
  discipline  work on a feature branch, >= 1 commit, clean tree, default branch untouched
  suite       the app's whole test suite passes (no regressions)
  hidden      the task's hidden acceptance tests pass (the agents never see them)
  validator   0 Critical findings
  reviewer    0 Critical findings

Modes:
  --stub   replays each task's reference solution with the fake claude: free, offline,
           tests the harness itself (CI runs this)
  live     the real `claude`, with your logged-in Claude Code. Local only: refuses to
           run in CI, asks for confirmation unless --yes, forces the sandbox on
           (sandbox.fail_if_unavailable) so a run can't touch anything outside its copy.

Usage:
  evals/run.py --stub
  evals/run.py --task csv-export --runs 1          # one live run first: check time and cost
  evals/run.py --runs 3 --yes                      # all tasks, pass@1 over 3 runs each
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import tomllib
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_APP = ROOT / "examples" / "sample-app"
FAKE_CLAUDE = ROOT / "tests" / "fixtures" / "fake-bin" / "claude"
TEST_COMMAND = "python -m pytest -q -p no:cacheprovider"
CRITICAL = re.compile(r"\*\*\[CRITICAL\]\*\*")
VERDICT = re.compile(r"Verdict:\s*\**\s*(APPROVE|REQUEST CHANGES|NEEDS DISCUSSION)", re.I)

STUB_VALIDATOR = """### Critical — must fix before merge
_None._
### Important — should fix before merge
_None._
### Acceptance criteria coverage
(all criteria implemented and tested)
### Recommended next agent
**None — ready for pr-reviewer**"""
STUB_REVIEWER = """### Critical — must fix before merge
_None._
### Summary
- Verdict: **APPROVE**"""


@dataclass
class Task:
    id: str
    title: str
    brief: str
    acceptance: list[str]
    max_turns: int
    path: Path


@dataclass
class RunResult:
    task: str
    run: int
    passed: bool = False
    checks: dict[str, Any] = field(default_factory=dict)
    turns: int = 0
    cost_usd: float = 0.0
    seconds: float = 0.0
    error: str = ""
    workspace: str = ""


def load_tasks(tasks_dir: Path, only: str | None) -> list[Task]:
    tasks = []
    for d in sorted(p for p in tasks_dir.iterdir() if (p / "task.toml").exists()):
        if only and d.name != only:
            continue
        spec = tomllib.loads((d / "task.toml").read_text())
        tasks.append(
            Task(
                d.name,
                spec["title"],
                spec["brief"].strip(),
                spec["acceptance"],
                int(spec.get("max_turns", 40)),
                d,
            )
        )
    if not tasks:
        raise SystemExit(f"no task found{f' named {only!r}' if only else ''} in {tasks_dir}")
    return tasks


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def base_env() -> dict[str, str]:
    venv_bin = str(Path(sys.executable).parent)
    return dict(
        os.environ,
        PATH=os.pathsep.join([venv_bin, os.environ.get("PATH", "")]),
        STAGEGATE_PYTHON=sys.executable,
        GIT_AUTHOR_NAME="stagegate-eval",
        GIT_AUTHOR_EMAIL="eval@example.com",
        GIT_COMMITTER_NAME="stagegate-eval",
        GIT_COMMITTER_EMAIL="eval@example.com",
        PYTHONDONTWRITEBYTECODE="1",
    )


def make_workspace(work: Path, live: bool) -> tuple[Path, str]:
    """Fresh sample-app repo with stagegate installed and committed on main; no remote."""
    repo = work / "bookshelf"
    shutil.copytree(SAMPLE_APP, repo, ignore=shutil.ignore_patterns("__pycache__"))
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "stagegate-eval")
    git(repo, "config", "user.email", "eval@example.com")
    config = f'[stack]\ntest_command = "{TEST_COMMAND}"\n'
    if live:
        config += "\n[sandbox]\nfail_if_unavailable = true\n"
    (repo / "stagegate.toml").write_text(config)
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "install.py"), str(repo)],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"install failed: {out.stderr}")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init with stagegate")
    return repo, git(repo, "rev-parse", "main")


# --------------------------------------------------------------------------- claude calls
def stub_transcript(task: Task, role: str) -> dict[str, Any]:
    if role == "validator":
        return {"steps": [{"tool": "Read"}], "result": STUB_VALIDATOR}
    if role == "reviewer":
        return {
            "steps": [{"tool": "Bash", "command": "git diff --stat main...HEAD"}],
            "result": STUB_REVIEWER,
        }
    steps: list[dict[str, Any]] = [{"tool": "Bash", "command": f"git switch -q -c feat/{task.id}"}]
    for f in sorted(p for p in (task.path / "solution").rglob("*") if p.is_file()):
        rel = f.relative_to(task.path / "solution").as_posix()
        steps.append({"tool": "Write", "path": rel, "content": f.read_text()})
    steps += [
        {"tool": "Bash", "command": TEST_COMMAND},
        {"tool": "Bash", "command": f"git add -A && git commit -q -m 'feat: {task.title}'"},
    ]
    return {"steps": steps, "result": "implemented"}


def call_claude(
    repo: Path,
    work: Path,
    prompt: str,
    agent: str,
    task: Task,
    role: str,
    live: bool,
    extra: list[str],
) -> dict[str, Any]:
    env = base_env()
    if live:
        exe = shutil.which("claude", path=env["PATH"])
    else:
        exe = str(FAKE_CLAUDE)
        transcript = work / f"{role}.transcript.json"
        transcript.write_text(json.dumps(stub_transcript(task, role)))
        env["FAKE_CLAUDE_TRANSCRIPT"] = str(transcript)
    argv = [
        exe,
        "-p",
        prompt,
        "--agent",
        agent,
        "--output-format",
        "json",
        "--max-turns",
        str(task.max_turns),
        *extra,
    ]
    started = time.monotonic()
    p = subprocess.run(argv, cwd=repo, env=env, capture_output=True, text=True, timeout=3600)
    (work / f"{role}.out.json").write_text(p.stdout)
    (work / f"{role}.err.txt").write_text(p.stderr)
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError:
        data = {"is_error": True, "result": (p.stdout + p.stderr)[-2000:]}
    data["_seconds"] = time.monotonic() - started
    data["_returncode"] = p.returncode
    return data


# --------------------------------------------------------------------------- grading
def run_pytest(repo: Path, *paths: str) -> bool:
    p = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", *paths],
        cwd=repo,
        env=base_env(),
        capture_output=True,
        text=True,
        timeout=600,
    )
    return p.returncode == 0


def grade_repo(repo: Path, main_sha: str, task: Task) -> dict[str, Any]:
    branch = git(repo, "branch", "--show-current")
    commits = int(git(repo, "rev-list", "--count", f"{main_sha}..HEAD") or 0)
    dirty = git(repo, "status", "--porcelain")
    main_untouched = git(repo, "rev-parse", "main") == main_sha
    checks: dict[str, Any] = {
        "branch": branch,
        "discipline": branch not in ("main", "") and commits >= 1 and not dirty and main_untouched,
        "suite": run_pytest(repo),
    }
    hidden = repo / "tests" / f"test_hidden_{task.id.replace('-', '_')}.py"
    shutil.copy(task.path / "hidden_test.py", hidden)
    checks["hidden"] = run_pytest(repo, str(hidden.relative_to(repo)))
    hidden.unlink()
    return checks


def run_one(task: Task, n: int, out: Path, live: bool) -> RunResult:
    result = RunResult(task.id, n)
    work = out / "work" / f"{task.id}-{n}"
    work.mkdir(parents=True)
    started = time.monotonic()
    try:
        repo, main_sha = make_workspace(work, live)
        result.workspace = str(repo)
        builder = call_claude(
            repo,
            work,
            "Implement this approved technical brief for the bookshelf project.\n\n"
            f"{task.brief}\n\nFollow your instructions: branch rule, tests, commits. Use the "
            f"branch feat/{task.id}. This repository has no remote: do not push and do not "
            "open a pull request. End with a short summary.",
            "backend-builder",
            task,
            "builder",
            live,
            [
                "--permission-mode",
                "acceptEdits",
                "--allowedTools",
                "Bash(python -m pytest*)",
                "Bash(git *)",
                "Bash(ruff *)",
            ],
        )
        changed = git(repo, "diff", "--name-only", f"{main_sha}...HEAD")
        acs = "\n".join(task.acceptance)
        validator = call_claude(
            repo,
            work,
            f"Validate the implementation against this approved story.\n\nAcceptance criteria:\n"
            f"{acs}\n\nTechnical brief:\n{task.brief}\n\nFiles changed on this branch:\n"
            f"{changed or '(none)'}\n\nReport in your standard format.",
            "implementation-validator",
            task,
            "validator",
            live,
            [],
        )
        reviewer = call_claude(
            repo,
            work,
            f"Review this branch against `{main_sha[:12]}` (the default branch). "
            "Report in your standard format, including the Verdict line.",
            "pr-reviewer",
            task,
            "reviewer",
            live,
            [
                "--allowedTools",
                "Bash(git diff*)",
                "Bash(git log*)",
                "Bash(git show*)",
                "Bash(git status*)",
            ],
        )
        calls = (builder, validator, reviewer)
        result.turns = sum(int(c.get("num_turns") or 0) for c in calls)
        result.cost_usd = round(sum(float(c.get("total_cost_usd") or 0) for c in calls), 4)
        checks = grade_repo(repo, main_sha, task)
        v_text, r_text = str(validator.get("result", "")), str(reviewer.get("result", ""))
        checks["validator_critical"] = (
            len(CRITICAL.findall(v_text)) if not validator.get("is_error") else None
        )
        checks["reviewer_critical"] = (
            len(CRITICAL.findall(r_text)) if not reviewer.get("is_error") else None
        )
        verdict = VERDICT.search(r_text)
        checks["reviewer_verdict"] = verdict.group(1).upper() if verdict else None
        checks["builder_error"] = bool(builder.get("is_error"))
        result.checks = checks
        result.passed = bool(
            checks["discipline"]
            and checks["suite"]
            and checks["hidden"]
            and checks["validator_critical"] == 0
            and checks["reviewer_critical"] == 0
        )
    except Exception as exc:  # noqa: BLE001 - one broken run must not stop the eval
        result.error = f"{type(exc).__name__}: {exc}"
    result.seconds = round(time.monotonic() - started, 1)
    return result


# --------------------------------------------------------------------------- reporting
def summarise(results: list[RunResult], meta: dict[str, Any]) -> str:
    by_task: dict[str, list[RunResult]] = {}
    for r in results:
        by_task.setdefault(r.task, []).append(r)
    total = len(results)
    passed = sum(r.passed for r in results)
    lines = [
        f"# stagegate eval: {meta['mode']} mode, {meta['date']}",
        "",
        f"**pass@1: {passed}/{total} runs ({100 * passed / total:.0f}%)** · "
        f"API-equivalent cost ${sum(r.cost_usd for r in results):.2f} · "
        f"{sum(r.turns for r in results)} turns · claude {meta['claude_version']}",
        "",
        "| Task | Passed | Discipline | Suite | Hidden tests | Validator crit. | Reviewer crit. "
        "| Avg time | Avg cost |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for task, runs in by_task.items():

        def frac(key: str, runs: list[RunResult] = runs) -> str:
            ok = sum(1 for r in runs if r.checks.get(key) is True)
            return f"{ok}/{len(runs)}"

        def zero(key: str, runs: list[RunResult] = runs) -> str:
            ok = sum(1 for r in runs if r.checks.get(key) == 0)
            return f"{ok}/{len(runs)} at 0"

        lines.append(
            f"| {task} | {sum(r.passed for r in runs)}/{len(runs)} | {frac('discipline')} | "
            f"{frac('suite')} | {frac('hidden')} | {zero('validator_critical')} | "
            f"{zero('reviewer_critical')} | {sum(r.seconds for r in runs) / len(runs):.0f}s | "
            f"${sum(r.cost_usd for r in runs) / len(runs):.2f} |"
        )
    errors = [r for r in results if r.error]
    if errors:
        lines += ["", "Errors:"] + [f"- {r.task} #{r.run}: {r.error}" for r in errors]
    lines += [
        "",
        "Cost is the API-equivalent `total_cost_usd` Claude Code reports; on a "
        "subscription it counts against plan usage rather than being billed.",
    ]
    return "\n".join(lines) + "\n"


def claude_version(live: bool) -> str:
    exe = shutil.which("claude") if live else str(FAKE_CLAUDE)
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
        return out.stdout.strip().splitlines()[0]
    except (OSError, IndexError, subprocess.SubprocessError, TypeError):
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--stub", action="store_true", help="fake claude + reference solutions")
    ap.add_argument("--task", help="run only this task id")
    ap.add_argument("--runs", type=int, default=1, help="runs per task (default 1)")
    ap.add_argument("--yes", action="store_true", help="don't ask before live runs")
    ap.add_argument("--tasks-dir", type=Path, default=ROOT / "evals" / "tasks")
    ap.add_argument("--out", type=Path, default=ROOT / "evals" / "runs")
    args = ap.parse_args(argv)
    live = not args.stub
    tasks = load_tasks(args.tasks_dir, args.task)
    total = len(tasks) * args.runs

    if live:
        if os.environ.get("CI"):
            print("Live evals never run in CI (they use a personal Claude login).", file=sys.stderr)
            return 2
        if not shutil.which("claude"):
            print("Claude Code (`claude`) not found on PATH.", file=sys.stderr)
            return 2
        print(
            f"About to run {total} live run(s) ({len(tasks)} task(s) x {args.runs}), "
            "3 Claude Code sessions each, with your Claude login and the sandbox forced on."
        )
        if not args.yes:
            if input("Continue? [y/N] ").strip().lower() != "y":
                print("Cancelled.")
                return 1

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = args.out / f"{stamp}-{'stub' if args.stub else 'live'}"
    out.mkdir(parents=True)
    meta = {
        "mode": "stub" if args.stub else "live",
        "date": stamp,
        "claude_version": claude_version(live),
        "python": platform.python_version(),
        "runs_per_task": args.runs,
        "tasks": [t.id for t in tasks],
    }
    results: list[RunResult] = []
    for task in tasks:
        for n in range(1, args.runs + 1):
            r = run_one(task, n, out, live)
            results.append(r)
            status = "PASS" if r.passed else "FAIL"
            print(
                f"  {status}  {task.id} #{n}  {r.seconds:.0f}s  ${r.cost_usd:.2f}  "
                f"{json.dumps({k: v for k, v in r.checks.items() if k != 'branch'})}"
                f"{'  ' + r.error if r.error else ''}"
            )

    (out / "results.json").write_text(
        json.dumps({"meta": meta, "results": [asdict(r) for r in results]}, indent=2) + "\n"
    )
    summary = summarise(results, meta)
    (out / "summary.md").write_text(summary)
    print("\n" + summary + f"\nResults: {out}")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
