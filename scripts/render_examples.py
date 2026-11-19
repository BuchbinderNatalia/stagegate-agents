#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Render the shipped workflow templates into OUTDIR so linters can check them.

Usage: render_examples.py OUTDIR
Writes OUTDIR/<variant>/.github/workflows/stagegate-deploy.yml for each variant.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "hooks" / "lib")]
import config  # noqa: E402
import render  # noqa: E402

VARIANTS = {
    "argocd": {
        "infra": {"enabled": True, "cluster": "demo", "registry": "registry.example.com/app"}
    },
    "kubectl": {"infra": {"enabled": True, "gitops": "none", "secrets": "none"}},
}


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    out = Path(argv[0])
    for name, overrides in VARIANTS.items():
        cfg = config._merge(config.DEFAULTS, overrides)
        files = render.collect(cfg, out / name / "demo-app", packs=("core", "infra"))
        for rel, content in files.items():
            if rel.startswith(".github/"):
                path = out / name / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
                print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
