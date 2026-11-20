#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Remove stagegate-agents from a repository (standard library only).

Usage: uninstall.py TARGET [--force] [--purge] [--dry-run]

Removes the files stagegate installed (from .claude/stagegate.manifest.json),
stagegate's hook entries in .claude/settings.json and the stagegate section of
CLAUDE.md. Keeps:
  - files you changed since install (unless --force)
  - stagegate.toml (unless --purge), the .gitignore block and the sandbox
    settings: they are safe to keep, and removing them could drop your own edits.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hooks" / "lib"))
import install  # noqa: E402
import render  # noqa: E402


def _prune_empty_dirs(path: Path, stop: Path) -> None:
    while path != stop and path.is_dir() and not any(path.iterdir()):
        path.rmdir()
        path = path.parent


def uninstall(target: Path, force: bool = False, purge: bool = False, dry_run: bool = False) -> int:
    target = install.git_root(target)
    manifest_path = target / render.MANIFEST
    try:
        manifest: dict[str, str] = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        manifest = {}
    if not manifest:
        print("stagegate: no install manifest found; nothing to remove.")
        return 0

    removed, kept = [], []
    for rel, digest in sorted(manifest.items()):
        path = target / rel
        if not path.exists():
            continue
        if render.sha(path.read_text(encoding="utf-8", errors="replace")) != digest and not force:
            kept.append(rel)
            continue
        removed.append(rel)
        if not dry_run:
            path.unlink()
            _prune_empty_dirs(path.parent, target)

    settings_path = target / ".claude" / "settings.json"
    claude_md = target / "CLAUDE.md"
    if not dry_run:
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
            settings_path.write_text(
                json.dumps(render.remove_from_settings(settings), indent=2) + "\n"
            )
        if claude_md.exists():
            text = claude_md.read_text(encoding="utf-8")
            if render.CLAUDE_MD_BEGIN in text and render.CLAUDE_MD_END in text:
                head, _, rest = text.partition(render.CLAUDE_MD_BEGIN)
                _, _, tail = rest.partition(render.CLAUDE_MD_END)
                remaining = (head.rstrip("\n") + "\n" + tail.lstrip("\n")).strip()
                if remaining:
                    claude_md.write_text(remaining + "\n", encoding="utf-8")
                else:
                    claude_md.unlink()
        if kept:
            manifest_path.write_text(
                json.dumps({k: manifest[k] for k in kept}, indent=2, sort_keys=True) + "\n"
            )
        else:
            manifest_path.unlink()
            _prune_empty_dirs(manifest_path.parent, target)
        if purge and (target / "stagegate.toml").exists():
            (target / "stagegate.toml").unlink()

    print(
        f"stagegate: {'would remove' if dry_run else 'removed'} {len(removed)} files"
        " and the guard hooks from .claude/settings.json and the CLAUDE.md section."
    )
    for rel in kept:
        print(f"  kept (changed by you; --force to remove): {rel}")
    print(
        "  kept: sandbox settings in .claude/settings.json and the .gitignore block"
        + ("" if purge else ", stagegate.toml (--purge to remove)")
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Remove stagegate-agents from a repository.")
    ap.add_argument("target", nargs="?", default=".", type=Path)
    ap.add_argument("--force", action="store_true", help="also remove files you changed")
    ap.add_argument("--purge", action="store_true", help="also remove stagegate.toml")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    try:
        return uninstall(args.target.resolve(), args.force, args.purge, args.dry_run)
    except (install.InstallError, json.JSONDecodeError) as exc:
        print(f"stagegate: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
