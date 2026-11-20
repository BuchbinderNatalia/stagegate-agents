# SPDX-License-Identifier: Apache-2.0
"""Docs stay true: relative links resolve, and named agents/skills/files exist."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = sorted([*ROOT.glob("*.md"), *ROOT.glob("docs/**/*.md"), *ROOT.glob("examples/**/README.md")])
LINK = re.compile(r"\]\(([^)\s]+)\)")
AGENTS = {
    p.name.removesuffix(".md.tmpl")
    for pack in ("core", "infra")
    for p in ROOT.glob(f"agents/{pack}/*.md.tmpl")
}
SKILLS = {p.parent.name for p in ROOT.glob("skills/*/*/SKILL.md.tmpl")}


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(ROOT)))
def test_relative_links_resolve(doc: Path) -> None:
    for target in LINK.findall(doc.read_text()):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        path = target.split("#", 1)[0]
        assert (doc.parent / path).exists(), f"{doc.name}: broken link {target}"


def test_readme_names_every_agent_and_skill() -> None:
    readme = (ROOT / "README.md").read_text()
    assert len(AGENTS) == 19 and len(SKILLS) == 5
    for name in AGENTS | SKILLS:
        assert name in readme, f"README doesn't mention {name}"


def test_required_project_files() -> None:
    for name in (
        "LICENSE",
        "NOTICE",
        "CITATION.cff",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "CHANGELOG.md",
        "docs/release-notes/v0.1.0.md",
    ):
        assert (ROOT / name).is_file(), name


def test_version_consistent() -> None:
    import tomllib

    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert f"version: {version}" in (ROOT / "CITATION.cff").read_text()
    assert f"## [{version}]" in (ROOT / "CHANGELOG.md").read_text()
    assert (ROOT / "docs" / "release-notes" / f"v{version}.md").exists()
    assert f"STAGEGATE_VERSION:-v{version}" in (ROOT / "scripts" / "install.sh").read_text()


def test_no_email_addresses_in_project_files() -> None:
    for name in ("CITATION.cff", "SECURITY.md", "CODE_OF_CONDUCT.md", "NOTICE", "README.md"):
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", (ROOT / name).read_text()), name
