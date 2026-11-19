# SPDX-License-Identifier: Apache-2.0
"""Merge gate: block `gh pr merge` unless every CI check on the PR is green.

Checks in the "pass" or "skipping" bucket count as green; failing, pending or
cancelled checks, or no checks at all, block. `--auto` is blocked too: without
required status checks on the branch, GitHub merges an --auto PR immediately.

Scope: a guardrail against an agent merging a red PR by accident, not a
security boundary. It cannot see merges through the web UI, the REST API,
`git push` to the default branch, or a script that calls gh internally.
Pair it with branch protection where your GitHub plan allows it.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import hookio  # noqa: E402
import shellwords  # noqa: E402

GUARD = "merge gate"
GREEN = {"pass", "skipping"}
# `gh pr merge` options that take a value (so the value is not the PR number).
VALUE_FLAGS = {
    "-b",
    "--body",
    "-F",
    "--body-file",
    "-t",
    "--subject",
    "-A",
    "--author-email",
    "--match-head-commit",
    "-R",
    "--repo",
}


def find_merge(command: str) -> tuple[str, str] | None:
    """Return (target, repo) for the first real `gh pr merge`, else None."""
    for argv in shellwords.commands(command):
        if shellwords.program(argv) != "gh" or argv[1:3] != ["pr", "merge"]:
            continue
        target, repo, i, rest = "", "", 0, argv[3:]
        while i < len(rest):
            arg = rest[i]
            if arg in VALUE_FLAGS:
                if arg in {"-R", "--repo"} and i + 1 < len(rest):
                    repo = rest[i + 1]
                i += 2
                continue
            if arg.startswith("--repo="):
                repo = arg.split("=", 1)[1]
            elif not arg.startswith("-") and not target:
                target = arg
            i += 1
        return target, repo
    return None


def failing_checks(target: str, repo: str, cwd: str | None) -> tuple[list[str], str]:
    """Return (problems, raw gh output). Empty problems = all green."""
    cmd = ["gh", "pr", "checks"]
    if target:
        cmd.append(target)
    if repo:
        cmd += ["--repo", repo]
    cmd += ["--json", "name,bucket"]
    try:
        # gh exits non-zero while checks fail or are pending: judge the JSON, not the code.
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=45)
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"could not run gh: {exc}"], ""
    raw = (proc.stdout or proc.stderr).strip()
    try:
        checks = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return ["could not read the PR's checks"], raw
    if not checks:
        return ["no CI checks reported on this PR (push a commit or re-run CI first)"], raw
    return [
        f"{c.get('name')}: {c.get('bucket')}" for c in checks if c.get("bucket") not in GREEN
    ], raw


def main() -> None:
    command, cwd = hookio.read_payload()
    hit = find_merge(command)
    if hit is None:
        hookio.allow()
    try:
        cfg = config.load(config.project_root(cwd))
    except config.ConfigError as exc:
        hookio.block(GUARD, [str(exc), "Fix stagegate.toml before merging."])
    if not cfg["review"]["require_green_ci"]:
        hookio.allow()

    target, repo = hit
    problems, raw = failing_checks(target, repo, cwd)
    if problems:
        lines = [f"PR {target or 'for the current branch'} is not green.", *problems]
        if problems[0].startswith("could not") and raw:
            lines.append(f"gh output: {raw[:500]}")
        lines.append("Wait for or fix the checks, then merge.")
        hookio.block(GUARD, lines)
    hookio.allow()


if __name__ == "__main__":
    main()
