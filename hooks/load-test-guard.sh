#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# stagegate load-test guard: load tools may only target local hosts.
# Logic: hooks/lib/load_test_guard.py. Tests: tests/unit/hooks/test_load_test_guard.py
input=$(cat)
# Fast path: skip Python unless a default load-tool name appears. A project that
# adds its own tools in stagegate.toml (guards.load_tools) always takes the slow path.
root=${CLAUDE_PROJECT_DIR:-.}
if ! grep -qs 'load_tools' "$root/stagegate.toml"; then
  case "$input" in
    *k6*|*artillery*|*locust*|*vegeta*|*wrk*|*autocannon*|*jmeter*|*hey*|*ab\ *|*oha*|*bombardier*|*siege*) ;;
    *) exit 0 ;;
  esac
fi
# shellcheck source=lib/run-guard.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/run-guard.sh"
run_guard "load-test guard" load_test_guard.py <<<"$input"
