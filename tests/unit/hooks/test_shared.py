# SPDX-License-Identifier: Apache-2.0
"""Tests for the shared hook libraries: shellwords, config, run-guard."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[3] / "hooks"

sys.path.insert(0, str(HOOKS / "lib"))
import config  # noqa: E402
import shellwords  # noqa: E402


@pytest.mark.parametrize(
    ("src", "expected"),
    [
        ("ls -la", [["ls", "-la"]]),
        ("a && b || c; d | e", [["a"], ["b"], ["c"], ["d"], ["e"]]),
        ('echo "x; gh pr merge 1"', [["echo", "x; gh pr merge 1"]]),
        ("sudo -u bob env A=1 /usr/bin/tool run", [["/usr/bin/tool", "run"]]),
        ("timeout 5s nice -n 10 tool", [["tool"]]),
        ("bash -c 'a && b'", [["bash", "-c", "a && b"], ["a"], ["b"]]),
        ("cat <<EOF\nrm -rf /\nEOF\nnext", [["cat", "<<EOF"], ["next"]]),
        ("curl https://x.example/#frag", [["curl", "https://x.example/#frag"]]),
    ],
)
def test_commands(src: str, expected: list[list[str]]) -> None:
    assert shellwords.commands(src) == expected


def test_depth_limit() -> None:
    nested = "tool"
    for _ in range(6):
        nested = f"bash -c {json.dumps(nested)}"
    progs = [shellwords.program(a) for a in shellwords.commands(nested)]
    assert "tool" not in progs  # deeper than MAX_DEPTH is not followed


def test_config_defaults_and_merge(tmp_path: Path) -> None:
    assert config.load(tmp_path)["review"]["require_green_ci"] is True
    (tmp_path / "stagegate.toml").write_text('[guards]\nforbidden_hosts = ["a.example"]\n')
    cfg = config.load(tmp_path)
    assert cfg["guards"]["forbidden_hosts"] == ["a.example"]
    assert "localhost" in cfg["guards"]["local_hosts"]  # defaults kept


def test_config_error(tmp_path: Path) -> None:
    (tmp_path / "stagegate.toml").write_text("not = [valid\n")
    with pytest.raises(config.ConfigError):
        config.load(tmp_path)


def test_project_root_prefers_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert config.project_root("/") == tmp_path


@pytest.mark.parametrize("hook", ["merge-gate.sh", "commit-guard.sh", "load-test-guard.sh"])
def test_fails_closed_without_python(hook: str, tmp_path: Path) -> None:
    """If the fast path matches but no Python 3.11+ exists, block (exit 2), never exit 1."""
    command = {
        "merge-gate.sh": "gh pr merge 1",
        "commit-guard.sh": "git commit -m x",
        "load-test-guard.sh": "k6 run x.js",
    }[hook]
    env = {
        "PATH": "/usr/bin:/bin",
        "STAGEGATE_PYTHON": "/nonexistent/python",
        "CLAUDE_PROJECT_DIR": str(tmp_path),
        "HOME": str(tmp_path),
    }
    # Hide every python3* on the minimal PATH by pointing at an empty bin dir.
    empty = tmp_path / "bin"
    empty.mkdir()
    for name in ("cat", "dirname", "grep", "bash"):
        src = next(Path(d) / name for d in ("/usr/bin", "/bin") if (Path(d) / name).exists())
        (empty / name).symlink_to(src)
    env["PATH"] = str(empty)
    payload = json.dumps({"tool_input": {"command": command}})
    result = subprocess.run(
        [str(empty / "bash"), str(HOOKS / hook)],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        timeout=30,
    )
    assert result.returncode == 2, result.stderr
    assert "Python 3.11+ not found" in result.stderr


def test_all_hooks_executable() -> None:
    for hook in ("merge-gate.sh", "commit-guard.sh", "load-test-guard.sh"):
        assert os.access(HOOKS / hook, os.X_OK), hook
