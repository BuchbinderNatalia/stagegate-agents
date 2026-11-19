#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Render stagegate templates and generate .claude/settings.json.

Standard library only (Python 3.11+). Used by scripts/install.sh.

Template syntax (deliberately tiny, strict):
  {{ stack.test_command }}        value (lists join with ", ", booleans as true/false)
  {{ guards.local_hosts | json }} JSON encoding
  {{ sandbox.deny_read | bullets }} one "- item" line per list entry
  {{#if stack.frontend_dir}} ... {{else}} ... {{/if}}   truthiness; nestable
  {{#unless infra.enabled}} ... {{/unless}}
An unknown key, an unknown filter, an unclosed block or any leftover "{{"
is an error: a half-rendered agent prompt must never be installed.
GitHub Actions expressions (`${{ github.sha }}`) pass through untouched.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks" / "lib"))
import config  # noqa: E402

# `${{ ... }}` (GitHub Actions expressions) is literal text, never a template tag.
TAG = re.compile(r"(?<!\$)\{\{\s*(.*?)\s*\}\}", re.DOTALL)
GHA_EXPR = re.compile(r"\$\{\{.*?\}\}", re.DOTALL)
HOOK_DIR = ".claude/hooks/stagegate"
HOOKS = ("commit-guard.sh", "merge-gate.sh", "load-test-guard.sh")
MANIFEST = ".claude/stagegate.manifest.json"
CLAUDE_MD_BEGIN = "<!-- stagegate:begin -->"
CLAUDE_MD_END = "<!-- stagegate:end -->"


class TemplateError(Exception):
    pass


# --------------------------------------------------------------------------- engine
def lookup(ctx: dict[str, Any], dotted: str) -> Any:
    cur: Any = ctx
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise TemplateError(f"unknown key: {dotted}")
        cur = cur[part]
    return cur


def _fmt(value: Any, filt: str | None, expr: str) -> str:
    if filt is None:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, list):
            return ", ".join(str(v) for v in value)
        return str(value)
    if filt == "json":
        return json.dumps(value)
    if filt == "bullets":
        items = value if isinstance(value, list) else [value]
        return "\n".join(f"- {v}" for v in items)
    raise TemplateError(f"unknown filter '{filt}' in {{{{ {expr} }}}}")


def render(text: str, ctx: dict[str, Any], name: str = "<template>") -> str:
    """Render `text`; raise TemplateError with the template name on any problem."""
    out: list[str] = []
    # Stack of (block kind, condition, in_else). Text is emitted only when every
    # enclosing block is active.
    stack: list[tuple[str, bool, bool]] = []

    def active() -> bool:
        return all(cond != in_else for _, cond, in_else in stack)

    pos = 0
    try:
        for m in TAG.finditer(text):
            if active():
                out.append(text[pos : m.start()])
            pos = m.end()
            expr = m.group(1)
            if expr.startswith("#if ") or expr.startswith("#unless "):
                kind, key = expr[1:].split(None, 1)
                cond = bool(lookup(ctx, key.strip()))
                stack.append((kind, cond if kind == "if" else not cond, False))
            elif expr == "else":
                if not stack or stack[-1][2]:
                    raise TemplateError("{{else}} without an open {{#if}}")
                kind, cond, _ = stack.pop()
                stack.append((kind, cond, True))
            elif expr in ("/if", "/unless"):
                if not stack or stack[-1][0] != expr[1:]:
                    raise TemplateError(f"unexpected {{{{{expr}}}}}")
                stack.pop()
            else:
                key, _, filt = (p.strip() for p in expr.partition("|"))
                value = lookup(ctx, key)
                if active():
                    out.append(_fmt(value, filt or None, expr))
        if stack:
            raise TemplateError(f"unclosed {{{{#{stack[-1][0]}}}}} block")
        if active():
            out.append(text[pos:])
    except TemplateError as exc:
        raise TemplateError(f"{name}: {exc}") from None

    result = "".join(out)
    plain = GHA_EXPR.sub("", result)
    if "{{" in plain or "}}" in plain:
        raise TemplateError(f"{name}: leftover template braces after rendering")
    return result


def context(cfg: dict[str, Any], target: Path) -> dict[str, Any]:
    ctx = copy.deepcopy(cfg)
    if not ctx["project"]["name"]:
        ctx["project"]["name"] = target.resolve().name
    return ctx


# --------------------------------------------------------------------------- settings.json
def hook_entries() -> list[dict[str, Any]]:
    return [
        {"type": "command", "command": f'"$CLAUDE_PROJECT_DIR"/{HOOK_DIR}/{hook}', "timeout": 60}
        for hook in HOOKS
    ]


def merge_settings(existing: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    """Add stagegate hooks and sandbox settings without dropping anything the user has."""
    settings = copy.deepcopy(existing)
    pre = settings.setdefault("hooks", {}).setdefault("PreToolUse", [])
    bash = next((g for g in pre if g.get("matcher") == "Bash"), None)
    if bash is None:
        bash = {"matcher": "Bash", "hooks": []}
        pre.append(bash)
    have = {h.get("command") for h in bash.setdefault("hooks", [])}
    bash["hooks"].extend(h for h in hook_entries() if h["command"] not in have)

    sb = cfg["sandbox"]
    sandbox = settings.setdefault("sandbox", {})
    sandbox["enabled"] = sb["enabled"]
    if sb["enabled"]:
        sandbox["failIfUnavailable"] = sb["fail_if_unavailable"]
        fs = sandbox.setdefault("filesystem", {})
        fs["denyRead"] = sorted(set(fs.get("denyRead", [])) | set(sb["deny_read"]))
        net = sandbox.setdefault("network", {})
        net["allowedDomains"] = sorted(
            set(net.get("allowedDomains", [])) | set(sb["allowed_domains"])
        )
        excl = sandbox.get("excludedCommands", [])
        sandbox["excludedCommands"] = excl + [c for c in sb["excluded_commands"] if c not in excl]
    return settings


def remove_from_settings(existing: dict[str, Any]) -> dict[str, Any]:
    """Inverse of merge_settings for uninstall: drop only stagegate's hook entries."""
    settings = copy.deepcopy(existing)
    ours = {h["command"] for h in hook_entries()}
    for group in settings.get("hooks", {}).get("PreToolUse", []):
        group["hooks"] = [h for h in group.get("hooks", []) if h.get("command") not in ours]
    pre = settings.get("hooks", {}).get("PreToolUse")
    if pre is not None:
        settings["hooks"]["PreToolUse"] = [g for g in pre if g.get("hooks")]
    return settings


# --------------------------------------------------------------------------- CLAUDE.md
SPDX_COMMENT = re.compile(r"^<!-- SPDX-License-Identifier: [^>]* -->\n?", re.MULTILINE)


def merge_claude_md(existing: str | None, section: str) -> str:
    """Insert or replace the stagegate section between markers; keep everything else.

    The template's SPDX comment is dropped: CLAUDE.md is the user's file.
    """
    section = SPDX_COMMENT.sub("", section)
    block = f"{CLAUDE_MD_BEGIN}\n{section.strip()}\n{CLAUDE_MD_END}\n"
    if not existing:
        return block
    if CLAUDE_MD_BEGIN in existing and CLAUDE_MD_END in existing:
        head, _, rest = existing.partition(CLAUDE_MD_BEGIN)
        _, _, tail = rest.partition(CLAUDE_MD_END)
        return head + block.rstrip("\n") + tail
    return existing.rstrip("\n") + "\n\n" + block


# --------------------------------------------------------------------------- writing
def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def write_files(
    files: dict[str, str], target: Path, force: bool = False, dry_run: bool = False
) -> dict[str, list[str]]:
    """Write rendered files, never clobbering a file the user changed since last install.

    The manifest records the hash of what stagegate last wrote. A file whose
    current content matches neither that hash nor the new content was edited by
    the user and is skipped unless force=True.
    """
    manifest_path = target / MANIFEST
    try:
        manifest: dict[str, str] = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        manifest = {}
    report: dict[str, list[str]] = {"created": [], "updated": [], "unchanged": [], "skipped": []}

    for rel, content in sorted(files.items()):
        path = target / rel
        new_hash = sha(content)
        if path.exists():
            current = sha(path.read_text(encoding="utf-8", errors="replace"))
            if current == new_hash:
                report["unchanged"].append(rel)
                manifest[rel] = new_hash
                continue
            if current != manifest.get(rel) and not force:
                report["skipped"].append(rel)  # user-modified
                continue
            report["updated"].append(rel)
        else:
            report["created"].append(rel)
        manifest[rel] = new_hash
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    if not dry_run:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return report


# --------------------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Render one stagegate template to stdout.")
    ap.add_argument("template", type=Path)
    ap.add_argument("--target", type=Path, default=Path("."), help="project root (for config)")
    args = ap.parse_args(argv)
    try:
        cfg = config.load(args.target.resolve())
        problems = config.validate(cfg)
        if problems:
            print("stagegate.toml problems:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 2
        text = args.template.read_text(encoding="utf-8")
        sys.stdout.write(render(text, context(cfg, args.target), str(args.template)))
    except (config.ConfigError, TemplateError, OSError) as exc:
        print(f"render: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
