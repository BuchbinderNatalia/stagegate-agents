#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check that stagegate-agents can work in a repository. Read-only.

Usage: doctor.py [TARGET]
Exit 0 = no errors (warnings allowed), 1 = at least one error.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hooks" / "lib"))
import config  # noqa: E402
import render  # noqa: E402

OK, WARN, ERR = "ok", "warn", "error"


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=20)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)


def sandbox_prerequisites() -> tuple[str, str]:
    """Claude Code's sandbox uses Seatbelt on macOS and bubblewrap (+ socat) on Linux/WSL2."""
    system = platform.system()
    if system == "Darwin":
        if shutil.which("sandbox-exec"):
            return OK, "macOS Seatbelt available"
        return WARN, "sandbox-exec not found; the sandbox may not start"
    if system == "Linux":
        missing = [t for t in ("bwrap", "socat") if not shutil.which(t)]
        if missing:
            return WARN, (
                f"missing {', '.join(missing)}: install bubblewrap and socat "
                "(e.g. apt install bubblewrap socat) or the sandbox can't start"
            )
        return OK, "bubblewrap and socat available"
    return WARN, f"{system}: Claude Code's sandbox supports macOS, Linux and WSL2 only"


def checks(target: Path) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    add = results.append

    v = sys.version_info
    add(
        (
            "python",
            OK if v >= (3, 11) else ERR,
            f"{v.major}.{v.minor}.{v.micro}"
            + ("" if v >= (3, 11) else " (need 3.11+; macOS: brew install python@3.12)"),
        )
    )

    code, out = _run(["git", "rev-parse", "--show-toplevel"], cwd=target)
    if code != 0:
        add(("git repo", ERR, f"{target} is not a git repository"))
        return results
    root = Path(out.splitlines()[-1])
    add(("git repo", OK, str(root)))

    if shutil.which("claude"):
        code, out = _run(["claude", "--version"])
        first = out.splitlines()[0] if out else ""
        add(
            (
                "claude CLI",
                OK if code == 0 else WARN,
                first if code == 0 else f"installed but `claude --version` failed: {first}",
            )
        )
    else:
        add(("claude CLI", WARN, "not found: install Claude Code to run the agents"))

    if shutil.which("gh"):
        code, _ = _run(["gh", "auth", "status"])
        add(
            (
                "gh CLI",
                OK if code == 0 else WARN,
                "authenticated"
                if code == 0
                else "not logged in: run `gh auth login` "
                "(needed to open PRs and for the merge gate)",
            )
        )
    else:
        add(("gh CLI", WARN, "not found: needed to open PRs and for the merge gate"))

    try:
        cfg = config.load(root)
        problems = config.validate(cfg)
        add(
            (
                "stagegate.toml",
                ERR if problems else OK,
                "; ".join(problems)
                if problems
                else ("found" if (root / config.CONFIG_NAME).exists() else "absent (defaults)"),
            )
        )
    except config.ConfigError as exc:
        add(("stagegate.toml", ERR, str(exc)))
        cfg = config.DEFAULTS

    manifest_path = root / render.MANIFEST
    try:
        manifest: dict[str, str] = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        manifest = {}
    if not manifest:
        add(("installed files", ERR, "not installed: run scripts/install.sh"))
    else:
        missing = [r for r in manifest if not (root / r).exists()]
        changed = [
            r
            for r in manifest
            if (root / r).exists()
            and render.sha((root / r).read_text(errors="replace")) != manifest[r]
        ]
        status = ERR if missing else (WARN if changed else OK)
        detail = f"{len(manifest)} files"
        if missing:
            detail += f"; MISSING: {', '.join(missing[:5])}"
        if changed:
            detail += f"; changed by you: {len(changed)} (re-install skips them)"
        add(("installed files", status, detail))
        hooks = [root / render.HOOK_DIR / h for h in render.HOOKS]
        not_exec = [h.name for h in hooks if h.exists() and not os.access(h, os.X_OK)]
        add(
            (
                "guard hooks",
                ERR if not_exec else OK,
                f"not executable: {', '.join(not_exec)}" if not_exec else "executable",
            )
        )

    try:
        settings = json.loads((root / ".claude" / "settings.json").read_text())
    except (OSError, json.JSONDecodeError):
        settings = {}
    commands = {
        h.get("command")
        for g in settings.get("hooks", {}).get("PreToolUse", [])
        for h in g.get("hooks", [])
    }
    wanted = {h["command"] for h in render.hook_entries()}
    add(
        (
            "hooks registered",
            OK if wanted <= commands else ERR,
            "settings.json has all 3 guards"
            if wanted <= commands
            else "guard hooks missing from .claude/settings.json: re-run install",
        )
    )

    if not settings.get("sandbox", {}).get("enabled"):
        add(
            (
                "sandbox",
                WARN,
                "OFF: agents run with your full permissions "
                "(set sandbox.enabled = true and re-install)",
            )
        )
    else:
        add(("sandbox", *sandbox_prerequisites()))
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check a stagegate-agents installation (read-only).")
    ap.add_argument("target", nargs="?", default=".", type=Path)
    args = ap.parse_args(argv)
    results = checks(args.target.resolve())
    icon = {OK: "✓", WARN: "!", ERR: "✗"}
    for name, status, detail in results:
        print(f"  {icon[status]} {name:16} {detail}")
    errors = sum(1 for _, s, _ in results if s == ERR)
    warnings = sum(1 for _, s, _ in results if s == WARN)
    print(f"\n{errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
