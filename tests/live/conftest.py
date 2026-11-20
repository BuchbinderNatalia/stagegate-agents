# SPDX-License-Identifier: Apache-2.0
"""Live tests run the REAL Claude Code. Local only, opt-in, never in CI.

Run:  STAGEGATE_LIVE=1 pytest tests/live -s
Uses your logged-in Claude Code (subscription), no API key. Each run works in a
throwaway copy of examples/sample-app with a local bare remote, with Claude Code's
sandbox forced on (fail_if_unavailable), so nothing touches your real repos.
"""

from __future__ import annotations

import os
import shutil

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    reason = None
    if os.environ.get("STAGEGATE_LIVE") != "1":
        reason = "live tests are opt-in: STAGEGATE_LIVE=1 (local only, uses your Claude login)"
    elif os.environ.get("CI"):
        reason = "live tests never run in CI"
    elif not shutil.which("claude"):
        reason = "Claude Code (claude) not installed"
    for item in items:
        if "tests/live/" in str(item.fspath):
            item.add_marker(pytest.mark.live)
            if reason:
                item.add_marker(pytest.mark.skip(reason=reason))
