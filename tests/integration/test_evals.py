# SPDX-License-Identifier: Apache-2.0
"""The eval harness: tasks are well-formed, and grading fails what it should."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("evalrun", ROOT / "evals" / "run.py")
evalrun = importlib.util.module_from_spec(spec)
sys.modules["evalrun"] = evalrun  # dataclasses look their module up while executing
spec.loader.exec_module(evalrun)
TASKS = sorted(p.name for p in (ROOT / "evals" / "tasks").iterdir() if p.is_dir())


def pytest_in(app: Path) -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts="],
        cwd=app,
        capture_output=True,
    ).returncode


@pytest.mark.parametrize("task_id", TASKS)
def test_task_is_well_formed(task_id: str, tmp_path: Path) -> None:
    """Reference solution passes the hidden tests; the untouched app fails them."""
    task = ROOT / "evals" / "tasks" / task_id
    spec_ = evalrun.load_tasks(ROOT / "evals" / "tasks", task_id)[0]
    assert spec_.title and spec_.brief and len(spec_.acceptance) >= 3
    for mode in ("solution", "baseline"):
        app = tmp_path / mode
        shutil.copytree(ROOT / "examples" / "sample-app", app)
        if mode == "solution":
            shutil.copytree(task / "solution", app, dirs_exist_ok=True)
        shutil.copy(task / "hidden_test.py", app / "tests" / "test_hidden.py")
        assert (pytest_in(app) == 0) == (mode == "solution"), f"{task_id}/{mode}"


def run_eval(tmp_path: Path, *args: str, env: dict[str, str] | None = None):
    return subprocess.run(
        [sys.executable, str(ROOT / "evals" / "run.py"), "--out", str(tmp_path / "runs"), *args],
        capture_output=True,
        text=True,
        env=env or dict(os.environ),
        timeout=900,
    )


def results(tmp_path: Path) -> dict:
    return json.loads(next((tmp_path / "runs").glob("*/results.json")).read_text())


def test_stub_run_passes(tmp_path: Path) -> None:
    p = run_eval(tmp_path, "--stub", "--task", "remove-book")
    assert p.returncode == 0, p.stdout + p.stderr
    r = results(tmp_path)["results"][0]
    assert r["passed"] and r["cost_usd"] == 0.0
    assert r["checks"] | {"branch": None} == {
        "branch": None,
        "discipline": True,
        "suite": True,
        "hidden": True,
        "validator_critical": 0,
        "reviewer_critical": 0,
        "reviewer_verdict": "APPROVE",
        "builder_error": False,
    }
    assert "pass@1: 1/1" in next((tmp_path / "runs").glob("*/summary.md")).read_text()


def test_broken_solution_fails(tmp_path: Path) -> None:
    tasks = tmp_path / "tasks"
    shutil.copytree(ROOT / "evals" / "tasks" / "csv-export", tasks / "csv-export")
    export = tasks / "csv-export" / "solution" / "bookshelf" / "export.py"
    export.write_text(export.read_text().replace("writer.writerow(FIELDS)\n", ""))  # no header
    p = run_eval(tmp_path, "--stub", "--tasks-dir", str(tasks))
    assert p.returncode == 1
    r = results(tmp_path)["results"][0]
    assert not r["passed"] and r["checks"]["hidden"] is False


def test_work_on_main_fails_discipline(tmp_path: Path) -> None:
    repo, main_sha = evalrun.make_workspace(tmp_path, live=False)
    (repo / "bookshelf" / "x.py").write_text("x = 1\n")
    evalrun.git(repo, "add", "-A")
    evalrun.git(repo, "commit", "-q", "-m", "on main")  # bypasses hooks, like a human could
    task = evalrun.load_tasks(ROOT / "evals" / "tasks", "csv-export")[0]
    checks = evalrun.grade_repo(repo, main_sha, task)
    assert checks["discipline"] is False and checks["hidden"] is False


def test_live_mode_refuses_in_ci(tmp_path: Path) -> None:
    p = run_eval(tmp_path, "--task", "csv-export", env=dict(os.environ, CI="true"))
    assert p.returncode == 2 and "never run in CI" in p.stderr


def test_parsers() -> None:
    text = "### Critical\n> **[CRITICAL]** `a.py:1` — x\n> **[CRITICAL]** `b.py:2` — y\n"
    assert len(evalrun.CRITICAL.findall(text)) == 2
    assert evalrun.VERDICT.search("- Verdict: **REQUEST CHANGES**").group(1) == "REQUEST CHANGES"
    assert evalrun.VERDICT.search("Verdict: APPROVE").group(1) == "APPROVE"
