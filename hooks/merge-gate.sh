#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# stagegate merge gate: blocks `gh pr merge` unless every CI check on the PR is
# green. Logic: hooks/lib/merge_gate.py. Tests: tests/unit/hooks/test_merge_gate.py
input=$(cat)
# Fast path: runs on every Bash call; skip Python unless "merge" appears at all.
case "$input" in *merge*) ;; *) exit 0 ;; esac
# shellcheck source=lib/run-guard.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/run-guard.sh"
run_guard "merge gate" merge_gate.py <<<"$input"
