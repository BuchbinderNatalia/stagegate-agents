# SPDX-License-Identifier: Apache-2.0
"""Tests for scripts/render.py, the config template and the CLAUDE.md template."""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hooks" / "lib"))
import config  # noqa: E402

spec = importlib.util.spec_from_file_location("render", ROOT / "scripts" / "render.py")
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)

CTX = {
    "a": {"name": "app", "on": True, "off": False, "items": ["x", "y"], "empty": ""},
}


# --------------------------------------------------------------------------- engine
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("{{ a.name }}", "app"),
        ("{{a.name}}", "app"),
        ("{{ a.on }}/{{ a.off }}", "true/false"),
        ("{{ a.items }}", "x, y"),
        ("{{ a.items | json }}", '["x", "y"]'),
        ("{{ a.items | bullets }}", "- x\n- y"),
        ("{{#if a.on}}yes{{/if}}", "yes"),
        ("{{#if a.off}}yes{{else}}no{{/if}}", "no"),
        ("{{#if a.empty}}yes{{else}}no{{/if}}", "no"),
        ("{{#unless a.off}}shown{{/unless}}", "shown"),
        ("{{#if a.on}}1{{#if a.off}}2{{else}}3{{/if}}4{{/if}}", "134"),
        ("{{#if a.off}}{{#if a.on}}hidden{{/if}}{{/if}}end", "end"),
        ("image: app:${{ github.sha }}", "image: app:${{ github.sha }}"),
        ("no tags", "no tags"),
    ],
)
def test_render(text: str, expected: str) -> None:
    assert render.render(text, CTX) == expected


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("{{ a.missing }}", "unknown key: a.missing"),
        ("{{#if a.off}}{{ a.missing }}{{/if}}", "unknown key"),  # strict even when hidden
        ("{{ a.name | shout }}", "unknown filter"),
        ("{{#if a.on}}open", "unclosed"),
        ("{{/if}}", "unexpected"),
        ("{{else}}", "without an open"),
        ("{{#if a.on}}x{{/unless}}", "unexpected"),
        ("left {{ over", "leftover"),
    ],
)
def test_render_errors(text: str, message: str) -> None:
    with pytest.raises(render.TemplateError, match=message):
        render.render(text, CTX, "t.md")


def test_partials() -> None:
    parts = {"greet": "hi {{ a.name }}{{#if a.on}}!{{/if}}", "loop": "{{> loop }}"}
    assert render.render("[{{> greet }}]", CTX, partials=parts) == "[hi app!]"
    assert render.render("{{#if a.off}}{{> greet }}{{/if}}x", CTX, partials=parts) == "x"
    with pytest.raises(render.TemplateError, match="unknown partial: nope"):
        render.render("{{> nope }}", CTX, partials=parts)
    with pytest.raises(render.TemplateError, match="nested too deep"):
        render.render("{{> loop }}", CTX, partials=parts)


def test_error_names_the_template() -> None:
    with pytest.raises(render.TemplateError, match="agents/x.md.tmpl"):
        render.render("{{ nope }}", CTX, "agents/x.md.tmpl")


def test_project_name_defaults_to_folder(tmp_path: Path) -> None:
    target = tmp_path / "my-service"
    target.mkdir()
    ctx = render.context(config.load(target), target)
    assert ctx["project"]["name"] == "my-service"


# --------------------------------------------------------------------------- config template
def test_config_template_documents_every_default() -> None:
    shipped = tomllib.loads((ROOT / "templates" / "stagegate.toml").read_text())
    assert shipped == config.DEFAULTS, "templates/stagegate.toml and config.DEFAULTS diverged"


def test_validate_reports_problems() -> None:
    cfg = copy.deepcopy(config.DEFAULTS)
    cfg["stack"]["test_command"] = 5
    cfg["sandbox"]["enabled"] = "yes"
    cfg["guards"]["local_hosts"] = "localhost"
    cfg["typo"] = {}
    problems = config.validate(cfg)
    assert "stack.test_command must be a string" in problems
    assert "sandbox.enabled must be true or false" in problems
    assert "guards.local_hosts must be a list of strings" in problems
    assert "unknown key: typo" in problems


def test_cli_rejects_invalid_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "stagegate.toml").write_text("[stack]\ntest_comand = 'pytest'\n")
    tmpl = tmp_path / "t.tmpl"
    tmpl.write_text("{{ stack.test_command }}")
    assert render.main([str(tmpl), "--target", str(tmp_path)]) == 2
    assert "unknown key: stack.test_comand" in capsys.readouterr().err


# --------------------------------------------------------------------------- CLAUDE.md
@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"stack": {"frontend_dir": "web", "run_prefix": "docker compose run --rm app"}},
        {"sandbox": {"enabled": False}, "infra": {"enabled": True}},
        {"guards": {"forbidden_patterns": ["legacy"]}},
    ],
)
def test_claude_md_template_renders(tmp_path: Path, overrides: dict) -> None:
    cfg = config._merge(config.DEFAULTS, overrides)
    text = (ROOT / "templates" / "CLAUDE.md.tmpl").read_text()
    out = render.render(text, render.context(cfg, tmp_path), "CLAUDE.md.tmpl")
    assert "## stagegate" in out
    if overrides.get("sandbox", {}).get("enabled") is False:
        assert "Sandbox is OFF" in out
    if overrides == {}:
        assert "secrets and state files, `:latest` image tags." in out
    if overrides.get("guards"):
        assert "configured forbidden patterns" in out
    if overrides.get("stack", {}).get("run_prefix"):
        assert "`docker compose run --rm app pytest -q`" in out


def test_claude_md_merge_preserves_user_content() -> None:
    user = "# My project\n\nOwn rules.\n"
    once = render.merge_claude_md(user, "section v1")
    assert once.startswith(user.rstrip("\n"))
    assert "section v1" in once
    twice = render.merge_claude_md(once, "section v2")
    assert "section v2" in twice and "section v1" not in twice
    assert twice.count(render.CLAUDE_MD_BEGIN) == 1
    assert twice.startswith("# My project")
    assert render.merge_claude_md(None, "s").startswith(render.CLAUDE_MD_BEGIN)
    spdx = "<!-- SPDX-License-Identifier: Apache-2.0 -->\n## stagegate\n"
    assert "SPDX" not in render.merge_claude_md(None, spdx)


# --------------------------------------------------------------------------- settings.json
def test_settings_merge_adds_hooks_and_sandbox() -> None:
    s = render.merge_settings({}, config.DEFAULTS)
    commands = [h["command"] for h in s["hooks"]["PreToolUse"][0]["hooks"]]
    assert all(c.startswith('"$CLAUDE_PROJECT_DIR"/.claude/hooks/stagegate/') for c in commands)
    assert len(commands) == 3
    assert s["sandbox"]["enabled"] is True
    assert "~/.aws" in s["sandbox"]["filesystem"]["denyRead"]
    assert "git push *" in s["sandbox"]["excludedCommands"]
    json.dumps(s)  # serialisable


def test_settings_merge_keeps_user_settings_and_is_idempotent() -> None:
    user = {
        "permissions": {"allow": ["Bash(make test)"]},
        "hooks": {
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine.sh"}]}
            ]
        },
        "sandbox": {
            "network": {"allowedDomains": ["internal.example.com"]},
            "excludedCommands": ["docker *"],
        },
    }
    once = render.merge_settings(user, config.DEFAULTS)
    twice = render.merge_settings(once, config.DEFAULTS)
    assert once == twice
    assert once["permissions"] == user["permissions"]
    cmds = [h["command"] for h in once["hooks"]["PreToolUse"][0]["hooks"]]
    assert cmds[0] == "mine.sh" and len(cmds) == 4
    assert "internal.example.com" in once["sandbox"]["network"]["allowedDomains"]
    assert once["sandbox"]["excludedCommands"][0] == "docker *"
    assert user["hooks"]["PreToolUse"][0]["hooks"] == [{"type": "command", "command": "mine.sh"}]


def test_settings_sandbox_opt_out() -> None:
    cfg = config._merge(config.DEFAULTS, {"sandbox": {"enabled": False}})
    s = render.merge_settings({}, cfg)
    assert s["sandbox"] == {"enabled": False}


def test_remove_from_settings_leaves_no_empty_sections() -> None:
    installed = render.merge_settings({"model": "sonnet"}, config.DEFAULTS)
    removed = render.remove_from_settings(installed)
    assert "hooks" not in removed and removed["model"] == "sonnet"


def test_remove_from_settings_only_removes_ours() -> None:
    user = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": "mine.sh"}]}]}}
    installed = render.merge_settings(user, config.DEFAULTS)
    removed = render.remove_from_settings(installed)
    assert removed["hooks"]["PreToolUse"] == [
        {"matcher": "Bash", "hooks": [{"command": "mine.sh"}]}
    ]


# --------------------------------------------------------------------------- write_files
def test_write_files_never_clobbers_user_edits(tmp_path: Path) -> None:
    files = {".claude/agents/a.md": "v1\n", ".claude/agents/b.md": "v1\n"}
    r1 = render.write_files(files, tmp_path)
    assert sorted(r1["created"]) == sorted(files)

    (tmp_path / ".claude/agents/a.md").write_text("my edit\n")  # user customises a.md
    r2 = render.write_files({k: "v2\n" for k in files}, tmp_path)
    assert r2["skipped"] == [".claude/agents/a.md"]
    assert r2["updated"] == [".claude/agents/b.md"]
    assert (tmp_path / ".claude/agents/a.md").read_text() == "my edit\n"

    r3 = render.write_files({k: "v2\n" for k in files}, tmp_path, force=True)
    assert r3["updated"] == [".claude/agents/a.md"]


def test_write_files_dry_run_writes_nothing(tmp_path: Path) -> None:
    r = render.write_files({"x.md": "x"}, tmp_path, dry_run=True)
    assert r["created"] == ["x.md"]
    assert not any(tmp_path.iterdir())


def test_write_files_idempotent(tmp_path: Path) -> None:
    render.write_files({"x.md": "x"}, tmp_path)
    assert render.write_files({"x.md": "x"}, tmp_path)["unchanged"] == ["x.md"]
