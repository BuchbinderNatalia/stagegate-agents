# SPDX-License-Identifier: Apache-2.0
"""Unit tests for scripts/check_spdx.py."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_spdx", ROOT / "scripts" / "check_spdx.py")
check_spdx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_spdx)


def test_header_present(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("#!/usr/bin/env python3\n# SPDX-License-Identifier: Apache-2.0\n")
    assert check_spdx.main([str(f)]) == 0


def test_header_after_frontmatter(tmp_path: Path) -> None:
    f = tmp_path / "agent.md.tmpl"
    f.write_text("---\nname: x\n---\n<!-- SPDX-License-Identifier: Apache-2.0 -->\n")
    assert check_spdx.main([str(f)]) == 0


def test_header_missing(tmp_path: Path) -> None:
    f = tmp_path / "b.sh"
    f.write_text("#!/usr/bin/env bash\necho hi\n")
    assert check_spdx.main([str(f)]) == 1


def test_unchecked_types_ignored(tmp_path: Path) -> None:
    f = tmp_path / "README.md"
    f.write_text("# no header needed\n")
    assert check_spdx.main([str(f)]) == 0
