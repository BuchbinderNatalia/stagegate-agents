# SPDX-License-Identifier: Apache-2.0
"""Integration: one backend-builder cycle on examples/sample-app, through the real hooks.

The fake `claude` replays what backend-builder does for the CSV-export brief. Every
Bash step goes through the hooks the installer registered in .claude/settings.json,
so this proves the installed factory is wired correctly, offline and for free.
"""

from __future__ import annotations

import subprocess
import sys

from tests.conftest import Workspace, build_feature_steps, git


def test_builder_cycle(workspace: Workspace) -> None:
    result = workspace.claude(build_feature_steps(), agent="backend-builder")
    assert result["num_turns"] == 10 and result["total_cost_usd"] == 0.0
    repo = workspace.repo

    # The work happened on a feature branch, with exactly one commit.
    assert git(repo, "branch", "--show-current") == "feat/csv-export"
    assert git(repo, "log", "--oneline", "main..HEAD").count("\n") == 0
    assert "feat: export the catalogue as CSV" in git(repo, "log", "-1", "--format=%s")

    # The guards caught both mistakes, and nothing leaked.
    outcomes = [e["outcome"] for e in workspace.events()]
    assert outcomes.count("blocked") == 2
    blocked = [e["detail"] for e in workspace.events() if e["outcome"] == "blocked"]
    assert "sensitive file staged: .env" in blocked[0]
    assert "push to the default branch 'main'" in blocked[1]
    assert ".env" not in git(repo, "log", "--all", "--name-only", "--format=")

    # The branch reached the remote; the default branch did not move.
    remote = git(repo, "ls-remote", "--heads", "origin")
    assert "refs/heads/feat/csv-export" in remote
    main_files = git(repo, "ls-tree", "-r", "--name-only", "origin/main")
    assert "bookshelf/export.py" not in main_files

    # The feature works: the sample app's full suite passes on the branch.
    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "-q", "-p", "no:cacheprovider"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert tests.returncode == 0, tests.stdout
    assert "9 passed" in tests.stdout


def test_read_only_agents_cannot_write(workspace: Workspace) -> None:
    steps = [
        {
            "agent": "story-writer",
            "tool": "Write",
            "path": "x.md",
            "content": "x",
            "expect": "denied",
        },
        {"agent": "codebase-researcher", "tool": "Bash", "command": "touch x", "expect": "denied"},
        {
            "agent": "implementation-validator",
            "tool": "Edit",
            "path": "bookshelf/catalog.py",
            "content": "",
            "expect": "denied",
        },
        {"agent": "codebase-researcher", "tool": "Read"},
    ]
    workspace.claude(steps)
    assert not (workspace.repo / "x.md").exists()
    assert (workspace.repo / "bookshelf/catalog.py").read_text()  # untouched
