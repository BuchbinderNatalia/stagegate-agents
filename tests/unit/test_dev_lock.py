# SPDX-License-Identifier: Apache-2.0
"""Keep the dev dependency sources and the hash-locked file consistent."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _name(req: str) -> str:
    return re.split(r"[<>=!~;\[ ]", req.strip(), maxsplit=1)[0].lower().replace("_", "-")


def _in_file() -> list[str]:
    lines = (ROOT / "requirements-dev.in").read_text().splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.startswith("#")]


def test_group_matches_requirements_in() -> None:
    group = tomllib.loads((ROOT / "pyproject.toml").read_text())["dependency-groups"]["dev"]
    assert sorted(group) == sorted(_in_file()), (
        "pyproject [dependency-groups].dev and requirements-dev.in differ — update both, "
        "then run scripts/lock-dev.sh"
    )


def test_every_direct_dependency_is_locked_with_hashes() -> None:
    lock = (ROOT / "requirements-dev.lock").read_text()
    pinned = {
        m.group(1).lower(): m.group(0)
        for m in re.finditer(r"^([A-Za-z0-9_.-]+)==\S+", lock, re.MULTILINE)
    }
    for req in _in_file():
        assert _name(req) in pinned, f"{req} missing from requirements-dev.lock"
    # Every pinned entry must carry at least one sha256 hash.
    blocks = re.split(r"\n(?=[A-Za-z0-9_.-]+==)", lock.split("\n", 6)[-1])
    for block in blocks:
        if "==" in block.split("\n", 1)[0]:
            assert "--hash=sha256:" in block, f"no hash for {block.splitlines()[0]}"


def test_no_runtime_dependencies() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["dependencies"] == [], "the factory must run on the standard library only"
