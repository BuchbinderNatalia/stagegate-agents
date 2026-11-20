#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Print the first Python 3.11+ found (STAGEGATE_PYTHON wins), or fail with a fix.
stagegate_find_python() {
  local py
  for py in "${STAGEGATE_PYTHON:-}" python3 python3.14 python3.13 python3.12 python3.11; do
    [ -n "$py" ] || continue
    command -v "$py" >/dev/null 2>&1 || continue
    if "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
      printf '%s' "$py"
      return 0
    fi
  done
  echo "stagegate: Python 3.11+ is required (macOS: brew install python@3.12," \
    "Debian/Ubuntu: apt install python3.12), or set STAGEGATE_PYTHON." >&2
  return 1
}
