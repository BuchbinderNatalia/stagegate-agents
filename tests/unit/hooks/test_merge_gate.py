# SPDX-License-Identifier: Apache-2.0
"""Merge gate regression suite (ported from production, plus new cases).

A fake `gh` on PATH answers `gh pr checks`: PR 29 = all green, PR 31 = one
failing check, anything else = no checks. No network, no real GitHub.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

NL = "\n"
FAKE_GH = """#!/usr/bin/env bash
echo "$@" >> "$(dirname "$0")/gh-calls.log"
if [ "$1 $2" = "pr checks" ]; then
  case "$3" in
    29) echo '[{"name":"tests","bucket":"pass"},{"name":"lint","bucket":"skipping"}]'; exit 0 ;;
    31) echo '[{"name":"tests","bucket":"fail"}]'; exit 8 ;;
  esac
  echo "no checks reported on the pull request" >&2; exit 1
fi
exit 1
"""

ALLOW = [
    ("commit msg mention", 'git commit -m "block gh pr merge unless green"'),
    ("echo words", "echo gh pr merge"),
    ("grep pattern", 'grep -rn "gh pr merge" .claude'),
    ("git merge", "git merge --no-edit origin/main"),
    ("if/then without gh merge", "if true; then echo merge; fi"),
    ("green #29 in a group", "{ gh pr merge 29; }"),
    ("heredoc body", f"git commit -F - <<'EOF'{NL}gh pr merge is gated now{NL}EOF{NL}git log -1"),
    ("multi-line quoted message", f'git commit -m "line one{NL}gh pr merge 30 mention{NL}end"'),
    ("green #29 on second line", f"echo ok{NL}gh pr merge 29"),
    ("green #29 with --repo", "gh pr merge 29 --repo org/app --squash"),
    ("pr view is not a merge", "gh pr view 30 --json mergeable"),
]
BLOCK = [
    ("plain", "gh pr merge 30"),
    ("flags first", "gh pr merge --squash 30"),
    ("after cd &&", "cd /tmp && gh pr merge 30"),
    ("command gh", "command gh pr merge 30"),
    ("env VAR= gh", "env GH_TOKEN=x gh pr merge 30"),
    ("bare assignment", "GH_REPO=a/b gh pr merge 30"),
    ("path to gh", "/usr/local/bin/gh pr merge 30"),
    ("bash -c", 'bash -c "gh pr merge 30"'),
    ("sh -c nested", "sh -c 'cd /tmp && gh pr merge 30'"),
    ("eval", 'eval "gh pr merge 30"'),
    ("subshell", "(gh pr merge 30)"),
    ("unparseable + real merge", "gh pr merge 30; echo 'oops"),
    ("command group", "{ gh pr merge 30; }"),
    ("group + redirect + pipe", "{ git add . && gh pr merge 30; } 2>&1 | tee log.txt"),
    ("if condition", "if gh pr merge 30; then echo ok; fi"),
    ("negation", "! gh pr merge 30"),
    ("while/do", "while true; do gh pr merge 30; break; done"),
    ("newline-separated", f'echo "All checks good"{NL}gh pr merge 30 --squash'),
    ("backticks", "echo `gh pr merge 30`"),
    ("sudo -u USER", "sudo -u someone gh pr merge 30"),
    ("xargs -I {}", "xargs -I {} gh pr merge 30"),
    ("line continuation", f"git status \\{NL}  && gh pr merge 30"),
    ("after a heredoc", f"cat <<EOF{NL}notes{NL}EOF{NL}gh pr merge 30"),
    ("$(...) substitution", "echo $(gh pr merge 30)"),
    ("timeout wrapper", "timeout 30 gh pr merge 30"),
    ("failing check", "gh pr merge 31 --squash"),
    ("--repo value is not the PR number", "gh pr merge -R org/app 31"),
    ("--auto still needs green", "gh pr merge 30 --auto"),
    ("current branch, no checks", "gh pr merge --squash"),
]


@pytest.fixture
def fake_gh(tmp_path_factory: pytest.TempPathFactory) -> Path:
    bindir = tmp_path_factory.mktemp("bin")
    gh = bindir / "gh"
    gh.write_text(FAKE_GH)
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
    return bindir


@pytest.mark.parametrize(("name", "command"), ALLOW, ids=[c[0] for c in ALLOW])
def test_allows(run_hook, fake_gh: Path, name: str, command: str) -> None:
    result = run_hook("merge-gate.sh", command, extra_path=fake_gh)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(("name", "command"), BLOCK, ids=[c[0] for c in BLOCK])
def test_blocks(run_hook, fake_gh: Path, name: str, command: str) -> None:
    result = run_hook("merge-gate.sh", command, extra_path=fake_gh)
    assert result.returncode == 2, f"expected block, got {result.returncode}: {result.stderr}"
    assert "BLOCKED by stagegate merge gate" in result.stderr


def test_repo_flag_is_passed_to_gh(run_hook, fake_gh: Path) -> None:
    run_hook("merge-gate.sh", "gh pr merge 29 -R org/app", extra_path=fake_gh)
    calls = (fake_gh / "gh-calls.log").read_text()
    assert "pr checks 29 --repo org/app --json name,bucket" in calls


def test_failing_check_is_named(run_hook, fake_gh: Path) -> None:
    result = run_hook("merge-gate.sh", "gh pr merge 31", extra_path=fake_gh)
    assert "tests: fail" in result.stderr


def test_disabled_by_config(run_hook, fake_gh: Path, project: Path) -> None:
    (project / "stagegate.toml").write_text("[review]\nrequire_green_ci = false\n")
    assert run_hook("merge-gate.sh", "gh pr merge 30", extra_path=fake_gh).returncode == 0


def test_broken_config_fails_closed(run_hook, fake_gh: Path, project: Path) -> None:
    (project / "stagegate.toml").write_text("[review\n")
    result = run_hook("merge-gate.sh", "gh pr merge 29", extra_path=fake_gh)
    assert result.returncode == 2 and "stagegate.toml" in result.stderr


def test_unrelated_commands_skip_python(run_hook, fake_gh: Path) -> None:
    # Fast path: no "merge" in the input -> exit 0 without calling gh.
    assert run_hook("merge-gate.sh", "ls -la", extra_path=fake_gh).returncode == 0
    assert not (fake_gh / "gh-calls.log").exists()
