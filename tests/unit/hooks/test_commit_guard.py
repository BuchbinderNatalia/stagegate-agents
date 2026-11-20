# SPDX-License-Identifier: Apache-2.0
"""Commit guard tests against a real temporary git repo."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def git(project: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=project, check=True, capture_output=True)


def stage(project: Path, name: str, content: str = "x\n") -> None:
    path = project / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    git(project, "add", name)


def test_clean_commit_allowed(run_hook, project: Path) -> None:
    stage(project, "app.py", "print('hi')\n")
    assert run_hook("commit-guard.sh", "git commit -m 'add app'").returncode == 0


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".env.production",
        "infra/terraform.tfstate",
        "prod.tfvars",
        "certs/server.pem",
        "deploy.key",
        "secrets.yaml",
    ],
)
def test_sensitive_files_blocked(run_hook, project: Path, name: str) -> None:
    stage(project, name)
    result = run_hook("commit-guard.sh", "git commit -m 'oops'")
    assert result.returncode == 2
    assert f"sensitive file staged: {name}" in result.stderr


@pytest.mark.parametrize("name", [".env.example", "vars.tfvars.example"])
def test_example_files_allowed(run_hook, project: Path, name: str) -> None:
    stage(project, name)
    assert run_hook("commit-guard.sh", "git commit -m 'docs'").returncode == 0


def test_latest_tag_blocked(run_hook, project: Path) -> None:
    stage(project, "k8s/deploy.yaml", "spec:\n  image: registry.example.com/app:latest\n")
    result = run_hook("commit-guard.sh", "git commit -m 'deploy'")
    assert result.returncode == 2 and ":latest" in result.stderr


def test_latest_tag_allowed_when_disabled(run_hook, project: Path) -> None:
    (project / "stagegate.toml").write_text("[guards]\nblock_latest_tag = false\n")
    stage(project, "k8s/deploy.yaml", "image: app:latest\n")
    assert run_hook("commit-guard.sh", "git commit -m 'deploy'").returncode == 0


def test_forbidden_pattern(run_hook, project: Path) -> None:
    (project / "stagegate.toml").write_text(
        "[guards]\nforbidden_patterns = ['from legacy_sdk import']\n"
    )
    stage(project, "svc.py", "from legacy_sdk import client\n")
    result = run_hook("commit-guard.sh", "git commit -m 'feat'")
    assert result.returncode == 2 and "forbidden pattern" in result.stderr


def test_invalid_regex_fails_closed(run_hook, project: Path) -> None:
    (project / "stagegate.toml").write_text("[guards]\nforbidden_patterns = ['(']\n")
    stage(project, "a.py")
    result = run_hook("commit-guard.sh", "git commit -m 'x'")
    assert result.returncode == 2 and "invalid configuration" in result.stderr


def test_commit_all_includes_unstaged_tracked(run_hook, project: Path) -> None:
    stage(project, "deploy.yaml", "image: app:v1\n")
    git(project, "commit", "-q", "-m", "init")
    (project / "deploy.yaml").write_text("image: app:latest\n")  # modified, not staged
    assert run_hook("commit-guard.sh", "git commit -m 'x'").returncode == 0
    assert run_hook("commit-guard.sh", "git commit -am 'x'").returncode == 2


def test_git_dash_c_path(run_hook, project: Path) -> None:
    sub = project / "nested"
    sub.mkdir()
    git(sub, "init", "-q")
    stage(sub, ".env")
    result = run_hook("commit-guard.sh", "git -C nested commit -m 'x'")
    assert result.returncode == 2


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "echo 'git commit -m x'",
        "git log --grep commit",
        "git commit-tree HEAD^{tree} -m x",
    ],
)
def test_not_a_commit(run_hook, project: Path, command: str) -> None:
    stage(project, ".env")  # would block a real commit
    assert run_hook("commit-guard.sh", command).returncode == 0


def test_commit_inside_bash_c(run_hook, project: Path) -> None:
    stage(project, ".env")
    assert run_hook("commit-guard.sh", "bash -c 'git add -A && git commit -m x'").returncode == 2


# --------------------------------------------------------------------------- default branch
def on_main(project: Path) -> None:
    stage(project, "README.md", "hi\n")
    git(project, "commit", "-q", "-m", "init")
    git(project, "checkout", "-q", "-B", "main")


def test_commit_on_default_branch_blocked(run_hook, project: Path) -> None:
    on_main(project)
    stage(project, "app.py", "x = 1\n")
    result = run_hook("commit-guard.sh", "git commit -m 'feat: x'")
    assert result.returncode == 2 and "commit on the default branch 'main'" in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "git push origin main",
        "git push origin HEAD:main",
        "git push -f origin +feat/test:refs/heads/main",
        "git push --all origin",
        "git push -u origin feat/test main",
        "git switch main && git push",
    ],
)
def test_push_to_default_branch_blocked(run_hook, project: Path, command: str) -> None:
    on_main(project) if command.endswith("git push") else None
    result = run_hook("commit-guard.sh", command)
    assert result.returncode == 2, result.stderr
    assert "push to the default branch 'main'" in result.stderr


@pytest.mark.parametrize(
    "command",
    [
        "git push -u origin HEAD",
        "git push origin feat/test",
        "git push",
        "git push -o ci.skip origin HEAD",
    ],
)
def test_push_feature_branch_allowed(run_hook, project: Path, command: str) -> None:
    assert run_hook("commit-guard.sh", command).returncode == 0


def test_bare_push_on_default_branch_blocked(run_hook, project: Path) -> None:
    on_main(project)
    assert run_hook("commit-guard.sh", "git push").returncode == 2


def test_protection_can_be_disabled(run_hook, project: Path) -> None:
    (project / "stagegate.toml").write_text("[git]\nprotect_default_branch = false\n")
    on_main(project)
    stage(project, "app.py", "x = 1\n")
    assert run_hook("commit-guard.sh", "git commit -m x").returncode == 0
    assert run_hook("commit-guard.sh", "git push origin main").returncode == 0


# --------------------------------------------------------------------------- add && commit
def write(project: Path, name: str, content: str = "x\n") -> None:
    (project / name).parent.mkdir(parents=True, exist_ok=True)
    (project / name).write_text(content)


@pytest.mark.parametrize(
    "command",
    [
        "git add -f .env && git commit -m x",
        "git add .env; git commit -m x",
        "git add -A && git commit -m x",
        "git add . && git commit -m x",
        "bash -c 'git add .env && git commit -m x'",
    ],
)
def test_add_in_same_command_is_checked(run_hook, project: Path, command: str) -> None:
    write(project, ".env", "KEY=1\n")  # not staged yet when the hook runs
    result = run_hook("commit-guard.sh", command)
    assert result.returncode == 2 and "sensitive file staged: .env" in result.stderr


def test_add_of_ignored_file_with_dash_a_is_not_flagged(run_hook, project: Path) -> None:
    write(project, ".gitignore", ".env\n")
    write(project, ".env", "KEY=1\n")
    write(project, "app.py", "x = 1\n")
    assert run_hook("commit-guard.sh", "git add -A && git commit -m x").returncode == 0


def test_added_content_checked_in_same_command(run_hook, project: Path) -> None:
    write(project, "k8s/d.yaml", "image: app:latest\n")
    result = run_hook("commit-guard.sh", "git add k8s/d.yaml && git commit -m x")
    assert result.returncode == 2 and ":latest" in result.stderr


def test_clean_add_and_commit_allowed(run_hook, project: Path) -> None:
    write(project, "app.py", "x = 1\n")
    assert run_hook("commit-guard.sh", "git add app.py && git commit -m x").returncode == 0
