# SPDX-License-Identifier: Apache-2.0
"""Commit guard: block `git commit` when it would commit something unsafe.

Runs only when the command actually runs `git commit` (not on every Bash call).
Inspects what the commit would contain: staged changes, plus tracked unstaged
changes when -a/--all is used. Blocks on:
  - files matching guards.blocked_files (secrets, state, keys), unless they
    match guards.allowed_files (e.g. .env.example);
  - `image: ...:latest` in added lines (guards.block_latest_tag);
  - added lines matching any guards.forbidden_patterns regex.

Limits: `git commit <pathspec>` commits working-tree content of those paths,
which is not inspected; commits made outside Claude Code are not seen. Use the
repo's pre-commit/gitleaks hooks as the second layer.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
import hookio  # noqa: E402
import shellwords  # noqa: E402

GUARD = "commit guard"
LATEST = re.compile(r"image:\s*[\"']?\S+:latest\b", re.IGNORECASE)
# git global options that take a separate value: git -C <path> commit, git -c k=v commit
GIT_VALUE_OPTS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}


def find_commit(command: str, cwd: str | None) -> tuple[Path, bool] | None:
    """Return (repo dir, commit_all) for the first real `git commit`, else None."""
    base = Path(cwd) if cwd else Path.cwd()
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
        if i < len(argv) and argv[i] == "commit":
            opts = argv[i + 1 :]
            commit_all = any(
                a == "--all" or (a.startswith("-") and not a.startswith("--") and "a" in a[1:])
                for a in opts
            )
            return where, commit_all
    return None


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True, timeout=30
    ).stdout


def matches(path: str, patterns: list[str]) -> bool:
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(name, p) for p in patterns)


def main() -> None:
    command, cwd = hookio.read_payload()
    hit = find_commit(command, cwd)
    if hit is None:
        hookio.allow()
    repo, commit_all = hit
    try:
        cfg = config.load(config.project_root(str(repo)))
        guards = cfg["guards"]
        forbidden = [re.compile(p) for p in guards["forbidden_patterns"]]
    except (config.ConfigError, re.error) as exc:
        hookio.block(GUARD, [f"invalid configuration: {exc}", "Fix stagegate.toml first."])

    try:
        files = _git(repo, "diff", "--cached", "--name-only", "-z").split("\0")
        diff = _git(repo, "diff", "--cached", "-U0", "--no-color")
        if commit_all:
            files += _git(repo, "diff", "--name-only", "-z").split("\0")
            diff += _git(repo, "diff", "-U0", "--no-color")
    except (OSError, subprocess.SubprocessError):
        hookio.allow()  # not a git repo / git missing: git commit itself will fail

    problems: list[str] = []
    for f in sorted({f for f in files if f}):
        if matches(f, guards["blocked_files"]) and not matches(f, guards["allowed_files"]):
            problems.append(f"sensitive file staged: {f}")

    added = [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    for line in added:
        if guards["block_latest_tag"] and LATEST.search(line):
            problems.append(f"':latest' image tag (pin a digest or git SHA): {line.strip()[:120]}")
        for rx in forbidden:
            if rx.search(line):
                problems.append(f"forbidden pattern /{rx.pattern}/: {line.strip()[:120]}")

    if problems:
        hookio.block(GUARD, [*problems[:20], "Unstage or fix these, then commit again."])
    hookio.allow()


if __name__ == "__main__":
    main()
