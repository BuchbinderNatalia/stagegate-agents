# SPDX-License-Identifier: Apache-2.0
"""Live: the real backend-builder flow builds CSV export in the sample app.

Judged by the same hidden acceptance tests the offline suite uses; the agent never sees them.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from tests.conftest import FAKE_BIN, TEST_EXPORT_PY, Workspace, git

PROMPT = (
    "Use the build-with-tests skill. Feature: add bookshelf/export.py with "
    "`to_csv(catalog: Catalog) -> str` that returns CSV text with the header row "
    "isbn,title,author,year followed by one row per book in Catalog.all() order, using the "
    "standard csv module with '\\n' line endings. Add tests. Work on the branch "
    "feat/csv-export, commit, and push the branch to origin. Do not open a pull request."
)


def test_live_build_with_tests(tmp_path: Path) -> None:
    ws = Workspace(tmp_path).setup("\n[sandbox]\nfail_if_unavailable = true\n")
    env = dict(ws.env)
    env["PATH"] = os.pathsep.join(p for p in env["PATH"].split(os.pathsep) if p != str(FAKE_BIN))
    claude = shutil.which("claude", path=env["PATH"])
    assert claude, "real claude not on PATH"

    run = subprocess.run(
        [
            claude,
            "-p",
            PROMPT,
            "--output-format",
            "json",
            "--permission-mode",
            "acceptEdits",
            "--max-turns",
            "40",
            "--allowedTools",
            "Bash(python -m pytest*)",
            "Bash(git *)",
        ],
        cwd=ws.repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    result = json.loads(run.stdout or "{}")
    print(
        f"\nlive run: turns={result.get('num_turns')} "
        f"api_equivalent_cost=${result.get('total_cost_usd', 0):.2f}"
    )
    assert run.returncode == 0 and not result.get("is_error"), run.stdout[-2000:] + run.stderr

    repo = ws.repo
    assert git(repo, "branch", "--show-current") == "feat/csv-export"
    assert git(repo, "log", "--oneline", "main..HEAD"), "no commit on the feature branch"
    assert "bookshelf/export.py" not in git(repo, "ls-tree", "-r", "--name-only", "origin/main")

    (repo / "tests" / "test_hidden_acceptance.py").write_text(TEST_EXPORT_PY)
    tests = subprocess.run(
        [sys.executable, "-m", "pytest", "-o", "addopts=", "-q", "-p", "no:cacheprovider"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert tests.returncode == 0, tests.stdout[-3000:]
