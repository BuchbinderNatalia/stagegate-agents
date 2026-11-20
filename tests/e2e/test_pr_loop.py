# SPDX-License-Identifier: Apache-2.0
"""E2E smoke: builder → pull request → pr-reviewer → merge gate → merged.

Fakes stand in for Claude and GitHub; the hooks, agents and settings are the real
installed ones. The merge gate must hold the PR while CI is pending or red and let
it through only when every check is green.
"""

from __future__ import annotations

import json

from tests.conftest import Workspace, build_feature_steps, git


def test_pr_review_merge_loop(workspace: Workspace) -> None:
    repo = workspace.repo
    workspace.claude(build_feature_steps(), agent="backend-builder")

    # The orchestrator opens the PR; pr-reviewer reviews it read-only.
    workspace.claude(
        [
            {"tool": "Bash", "command": "gh pr create --title 'feat: CSV export' --base main"},
            {"agent": "pr-reviewer", "tool": "Bash", "command": "git diff --stat main...HEAD"},
            {
                "agent": "pr-reviewer",
                "tool": "Bash",
                "command": "gh pr checks 1 --json name,bucket || true",
            },
            {
                "agent": "pr-reviewer",
                "tool": "Write",
                "path": "bookshelf/export.py",
                "content": "# reviewer edit\n",
                "expect": "denied",
            },
        ]
    )
    assert (repo / "bookshelf/export.py").read_text().startswith("# SPDX")

    # CI still running → the merge gate blocks.
    workspace.claude([{"tool": "Bash", "command": "gh pr merge 1 --squash", "expect": "blocked"}])
    assert "tests: pending" in workspace.events()[-1]["detail"]

    # CI red → still blocked, and the failing check is named.
    workspace.set_checks("fail")
    workspace.claude([{"tool": "Bash", "command": "gh pr merge 1 --merge", "expect": "blocked"}])
    assert "tests: fail" in workspace.events()[-1]["detail"]

    # Wrapping the merge doesn't get around the gate.
    workspace.claude(
        [{"tool": "Bash", "command": "bash -c 'gh pr merge 1 --merge'", "expect": "blocked"}]
    )

    # CI green → allowed; GitHub (fake) merges into main.
    workspace.set_checks("pass")
    workspace.claude([{"tool": "Bash", "command": "gh pr merge 1 --merge"}])
    assert json.loads(workspace.gh_state.read_text())["prs"]["1"]["state"] == "MERGED"
    git(repo, "fetch", "-q", "origin")
    assert "bookshelf/export.py" in git(repo, "ls-tree", "-r", "--name-only", "origin/main")
    assert "Merge pull request #1" in git(repo, "log", "-1", "--format=%s", "origin/main")


def test_merge_gate_blocks_pr_without_checks(workspace: Workspace) -> None:
    workspace.claude(build_feature_steps(), agent="backend-builder")
    workspace.claude([{"tool": "Bash", "command": "gh pr create --base main"}])
    state = json.loads(workspace.gh_state.read_text())
    state["prs"]["1"]["checks"] = []
    workspace.gh_state.write_text(json.dumps(state))
    workspace.claude([{"tool": "Bash", "command": "gh pr merge 1", "expect": "blocked"}])
    assert "no CI checks reported" in workspace.events()[-1]["detail"]
