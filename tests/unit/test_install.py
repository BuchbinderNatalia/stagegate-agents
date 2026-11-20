# SPDX-License-Identifier: Apache-2.0
"""Install, re-install, uninstall and doctor against real temporary git repos."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hooks" / "lib"))
install = importlib.import_module("install")
uninstall = importlib.import_module("uninstall")
doctor = importlib.import_module("doctor")
render = importlib.import_module("render")


def make_repo(path: Path, files: dict[str, str] | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    for rel, content in (files or {}).items():
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text(content)
    return path


def agents(repo: Path) -> set[str]:
    return {p.stem for p in (repo / ".claude" / "agents").glob("*.md")}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "svc", {"pyproject.toml": "[tool.ruff]\n", "tests/__init__.py": ""})


# --------------------------------------------------------------------------- install
def test_fresh_install(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert install.main([str(repo)]) == 0
    assert len(agents(repo)) == 9  # no frontend → no frontend-builder
    assert (repo / ".claude/skills/feature-factory/SKILL.md").exists()
    assert (repo / ".claude/stagegate/stack.md").exists()
    for hook in render.HOOKS:
        assert os.access(repo / render.HOOK_DIR / hook, os.X_OK)
    settings = json.loads((repo / ".claude/settings.json").read_text())
    assert settings["sandbox"]["enabled"] is True
    assert len(settings["hooks"]["PreToolUse"][0]["hooks"]) == 3
    cfg = tomllib.loads((repo / "stagegate.toml").read_text())
    assert cfg["project"]["name"] == "svc"
    assert cfg["stack"]["lint_command"] == "ruff check ."  # ruff configured → kept
    assert render.CLAUDE_MD_BEGIN in (repo / "CLAUDE.md").read_text()
    assert ".env" in (repo / ".gitignore").read_text()
    assert "9 agents ready" in capsys.readouterr().out


def test_reinstall_is_a_no_op(repo: Path) -> None:
    install.main([str(repo)])
    snapshot = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git/" not in str(p)}
    install.main([str(repo)])
    after = {p: p.read_bytes() for p in repo.rglob("*") if p.is_file() and ".git/" not in str(p)}
    assert after == snapshot


def test_detects_fastapi_frontend_and_no_ruff(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path / "shop",
        {
            "backend/requirements.txt": "fastapi==0.115\nuvicorn\n",
            "backend/tests/test_x.py": "",
            "web/package.json": "{}",
        },
    )
    install.main([str(repo)])
    cfg = tomllib.loads((repo / "stagegate.toml").read_text())
    assert cfg["stack"]["profile"] == "python-fastapi"
    assert cfg["stack"]["backend_dir"] == "backend"
    assert cfg["stack"]["tests_dir"] == "backend/tests"
    assert cfg["stack"]["frontend_dir"] == "web"
    assert cfg["stack"]["lint_command"] == "python -m compileall -q ."
    assert "frontend-builder" in agents(repo) and len(agents(repo)) == 10
    assert "React + TypeScript" in (repo / ".claude/stagegate/stack.md").read_text()


def test_with_infra(repo: Path) -> None:
    install.main([str(repo), "--with-infra"])
    assert len(agents(repo)) == 18  # 9 core + 9 infra (argocd default)
    assert (repo / ".github/workflows/stagegate-deploy.yml").exists()
    assert tomllib.loads((repo / "stagegate.toml").read_text())["infra"]["enabled"] is True


def test_with_infra_turns_on_existing_config(repo: Path) -> None:
    install.main([str(repo)])
    install.main([str(repo), "--with-infra"])
    text = (repo / "stagegate.toml").read_text()
    assert tomllib.loads(text)["infra"]["enabled"] is True
    assert "# Optional infra pack" in text  # comments kept


def test_user_edits_survive_reinstall(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    install.main([str(repo)])
    agent = repo / ".claude/agents/story-writer.md"
    agent.write_text(agent.read_text() + "\nOur own rule.\n")
    (repo / "stagegate.toml").write_text(
        (repo / "stagegate.toml").read_text().replace('default = "sonnet"', 'default = "opus"')
    )
    capsys.readouterr()
    install.main([str(repo)])
    assert "Our own rule." in agent.read_text()
    assert "story-writer.md" in capsys.readouterr().out  # reported as skipped
    assert "model: opus" in (repo / ".claude/agents/spec-writer.md").read_text()
    install.main([str(repo), "--force"])
    assert "Our own rule." not in agent.read_text()


def test_existing_claude_md_and_settings_preserved(repo: Path) -> None:
    (repo / "CLAUDE.md").write_text("# House rules\n\nUse tabs.\n")
    (repo / ".claude").mkdir()
    (repo / ".claude/settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(make)"]}})
    )
    install.main([str(repo)])
    assert (repo / "CLAUDE.md").read_text().startswith("# House rules\n\nUse tabs.")
    settings = json.loads((repo / ".claude/settings.json").read_text())
    assert settings["permissions"] == {"allow": ["Bash(make)"]}


def test_invalid_settings_aborts_without_writing(repo: Path) -> None:
    (repo / ".claude").mkdir()
    (repo / ".claude/settings.json").write_text("{not json")
    assert install.main([str(repo)]) == 2
    assert not (repo / "stagegate.toml").exists()
    assert not (repo / ".claude/agents").exists()


def test_invalid_config_aborts(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "stagegate.toml").write_text("[stack]\ntest_comand = 'pytest'\n")
    assert install.main([str(repo)]) == 2
    assert "unknown key: stack.test_comand" in capsys.readouterr().err
    assert not (repo / ".claude").exists()


def test_not_a_git_repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "plain").mkdir()
    assert install.main([str(tmp_path / "plain")]) == 2
    assert "not inside a git repository" in capsys.readouterr().err


def test_dry_run_writes_nothing(repo: Path) -> None:
    before = sorted(p.name for p in repo.iterdir())
    assert install.main([str(repo), "--dry-run"]) == 0
    assert sorted(p.name for p in repo.iterdir()) == before


def test_installed_hook_works(repo: Path) -> None:
    install.main([str(repo)])
    (repo / ".env").write_text("SECRET=1\n")
    subprocess.run(["git", "add", "-f", ".env"], cwd=repo, check=True)
    payload = json.dumps({"tool_input": {"command": "git commit -m x"}, "cwd": str(repo)})
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo), STAGEGATE_PYTHON=sys.executable)
    result = subprocess.run(
        ["bash", str(repo / render.HOOK_DIR / "commit-guard.sh")],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        cwd=repo,
        timeout=60,
    )
    assert result.returncode == 2 and "sensitive file staged: .env" in result.stderr


def test_installed_hooks_leave_no_cache_files(repo: Path) -> None:
    install.main([str(repo)])
    payload = json.dumps({"tool_input": {"command": "git commit -m x"}, "cwd": str(repo)})
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(repo), STAGEGATE_PYTHON=sys.executable)
    env.pop("PYTHONDONTWRITEBYTECODE", None)  # -B must work on its own (-E ignores env vars)
    for hook in render.HOOKS:
        subprocess.run(
            ["bash", str(repo / render.HOOK_DIR / hook)],
            input=payload,
            text=True,
            capture_output=True,
            env=env,
            cwd=repo,
            timeout=60,
        )
    assert not list((repo / ".claude").rglob("__pycache__"))
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo,
        capture_output=True,
        text=True,
    ).stdout
    assert "__pycache__" not in status


def test_installed_hook_code_passes_strict_lint(repo: Path) -> None:
    """Users' own linters must not fail on stagegate's files (no config of ours applies)."""
    install.main([str(repo)])
    ruff = Path(sys.executable).parent / "ruff"
    p = subprocess.run(
        [
            str(ruff),
            "check",
            "--isolated",
            "--line-length",
            "100",
            "--select",
            "E,F,W,I,B,UP,S,RUF,ISC,PLW,PLE",
            "--ignore",
            "S603,S607,S404",
            str(repo / render.HOOK_DIR),
        ],
        capture_output=True,
        text=True,
    )
    assert p.returncode == 0, p.stdout


# --------------------------------------------------------------------------- uninstall
def test_uninstall(repo: Path) -> None:
    (repo / "CLAUDE.md").write_text("# House rules\n")
    install.main([str(repo)])
    changed = repo / ".claude/agents/pr-reviewer.md"
    changed.write_text("customised\n")
    assert uninstall.main([str(repo)]) == 0
    assert agents(repo) == {"pr-reviewer"}  # the customised one is kept
    assert (repo / "CLAUDE.md").read_text() == "# House rules\n"
    settings = json.loads((repo / ".claude/settings.json").read_text())
    assert "hooks" not in settings
    assert (repo / "stagegate.toml").exists()
    assert uninstall.main([str(repo), "--force", "--purge"]) == 0
    assert not (repo / ".claude/agents").exists()
    assert not (repo / "stagegate.toml").exists()


def test_uninstall_removes_claude_md_it_created(repo: Path) -> None:
    install.main([str(repo)])
    uninstall.main([str(repo)])
    assert not (repo / "CLAUDE.md").exists()


# --------------------------------------------------------------------------- doctor
def test_doctor(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        doctor.shutil, "which", lambda name: None if name in {"claude", "gh"} else "/x"
    )
    status = {name: s for name, s, _ in doctor.checks(repo)}
    assert status["installed files"] == doctor.ERR  # not installed yet
    install.main([str(repo)])
    status = {name: s for name, s, _ in doctor.checks(repo)}
    assert status["installed files"] == status["hooks registered"] == doctor.OK
    assert status["claude CLI"] == status["gh CLI"] == doctor.WARN
    os.chmod(repo / render.HOOK_DIR / "merge-gate.sh", 0o600)  # drop the exec bit
    assert {n: s for n, s, _ in doctor.checks(repo)}["guard hooks"] == doctor.ERR


def test_doctor_reports_sandbox_off(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    (repo / "stagegate.toml").write_text("[sandbox]\nenabled = false\n")
    install.main([str(repo)])
    sandbox = next(d for n, s, d in doctor.checks(repo) if n == "sandbox")
    assert "OFF" in sandbox


# --------------------------------------------------------------------------- shell wrappers
def test_install_sh_from_clone(repo: Path) -> None:
    env = dict(os.environ, STAGEGATE_PYTHON=sys.executable)
    out = subprocess.run(
        ["bash", str(ROOT / "scripts/install.sh"), str(repo)],
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr
    assert len(agents(repo)) == 9


def _tarball(tmp_path: Path) -> Path:
    tar = tmp_path / "stagegate.tar.gz"
    with tarfile.open(tar, "w:gz") as tf:
        for sub in ("agents", "skills", "stacks", "templates", "hooks", "scripts", "LICENSE"):
            tf.add(
                ROOT / sub,
                arcname=f"stagegate-agents-0.1.0/{sub}",
                filter=lambda t: None if "__pycache__" in t.name else t,
            )
    return tar


def test_install_sh_piped_download_with_checksum(repo: Path, tmp_path: Path) -> None:
    import hashlib

    tar = _tarball(tmp_path)
    digest = hashlib.sha256(tar.read_bytes()).hexdigest()
    script = (ROOT / "scripts/install.sh").read_text()
    env = dict(
        os.environ,
        STAGEGATE_PYTHON=sys.executable,
        STAGEGATE_TARBALL_URL=tar.as_uri(),
        STAGEGATE_SHA256=digest,
    )
    ok = subprocess.run(
        ["bash", "-s", "--", str(repo)],
        input=script,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert ok.returncode == 0, ok.stderr
    assert "checksum verified" in ok.stdout and len(agents(repo)) == 9

    env["STAGEGATE_SHA256"] = "0" * 64
    bad = subprocess.run(
        ["bash", "-s", "--", str(repo)],
        input=script,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    assert bad.returncode != 0 and "checksum mismatch" in bad.stderr
