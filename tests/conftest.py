# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures: the sample app installed in a temp repo, fake claude/gh on PATH."""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
FAKE_BIN = ROOT / "tests" / "fixtures" / "fake-bin"
SAMPLE_APP = ROOT / "examples" / "sample-app"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


class Workspace:
    """A sample-app checkout with stagegate installed, a bare origin and fake CLIs."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.repo = tmp / "bookshelf"
        self.origin = tmp / "origin.git"
        self.log = tmp / "claude-log.jsonl"
        self.gh_state = tmp / "gh-state.json"
        venv_bin = Path(sys.executable).parent
        self.env = dict(
            os.environ,
            PATH=os.pathsep.join([str(FAKE_BIN), str(venv_bin), os.environ["PATH"]]),
            FAKE_CLAUDE_LOG=str(self.log),
            FAKE_GH_STATE=str(self.gh_state),
            STAGEGATE_PYTHON=sys.executable,
            GIT_AUTHOR_NAME="agent",
            GIT_AUTHOR_EMAIL="agent@example.com",
            GIT_COMMITTER_NAME="agent",
            GIT_COMMITTER_EMAIL="agent@example.com",
            PYTHONDONTWRITEBYTECODE="1",
        )

    def setup(self, extra_config: str = "") -> Workspace:
        shutil.copytree(SAMPLE_APP, self.repo, ignore=shutil.ignore_patterns("__pycache__"))
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], check=True)
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "user.name", "dev")
        git(self.repo, "config", "user.email", "dev@example.com")
        (self.repo / "stagegate.toml").write_text(
            '[stack]\ntest_command = "python -m pytest -q -p no:cacheprovider"\n' + extra_config
        )
        install = importlib.import_module("install")
        assert install.main([str(self.repo)]) == 0
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init with stagegate")
        git(self.repo, "remote", "add", "origin", str(self.origin))
        git(self.repo, "push", "-q", "origin", "main")
        return self

    def claude(self, steps: list[dict[str, Any]], agent: str = "main") -> dict[str, Any]:
        transcript = self.tmp / f"transcript-{len(list(self.tmp.glob('transcript-*')))}.json"
        transcript.write_text(json.dumps({"agent": agent, "steps": steps}))
        env = dict(self.env, FAKE_CLAUDE_TRANSCRIPT=str(transcript))
        p = subprocess.run(
            [str(FAKE_BIN / "claude"), "-p", "replay", "--output-format", "json"],
            cwd=self.repo,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        result = json.loads(p.stdout)
        assert not result["is_error"], result["result"]
        return result

    def events(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def set_checks(self, bucket: str, pr: int = 1) -> None:
        state = json.loads(self.gh_state.read_text())
        state["prs"][str(pr)]["checks"] = [{"name": "tests", "bucket": bucket}]
        self.gh_state.write_text(json.dumps(state))


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "hooks" / "lib")]
    return Workspace(tmp_path).setup()


# --------------------------------------------------------------------------- feature content
EXPORT_PY = '''# SPDX-License-Identifier: Apache-2.0
"""Export the catalogue as CSV."""

from __future__ import annotations

import csv
import io

from bookshelf.catalog import Catalog

FIELDS = ("isbn", "title", "author", "year")


def to_csv(catalog: Catalog) -> str:
    """CSV with a header row, books in Catalog.all() order."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\\n")
    writer.writerow(FIELDS)
    for book in catalog.all():
        writer.writerow([book.isbn, book.title, book.author, book.year])
    return buf.getvalue()
'''

TEST_EXPORT_PY = """# SPDX-License-Identifier: Apache-2.0
from bookshelf import Book, Catalog
from bookshelf.export import to_csv


# AC-1 [unit]: header row and one row per book, sorted like Catalog.all()
def test_rows_sorted_with_header() -> None:
    c = Catalog()
    c.add(Book("2", "Emma", "Jane Austen", 1815))
    c.add(Book("1", "Dune", "Frank Herbert", 1965))
    assert to_csv(c).splitlines() == [
        "isbn,title,author,year", "1,Dune,Frank Herbert,1965", "2,Emma,Jane Austen,1815"]


# AC-2 [unit]: empty catalogue exports only the header
def test_empty_catalog() -> None:
    assert to_csv(Catalog()) == "isbn,title,author,year\\n"


# AC-3 [unit]: commas and quotes are escaped
def test_escaping() -> None:
    c = Catalog()
    c.add(Book("3", 'Say "Hi", World', "A, B", 2000))
    assert to_csv(c).splitlines()[1] == '3,"Say ""Hi"", World","A, B",2000'
"""


def build_feature_steps() -> list[dict[str, Any]]:
    """What backend-builder does for the CSV-export brief, plus two mistakes the guards catch."""
    return [
        {"tool": "Bash", "command": "git switch -q -c feat/csv-export"},
        {"tool": "Write", "path": "bookshelf/export.py", "content": EXPORT_PY},
        {"tool": "Write", "path": "tests/test_export.py", "content": TEST_EXPORT_PY},
        {"tool": "Bash", "command": "python -m pytest -q -p no:cacheprovider"},
        {
            "tool": "Bash",
            "command": "git add bookshelf/export.py tests/test_export.py && "
            "git commit -q -m 'feat: export the catalogue as CSV'",
        },
        # Mistake 1: committing a secrets file.
        {"tool": "Write", "path": ".env", "content": "API_KEY=FAKE-not-a-real-key\n"},
        {
            "tool": "Bash",
            "command": "git add -f .env && git commit -q -m 'chore: env'",
            "expect": "blocked",
        },
        {"tool": "Bash", "command": "git reset -q .env && rm .env"},
        # Mistake 2: pushing straight to the default branch.
        {"tool": "Bash", "command": "git push -q origin HEAD:main", "expect": "blocked"},
        {"tool": "Bash", "command": "git push -q -u origin HEAD"},
    ]
