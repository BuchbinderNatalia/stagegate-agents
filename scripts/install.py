#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Install stagegate-agents into a git repository (standard library only).

Usage: install.py TARGET [--with-infra] [--force] [--dry-run]

What it does, in order:
  1. Refuses to run outside a git repository.
  2. Creates stagegate.toml if missing (auto-detects test/lint commands, a
     frontend folder and FastAPI); never edits an existing one except to turn
     infra.enabled on when --with-infra is given.
  3. Renders agents, skills and the stack profile into .claude/, copies the
     guard hooks to .claude/hooks/stagegate/, and (infra pack) the deploy
     workflow to .github/workflows/stagegate-deploy.yml.
  4. Merges .claude/settings.json (guard hooks + sandbox) and the stagegate
     section of CLAUDE.md, keeping everything the user already has.
  5. Adds secret-file patterns to .gitignore.
Files the user changed since the last install are skipped unless --force.
Exit codes: 0 ok, 2 refused (nothing written).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Deliberate: someone may run this file directly with an old Python. Checked before
# importing tomllib (3.11+) so they get this message, not a ModuleNotFoundError.
if sys.version_info < (3, 11):  # noqa: UP036  # pragma: no cover
    sys.exit("stagegate needs Python 3.11+ (macOS: brew install python@3.12)")

import tomllib  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hooks" / "lib"))
import config  # noqa: E402
import render  # noqa: E402

HOOK_FILES = [
    "commit-guard.sh",
    "merge-gate.sh",
    "load-test-guard.sh",
    "lib/run-guard.sh",
    "lib/shellwords.py",
    "lib/config.py",
    "lib/hookio.py",
    "lib/merge_gate.py",
    "lib/load_test_guard.py",
    "lib/commit_guard.py",
]
GITIGNORE_BEGIN = "# >>> stagegate: never commit secrets or state"
GITIGNORE_END = "# <<< stagegate"
GITIGNORE_LINES = [
    ".env",
    ".env.*",
    "!.env.example",
    "*.pem",
    "*.key",
    "*.tfstate",
    "*.tfstate.backup",
    "*.tfvars",
    "!*.tfvars.example",
    ".leak-denylist",
    ".claude/settings.local.json",
]


class InstallError(Exception):
    pass


def git_root(path: Path) -> Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InstallError(f"{path} is not inside a git repository (run `git init` first)") from exc
    return Path(out)


# --------------------------------------------------------------------------- detection
def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def detect(target: Path) -> dict[str, dict[str, str]]:
    """Best-effort guesses for a new stagegate.toml. Only sets what it is sure about."""
    found: dict[str, dict[str, str]] = {"project": {"name": target.name}, "stack": {}}
    stack = found["stack"]
    py_files = [target / "pyproject.toml", *target.glob("requirements*.txt"), target / "setup.cfg"]
    py_text = "\n".join(_read(p) for p in py_files).lower()

    backend = target / "backend"
    if (backend / "pyproject.toml").exists() or list(backend.glob("requirements*.txt")):
        stack["backend_dir"] = "backend"
        py_text += (
            "\n"
            + "\n".join(
                _read(p) for p in [backend / "pyproject.toml", *backend.glob("requirements*.txt")]
            ).lower()
        )
        if (backend / "tests").is_dir():
            stack["tests_dir"] = "backend/tests"
    if re.search(r"\bfastapi\b", py_text):
        stack["profile"] = "python-fastapi"

    for candidate in ("frontend", "web", "client", "ui"):
        if (target / candidate / "package.json").exists():
            stack["frontend_dir"] = candidate
            break

    if "ruff" not in py_text and not (target / "ruff.toml").exists():
        stack["lint_command"] = "python -m compileall -q ."  # safe fallback, no extra tools
    return found


def _set_value(text: str, table: str, key: str, value: str | bool) -> str:
    """Replace `key = ...` inside [table] of the shipped template, keeping comments."""
    rendered = ("true" if value else "false") if isinstance(value, bool) else json.dumps(value)
    pattern = re.compile(
        rf"(^\[{re.escape(table)}\][^\[]*?^{re.escape(key)}\s*=\s*)([^#\n]*?)(\s*(#.*)?$)",
        re.MULTILINE | re.DOTALL,
    )
    new, count = pattern.subn(lambda m: m.group(1) + rendered + m.group(3), text, count=1)
    if count != 1:
        raise InstallError(f"template has no [{table}] {key}")
    return new


def new_config_text(target: Path, with_infra: bool) -> str:
    text = (ROOT / "templates" / "stagegate.toml").read_text(encoding="utf-8")
    for table, values in detect(target).items():
        for key, value in values.items():
            text = _set_value(text, table, key, value)
    if with_infra:
        text = _set_value(text, "infra", "enabled", True)
    return text


# --------------------------------------------------------------------------- install
def plan(target: Path, with_infra: bool) -> tuple[dict[str, str], dict, list[str]]:
    """Return (files to write via manifest, config, notes) without touching disk."""
    notes: list[str] = []
    cfg_path = target / config.CONFIG_NAME
    if cfg_path.exists():
        cfg = config.load(target)
    else:  # what the new stagegate.toml will contain
        cfg = config._merge(config.DEFAULTS, tomllib.loads(new_config_text(target, with_infra)))
    problems = config.validate(cfg)
    if problems:
        raise InstallError("stagegate.toml problems:\n  " + "\n  ".join(problems))
    if with_infra and not cfg["infra"]["enabled"]:
        cfg["infra"]["enabled"] = True
        notes.append("infra.enabled set to true in stagegate.toml (--with-infra)")

    packs = ("core", "infra") if cfg["infra"]["enabled"] else ("core",)
    files = render.collect(cfg, target, packs)
    for rel in HOOK_FILES:
        files[f"{render.HOOK_DIR}/{rel}"] = (ROOT / "hooks" / rel).read_text(encoding="utf-8")
    return files, cfg, notes


def merged_gitignore(existing: str) -> str | None:
    if GITIGNORE_BEGIN in existing:
        return None
    block = "\n".join([GITIGNORE_BEGIN, *GITIGNORE_LINES, GITIGNORE_END]) + "\n"
    return (existing.rstrip("\n") + "\n\n" if existing.strip() else "") + block


def install(
    target: Path, with_infra: bool = False, force: bool = False, dry_run: bool = False
) -> int:
    target = git_root(target)
    settings_path = target / ".claude" / "settings.json"
    try:
        existing_settings = json.loads(settings_path.read_text()) if settings_path.exists() else {}
    except json.JSONDecodeError as exc:
        raise InstallError(f"{settings_path} is not valid JSON ({exc}); fix it first") from exc

    cfg_path = target / config.CONFIG_NAME
    created_config = not cfg_path.exists()
    files, cfg, notes = plan(target, with_infra)

    ctx = render.context(cfg, target)
    section = render.render(
        (ROOT / "templates" / "CLAUDE.md.tmpl").read_text(encoding="utf-8"), ctx, "CLAUDE.md.tmpl"
    )
    claude_md = target / "CLAUDE.md"
    new_claude_md = render.merge_claude_md(_read(claude_md) or None, section)
    new_settings = render.merge_settings(existing_settings, cfg)
    new_gitignore = merged_gitignore(_read(target / ".gitignore"))

    print(f"stagegate: installing into {target}{' (dry run)' if dry_run else ''}")
    report = render.write_files(files, target, force=force, dry_run=dry_run)

    if not dry_run:
        if created_config:
            cfg_path.write_text(new_config_text(target, with_infra), encoding="utf-8")
        elif any("infra.enabled set" in n for n in notes):
            cfg_path.write_text(
                _set_value(cfg_path.read_text(encoding="utf-8"), "infra", "enabled", True),
                encoding="utf-8",
            )
        for rel in files:
            if rel.endswith(".sh"):
                (target / rel).chmod(0o755)
        claude_md.write_text(new_claude_md, encoding="utf-8")
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(new_settings, indent=2) + "\n", encoding="utf-8")
        if new_gitignore is not None:
            (target / ".gitignore").write_text(new_gitignore, encoding="utf-8")

    for kind in ("created", "updated", "unchanged", "skipped"):
        if report[kind]:
            print(
                f"  {kind:9} {len(report[kind]):3}  "
                + ("" if kind != "skipped" else "(changed by you; --force to overwrite)")
            )
            if kind in ("skipped", "updated"):
                for rel in report[kind]:
                    print(f"             - {rel}")
    print(f"  {'config':9}      {'created' if created_config else 'kept'} {config.CONFIG_NAME}")
    print(
        "  merged         .claude/settings.json (guard hooks"
        + (", sandbox" if cfg["sandbox"]["enabled"] else ", sandbox OFF")
        + "), CLAUDE.md section"
    )
    for note in notes:
        print(f"  note           {note}")
    if not cfg["sandbox"]["enabled"]:
        print("  WARNING        sandbox.enabled = false: agents run with your full permissions")
    agents = sum(1 for f in files if f.startswith(".claude/agents/"))
    print(
        f"\n{agents} agents ready. Next:\n"
        f"  1. Review {config.CONFIG_NAME} (test command, folders, models)\n"
        "  2. Run scripts/doctor.sh (checks Python, git, claude, gh and the sandbox)\n"
        "  3. Commit on a branch, then in Claude Code: /feature-factory <your idea>"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Install stagegate-agents into a git repository.")
    ap.add_argument("target", nargs="?", default=".", type=Path)
    ap.add_argument("--with-infra", action="store_true", help="also install the infra pack")
    ap.add_argument("--force", action="store_true", help="overwrite files you changed")
    ap.add_argument("--dry-run", action="store_true", help="show what would change, write nothing")
    args = ap.parse_args(argv)
    try:
        return install(args.target.resolve(), args.with_infra, args.force, args.dry_run)
    except (InstallError, config.ConfigError, render.TemplateError) as exc:
        print(f"stagegate: {exc}", file=sys.stderr)
        print("stagegate: nothing was changed.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
