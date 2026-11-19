#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# stagegate commit guard: blocks `git commit` of secrets/state files, ':latest'
# image tags and configured forbidden patterns, and (by default) commits on or
# pushes to the default branch.
# Logic: hooks/lib/commit_guard.py. Tests: tests/unit/hooks/test_commit_guard.py
input=$(cat)
# Fast path: skip Python unless "commit" or "push" appears at all.
case "$input" in *commit*|*push*) ;; *) exit 0 ;; esac
# shellcheck source=lib/run-guard.sh
. "$(dirname "${BASH_SOURCE[0]}")/lib/run-guard.sh"
run_guard "commit guard" commit_guard.py <<<"$input"
