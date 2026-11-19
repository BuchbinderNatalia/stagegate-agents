# SPDX-License-Identifier: Apache-2.0
"""Unit tests for scripts/leak_check.py."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("leak_check", ROOT / "scripts" / "leak_check.py")
leak_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(leak_check)

# Values are assembled at runtime so this test file itself stays clean.
ACCOUNT = "1234" + "5678" + "9012"
WORD = "base" + "44"


def rules(text: str, denylist: list[str] | None = None) -> list[str]:
    return [r for _, r in leak_check.scan_text(text, denylist or [])]


@pytest.mark.parametrize(
    "text",
    [
        "image: <AWS_ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/app:sha",
        "contact: you@example.com",
        "Co-Authored-By: Claude <noreply@anthropic.com>",
        "author: 1+someone@users.noreply.github.com",
        "remote: git@github.com:org/repo.git",
        "version 2026.11.19 build 1700000000",  # 10 digits, not 12
        "sha 3f2a1b9c8d7e6f5a4b3c2d1e0f9a8b7c6d5e4f3a",
    ],
)
def test_clean_lines(text: str) -> None:
    assert rules(text) == []


def test_account_id_flagged() -> None:
    assert rules(f"arn:aws:iam::{ACCOUNT}:role/x") == [
        "12-digit number (looks like an AWS account ID)"
    ]


def test_personal_email_flagged() -> None:
    personal = "someone" + "@" + "mail-provider.test"
    assert rules(f"le_email: {personal}") == ["email address outside the allowlist"]


def test_forbidden_word_case_insensitive() -> None:
    assert len(rules(f"import {WORD.upper()} sdk")) == 1


def test_denylist_reported_by_index_not_value() -> None:
    found = rules("bucket: my-secret-state-bucket", ["my-secret-state-bucket"])
    assert found == ["denylist entry #1"]
    assert "my-secret" not in found[0]


def test_denylist_from_env_and_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".leak-denylist").write_text("# comment\nFromFile\n\n")
    monkeypatch.setenv("LEAK_DENYLIST", "from-env\n")
    assert leak_check.load_denylist(tmp_path) == ["from-env", "fromfile"]


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "ok.md").write_text("hello you@example.com\n")
    assert leak_check.main(["--root", str(tmp_path)]) == 0

    (tmp_path / "bad.yml").write_text(f"account: {ACCOUNT}\n")
    assert leak_check.main(["--root", str(tmp_path)]) == 1
    assert "bad.yml:1" in capsys.readouterr().out


def test_denylist_file_itself_is_not_scanned(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".leak-denylist").write_text(f"{ACCOUNT}\n")
    assert leak_check.main(["--root", str(tmp_path)]) == 0


def test_repository_is_clean() -> None:
    """The real repo must pass (private denylist applies when configured locally/CI)."""
    assert leak_check.main(["--root", str(ROOT)]) == 0
