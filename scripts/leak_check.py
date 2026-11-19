#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail if private identifiers leak into the repository.

Two layers:

1. Generic rules, committed here: AWS-account-like 12-digit numbers, email
   addresses outside an allowlist, and words that must never appear in this
   project (names of the private project the factory was extracted from).
2. A private denylist that is NEVER committed: literal strings (account IDs,
   bucket names, domains, personal emails) read from the LEAK_DENYLIST
   environment variable (CI secret, newline-separated) and/or an untracked
   `.leak-denylist` file (local, one entry per line, `#` comments allowed).

Findings name the file, line and rule. Denylist hits are reported as
"denylist entry #N", never by value, so CI logs don't leak what they protect.

Usage: leak_check.py [--root DIR] [FILE ...]   (no files = all git files)
Exit 0 = clean, 1 = findings, 2 = usage/setup error.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

# Built by concatenation so this file does not flag itself.
FORBIDDEN_WORDS = ["base" + "44", "star" + "pulse"]

ACCOUNT_ID = re.compile(r"(?<![\w.-])\d{12}(?![\w.-])")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ALLOWED_EMAIL_SUFFIXES = (
    "@example.com",
    "@example.org",
    "@example.net",
    "@users.noreply.github.com",
    "@anthropic.com",  # Co-Authored-By trailer documented in CONTRIBUTING
)
ALLOWED_EMAIL_EXACT = {"git@github.com"}  # SSH remote syntax, not an address

SKIP_SUFFIXES = {".png", ".gif", ".jpg", ".jpeg", ".ico", ".pdf", ".woff", ".woff2"}
SKIP_NAMES = {"LICENSE"}  # verbatim Apache text


def load_denylist(root: Path) -> list[str]:
    entries: list[str] = []
    raw = os.environ.get("LEAK_DENYLIST", "")
    path = root / ".leak-denylist"
    if path.is_file():
        raw += "\n" + path.read_text(encoding="utf-8")
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            entries.append(line.lower())
    return entries


def git_files(root: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout.decode()
    return [root / p for p in out.split("\0") if p]


def scan_text(text: str, denylist: list[str]) -> Iterable[tuple[int, str]]:
    for lineno, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        for word in FORBIDDEN_WORDS:
            if word in low:
                yield lineno, f"forbidden word ({word[:4]}…)"
        if ACCOUNT_ID.search(line):
            yield lineno, "12-digit number (looks like an AWS account ID)"
        for m in EMAIL.finditer(line):
            addr = m.group(0).lower()
            if addr in ALLOWED_EMAIL_EXACT or addr.endswith(ALLOWED_EMAIL_SUFFIXES):
                continue
            yield lineno, "email address outside the allowlist"
        for i, entry in enumerate(denylist, 1):
            if entry in low:
                yield lineno, f"denylist entry #{i}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", help="repository root (default: .)")
    ap.add_argument("files", nargs="*")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    try:
        files = [Path(f) for f in args.files] if args.files else git_files(root)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(f"leak_check: cannot list files: {exc}", file=sys.stderr)
        return 2

    denylist = load_denylist(root)
    findings = 0
    for path in files:
        if path.name in SKIP_NAMES or path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.name == ".leak-denylist" or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(root) if path.is_absolute() and root in path.parents else path
        for lineno, rule in scan_text(text, denylist):
            print(f"{rel}:{lineno}: {rule}")
            findings += 1

    if findings:
        print(
            f"leak_check: {findings} finding(s). Replace with placeholders "
            "(<AWS_ACCOUNT_ID>, you@example.com, app.example.com).",
            file=sys.stderr,
        )
        return 1
    if not denylist:
        print("leak_check: clean (generic rules only — no private denylist configured)")
    else:
        print(f"leak_check: clean (generic rules + {len(denylist)} private denylist entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
