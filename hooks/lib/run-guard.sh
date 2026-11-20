#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Shared runner for stagegate guard hooks (Claude Code PreToolUse on Bash).
#
# Usage (from a guard wrapper): run_guard <guard name> <module.py> <<< "$input"
# Finds Python 3.11+ (tomllib), then runs hooks/lib/<module.py> with the hook
# JSON on stdin. Fails CLOSED: if the wrapper's fast path already matched (the
# command may be risky) and no suitable Python exists, the call is blocked with
# exit 2. Exit 1 would NOT block: Claude Code treats it as a non-blocking error.

stagegate_python() {
  local py
  for py in "${STAGEGATE_PYTHON:-}" python3 python3.14 python3.13 python3.12 python3.11; do
    [ -n "$py" ] || continue
    command -v "$py" >/dev/null 2>&1 || continue
    if "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
      printf '%s' "$py"
      return 0
    fi
  done
  return 1
}

run_guard() {
  local name=$1 module=$2 lib py
  lib=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
  if ! py=$(stagegate_python); then
    echo "BLOCKED by stagegate $name: Python 3.11+ not found, so this command cannot be checked." \
      "Install it (macOS: brew install python@3.12) or set STAGEGATE_PYTHON." >&2
    exit 2
  fi
  # -E: ignore PYTHON* env vars; -s: no user site-packages; -B: don't write
  # __pycache__ into the user's repository. The lib dir stays on sys.path so the
  # guard can import its sibling modules.
  exec "$py" -E -s -B "$lib/$module"
}
