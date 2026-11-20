# SPDX-License-Identifier: Apache-2.0
"""Claude Code PreToolUse hook I/O helpers.

Contract (https://code.claude.com/docs/en/hooks): the hook gets JSON on stdin
with `tool_input.command` and `cwd`; exit 0 = no objection, exit 2 = block,
and stderr is shown to Claude as the reason. Any other exit code is a
NON-blocking error, so guards must never use `exit 1` to enforce a policy.
"""

from __future__ import annotations

import json
import sys
from typing import NoReturn

ALLOW = 0
BLOCK = 2


def read_payload() -> tuple[str, str | None]:
    """Return (command, cwd) from the hook JSON; ('', None) if unreadable."""
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "", None
    if not isinstance(data, dict):
        return "", None
    tool_input = data.get("tool_input") or {}
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    cwd = data.get("cwd")
    return (command if isinstance(command, str) else ""), (cwd if isinstance(cwd, str) else None)


def block(guard: str, lines: list[str]) -> NoReturn:
    sys.stderr.write(f"BLOCKED by stagegate {guard}: " + "\n".join(lines) + "\n")
    sys.exit(BLOCK)


def allow() -> NoReturn:
    sys.exit(ALLOW)
