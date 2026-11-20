# SPDX-License-Identifier: Apache-2.0
"""Commit guard: block unsafe `git commit` and `git push`.

Runs only when the command actually runs `git commit` or `git push` (not on every
Bash call). With git.protect_default_branch (default on) it blocks commits on the
default branch and pushes that would update it: work goes through a branch + PR.
Inspects what the commit would contain: staged changes, plus tracked unstaged
changes when -a/--all is used. Blocks on:
  - files matching guards.blocked_files (secrets, state, keys), unless they
    match guards.allowed_files (e.g. .env.example);
  - `image: ...:latest` in added lines (guards.block_latest_tag);
  - added lines matching any guards.forbidden_patterns regex.

Files a `git add` earlier in the same command will stage are included too (the hook
runs before the command, so they aren't in the index yet).

Limits: `git commit <pathspec>` commits working-tree content of those paths,
which is not inspected; commits made outside Claude Code are not seen. Use the
repo's pre-commit/gitleaks hooks as the second layer.
"""

from __future__ import annotations

import fnmatch
import importlib
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Sibling modules, loaded after the path is set (no import-order suppressions needed,
# so the installed code passes users' own linters).
config = importlib.import_module("config")
hookio = importlib.import_module("hookio")
shellwords = importlib.import_module("shellwords")

GUARD = "commit guard"
LATEST = re.compile(r"image:\s*[\"']?\S+:latest\b", re.IGNORECASE)
# git global options that take a separate value: git -C <path> commit, git -c k=v commit
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}


GitCall = tuple[str, Path, list[str]]  # (subcommand, repo dir, args after the subcommand)
# `git push` options that take a separate value.
PUSH_VALUE_OPTS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}


def git_calls(command: str, cwd: str | None) -> list[GitCall]:
    """Every real `git add` / `commit` / `push` in the command, with the repo it runs in."""
    base = Path(cwd) if cwd else Path.cwd()
    calls: list[GitCall] = []
    for argv in shellwords.commands(command):
        if shellwords.program(argv) != "git":
            continue
        where, i = base, 1
        while i < len(argv) and argv[i].startswith("-"):
            if argv[i] in GIT_VALUE_OPTS and i + 1 < len(argv):
                if argv[i] == "-C":
                    where = where / argv[i + 1]
                i += 2
            else:
                i += 1
        if i < len(argv) and argv[i] in ("add", "commit", "push"):
            calls.append((argv[i], where, argv[i + 1 :]))
    return calls


def pending_adds(repo: Path, args: list[str]) -> list[str]:
    """Paths a `git add` earlier in the same command will stage (the hook runs before it).

    `git add -A` / `.` / `--all` / `-u` add modified files (and, except -u, untracked
    ones that aren't ignored); explicit paths are taken as given, also when forced (-f).
    """
    opts = {a for a in args if a.startswith("-")}
    paths = [a for a in args if not a.startswith("-")]
    out: list[str] = []
    if opts & {"-A", "--all", "-u", "--update"} or "." in paths:
        out += _git(repo, "diff", "--name-only", "-z").split("\0")
        if not opts & {"-u", "--update"}:
            out += _git(repo, "ls-files", "--others", "--exclude-standard", "-z").split("\0")
    out += [p for p in paths if p != "."]
    return [p for p in out if p]


def added_lines(repo: Path, path: str) -> list[str]:
    """Lines a pending `git add` of `path` would introduce."""
    try:
        tracked = bool(_git(repo, "ls-files", "--", path).strip())
        if tracked:
            diff = _git(repo, "diff", "-U0", "--no-color", "--", path)
            return [
                ln[1:]
                for ln in diff.splitlines()
                if ln.startswith("+") and not ln.startswith("+++")
            ]
        target = repo / path
        return target.read_text(errors="replace").splitlines() if target.is_file() else []
    except (OSError, subprocess.SubprocessError):
        return []


def commits_all(args: list[str]) -> bool:
    return any(
        a == "--all" or (a.startswith("-") and not a.startswith("--") and "a" in a[1:])
        for a in args
    )


def push_targets_default(args: list[str], current: str, default: str) -> bool:
    """True if this `git push` would update the default branch."""
    if any(a in ("--all", "--mirror") for a in args):
        return True
    positional, i = [], 0
    while i < len(args):
        a = args[i]
        if a in PUSH_VALUE_OPTS:
            i += 2
            continue
        if a == "--delete" or a == "-d":
            i += 1
            continue
        if not a.startswith("-"):
            positional.append(a)
        i += 1
    refspecs = positional[1:]  # positional[0] is the remote
    if not refspecs:
        return current == default  # pushes the current branch
    for raw in refspecs:
        spec = raw.lstrip("+")  # "+" forces the push; the destination is what matters
        dest = spec.split(":", 1)[1] if ":" in spec else spec
        if dest == "HEAD":
            dest = current
        if dest.removeprefix("refs/heads/") == default:
            return True
    return False


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True, timeout=30
    ).stdout


def matches(path: str, patterns: list[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(name, p) for p in patterns)


def main() -> None:
    command, cwd = hookio.read_payload()
    calls = git_calls(command, cwd)
    if not calls:
        hookio.allow()
    try:
        cfg = config.load(config.project_root(str(calls[0][1])))
        guards = cfg["guards"]
        forbidden = [re.compile(p) for p in guards["forbidden_patterns"]]
    except (config.ConfigError, re.error) as exc:
        hookio.block(GUARD, [f"invalid configuration: {exc}", "Fix stagegate.toml first."])
    default = cfg["project"]["default_branch"]
    protect = cfg["git"]["protect_default_branch"]

    problems: list[str] = []
    pending: dict[Path, list[str]] = {}  # repo -> paths a preceding `git add` will stage
    for sub, repo, args in calls:
        if sub == "add":
            try:
                pending.setdefault(repo, []).extend(pending_adds(repo, args))
            except (OSError, subprocess.SubprocessError):
                pass
            continue
        try:
            current = _git(repo, "branch", "--show-current").strip()
        except (OSError, subprocess.SubprocessError):
            continue  # not a git repo: git itself will fail
        if protect and sub == "push" and push_targets_default(args, current, default):
            problems.append(
                f"push to the default branch '{default}': push a feature branch "
                "and open a pull request"
            )
        if sub != "commit":
            continue
        if protect and current == default:
            problems.append(
                f"commit on the default branch '{default}': "
                f"create a branch first (git switch -c {cfg['git']['branch_prefix']}<slug>)"
            )
        try:
            files = _git(repo, "diff", "--cached", "--name-only", "-z").split("\0")
            diff = _git(repo, "diff", "--cached", "-U0", "--no-color")
            if commits_all(args):
                files += _git(repo, "diff", "--name-only", "-z").split("\0")
                diff += _git(repo, "diff", "-U0", "--no-color")
        except (OSError, subprocess.SubprocessError):
            continue
        added = [
            ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")
        ]
        for path in pending.get(repo, []):
            files.append(path)
            added += added_lines(repo, path)
        for f in sorted({f for f in files if f}):
            if matches(f, guards["blocked_files"]) and not matches(f, guards["allowed_files"]):
                problems.append(f"sensitive file staged: {f}")
        for line in added:
            if guards["block_latest_tag"] and LATEST.search(line):
                problems.append(
                    f"':latest' image tag (pin a digest or git SHA): {line.strip()[:120]}"
                )
            for rx in forbidden:
                if rx.search(line):
                    problems.append(f"forbidden pattern /{rx.pattern}/: {line.strip()[:120]}")

    if problems:
        unique = list(dict.fromkeys(problems))[:20]
        hookio.block(GUARD, [*unique, "Fix these, then try again."])
    hookio.allow()


if __name__ == "__main__":
    main()
