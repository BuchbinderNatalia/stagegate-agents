# SPDX-License-Identifier: Apache-2.0
"""Fixtures for running the real guard wrappers the way Claude Code does."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
HOOKS = ROOT / "hooks"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """An empty git repo used as $CLAUDE_PROJECT_DIR."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    # Agents work on feature branches; the default branch is protected by the commit guard.
    subprocess.run(["git", "checkout", "-q", "-b", "feat/test"], cwd=tmp_path, check=True)
    return tmp_path


RunHook = Callable[..., subprocess.CompletedProcess[str]]


@pytest.fixture
def run_hook(project: Path) -> RunHook:
    def _run(
        hook: str, command: str, cwd: Path | None = None, extra_path: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        payload = json.dumps(
            {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd or project)}
        )
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project), STAGEGATE_PYTHON=sys.executable)
        if extra_path:
            env["PATH"] = f"{extra_path}{os.pathsep}{env['PATH']}"
        return subprocess.run(
            ["bash", str(HOOKS / hook)],
            input=payload,
            text=True,
            capture_output=True,
            cwd=cwd or project,
            env=env,
            timeout=60,
        )

    return _run
