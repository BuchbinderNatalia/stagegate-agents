#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Require an SPDX license header near the top of every source file.

Checks .py, .sh, .yml, .yaml, .toml and .tmpl files. The identifier must appear
in the first 25 lines (agent templates carry YAML frontmatter first, then an
HTML comment with the identifier).

Usage: check_spdx.py FILE ...   (no files = all git-tracked files)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HEADER = "SPDX-License-Identifier: Apache-2.0"
CHECKED = {".py", ".sh", ".yml", ".yaml", ".toml", ".tmpl"}
HEAD_LINES = 25


def needs_header(path: Path) -> bool:
    return path.suffix in CHECKED and path.is_file()


def has_header(path: Path) -> bool:
    with path.open(encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i >= HEAD_LINES:
                return False
            if HEADER in line:
                return True
    return False


def main(argv: list[str]) -> int:
    if argv:
        files = [Path(a) for a in argv]
    else:
        out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
        files = [Path(p) for p in out.decode().split("\0") if p]
    missing = [f for f in files if needs_header(f) and not has_header(f)]
    for f in missing:
        print(f"{f}: missing '{HEADER}' in the first {HEAD_LINES} lines")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
