# SPDX-License-Identifier: Apache-2.0
"""Every agent and skill template renders into a valid Claude Code file under many configs."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hooks" / "lib"))
import config  # noqa: E402

spec = importlib.util.spec_from_file_location("render", ROOT / "scripts" / "render.py")
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)

KNOWN_TOOLS = {"Read", "Grep", "Glob", "Edit", "Write", "Bash", "WebFetch", "WebSearch"}
MODEL_ALIASES = {"haiku", "sonnet", "opus", "inherit"}
READ_ONLY = {
    "codebase-researcher",
    "story-writer",
    "spec-writer",
    "test-strategist",
    "implementation-validator",
}
NO_FILE_WRITES = READ_ONLY | {"pr-reviewer"}
CORE_AGENTS = {
    "codebase-researcher",
    "story-writer",
    "spec-writer",
    "test-strategist",
    "backend-builder",
    "frontend-builder",
    "test-verifier",
    "e2e-test-writer",
    "implementation-validator",
    "pr-reviewer",
}
# Project-specific technology that must not leak into the stack-neutral core templates.
NOT_IN_CORE = re.compile(
    r"Keycloak|Motor\b|MongoDB|Vault|OpenAI|Anthropic|Recharts|APScheduler|EKS|ArgoCD|"
    r"docker-compose run --rm backend|git push origin main",
)

CONFIGS = {
    "defaults": {},
    "fullstack": {
        "stack": {
            "profile": "python-fastapi",
            "backend_dir": "backend",
            "frontend_dir": "web",
            "run_prefix": "docker compose run --rm app",
        },
        "git": {"commit_style": "per-file"},
        "guards": {"forbidden_patterns": ["from legacy import"]},
    },
    "infra-on": {"infra": {"enabled": True}, "models": {"fast": "claude-haiku-5-5"}},
}


def rendered(name: str, tmp_path: Path) -> dict[str, str]:
    cfg = config._merge(config.DEFAULTS, CONFIGS[name])
    return render.collect(cfg, tmp_path / "proj")


def frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), "file must start with YAML frontmatter"
    head = text.split("---\n", 2)[1]
    return yaml.safe_load(head)


@pytest.mark.parametrize("cfg_name", list(CONFIGS))
def test_agents_render_valid(cfg_name: str, tmp_path: Path) -> None:
    files = rendered(cfg_name, tmp_path)
    agents = {k: v for k, v in files.items() if k.startswith(".claude/agents/")}
    assert agents, "no agents rendered"
    for path, text in agents.items():
        meta = frontmatter(text)
        stem = Path(path).stem
        assert meta["name"] == stem
        assert len(meta["description"]) > 40
        assert meta["model"] in MODEL_ALIASES or str(meta["model"]).startswith("claude-")
        tools = set(meta["tools"])
        assert tools <= KNOWN_TOOLS, f"{stem}: unknown tools {tools - KNOWN_TOOLS}"
        if stem in NO_FILE_WRITES:
            assert not tools & {"Edit", "Write"}, f"{stem} must not write files"
        if stem in READ_ONLY:
            assert "Bash" not in tools, f"{stem} is read-only and must not run commands"
        assert "SPDX-License-Identifier" in text


def test_frontend_builder_only_with_frontend(tmp_path: Path) -> None:
    assert ".claude/agents/frontend-builder.md" not in rendered("defaults", tmp_path)
    full = rendered("fullstack", tmp_path)
    names = {Path(p).stem for p in full if p.startswith(".claude/agents/")}
    assert names == CORE_AGENTS


def test_skills_have_frontmatter(tmp_path: Path) -> None:
    files = rendered("fullstack", tmp_path)
    skills = {k: v for k, v in files.items() if k.startswith(".claude/skills/")}
    assert set(skills) == {
        ".claude/skills/feature-factory/SKILL.md",
        ".claude/skills/build-with-tests/SKILL.md",
    }
    for path, text in skills.items():
        meta = frontmatter(text)
        assert meta["name"] == Path(path).parent.name
        assert len(meta["description"]) > 40


def test_feature_factory_only_names_existing_agents(tmp_path: Path) -> None:
    files = rendered("fullstack", tmp_path)
    chain = files[".claude/skills/feature-factory/SKILL.md"]
    role = r"(?:researcher|writer|builder|strategist|verifier|validator|reviewer)"
    mentioned = set(re.findall(rf"\b([a-z0-9]+(?:-[a-z0-9]+)*-{role})\b", chain))
    assert mentioned == CORE_AGENTS, (
        f"unknown: {mentioned - CORE_AGENTS}, missing: {CORE_AGENTS - mentioned}"
    )


def test_config_values_reach_the_agents(tmp_path: Path) -> None:
    files = rendered("fullstack", tmp_path)
    builder = files[".claude/agents/backend-builder.md"]
    assert "`docker compose run --rm app pytest -q`" in builder
    assert "Commit each file on its own" in builder
    assert "git push -u origin HEAD" in builder
    validator = files[".claude/agents/implementation-validator.md"]
    assert "from legacy import" in validator
    assert "Python + FastAPI" in files[".claude/stagegate/stack.md"]
    assert "React + TypeScript" in files[".claude/stagegate/stack.md"]


def test_infra_sections_only_when_enabled(tmp_path: Path) -> None:
    off = rendered("defaults", tmp_path)[".claude/agents/pr-reviewer.md"]
    on = rendered("infra-on", tmp_path)[".claude/agents/pr-reviewer.md"]
    assert "Infra (if changed)" not in off and "Infra (if changed)" in on


def test_core_templates_are_stack_neutral() -> None:
    for tmpl in [*ROOT.glob("agents/core/*.tmpl"), *ROOT.glob("skills/core/*/*.tmpl")]:
        hits = NOT_IN_CORE.findall(tmpl.read_text())
        assert not hits, f"{tmpl.relative_to(ROOT)} contains project-specific terms: {hits}"


def test_unknown_profile_is_an_error(tmp_path: Path) -> None:
    cfg = config._merge(config.DEFAULTS, {"stack": {"profile": "cobol"}})
    with pytest.raises(render.TemplateError, match="unknown stack.profile 'cobol'"):
        render.collect(cfg, tmp_path)


def test_never_pushes_to_default_branch(tmp_path: Path) -> None:
    for text in rendered("fullstack", tmp_path).values():
        assert "git push origin main" not in text
