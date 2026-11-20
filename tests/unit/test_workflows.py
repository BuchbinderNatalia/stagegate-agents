# SPDX-License-Identifier: Apache-2.0
"""Rules every workflow in this repo (and every one stagegate generates) must follow."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def rendered(tmp_path: Path) -> list[Path]:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/render_examples.py"), str(tmp_path)],
        check=True,
        capture_output=True,
    )
    return sorted(tmp_path.glob("*/.github/workflows/*.yml"))


def check(path: Path) -> None:
    text = path.read_text()
    wf = yaml.safe_load(text)
    triggers = wf.get(True) or wf.get("on")  # YAML 1.1 parses `on:` as True
    assert "pull_request_target" not in (triggers or {}), f"{path.name}: pull_request_target"
    assert "permissions" in wf, f"{path.name}: no top-level permissions"
    assert wf["permissions"] != "write-all", f"{path.name}: write-all"
    for name, job in wf["jobs"].items():
        assert "timeout-minutes" in job, f"{path.name}:{name} has no timeout"
        for step in job.get("steps", []):
            uses = step.get("uses")
            if uses and not uses.startswith("./"):
                assert PINNED.match(uses), f"{path.name}:{name}: unpinned action {uses}"
            if str(uses or "").startswith("actions/checkout@"):
                assert "persist-credentials" in step.get("with", {}), f"{path.name}:{name}"
    assert "@master" not in text and "@main" not in text


def test_repo_has_expected_workflows() -> None:
    names = {p.name for p in WORKFLOWS}
    assert names == {
        "ci.yml",
        "secret-scan.yml",
        "codeql.yml",
        "scorecard.yml",
        "dependency-review.yml",
        "workflow-lint.yml",
        "release.yml",
    }


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: p.name)
def test_repo_workflow_rules(path: Path) -> None:
    check(path)


def test_generated_workflows_follow_the_same_rules(tmp_path: Path) -> None:
    files = rendered(tmp_path)
    assert len(files) == 2
    for path in files:
        check(path)


def test_dependabot_covers_actions_and_pip() -> None:
    cfg = yaml.safe_load((ROOT / ".github/dependabot.yml").read_text())
    assert {u["package-ecosystem"] for u in cfg["updates"]} == {"github-actions", "pip"}
