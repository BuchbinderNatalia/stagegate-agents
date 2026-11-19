# SPDX-License-Identifier: Apache-2.0
"""Load stagegate.toml (standard library only, Python 3.11+).

The project root is $CLAUDE_PROJECT_DIR (set by Claude Code for hooks), else
the git top-level of the current directory, else the current directory.
Values in stagegate.toml are deep-merged over DEFAULTS, so a minimal file (or
none at all) still yields a complete configuration.
"""

from __future__ import annotations

import copy
import os
import subprocess
import tomllib
from pathlib import Path
from typing import Any

CONFIG_NAME = "stagegate.toml"

DEFAULTS: dict[str, Any] = {
    "project": {"name": "", "default_branch": "main"},
    "review": {"require_green_ci": True},
    "guards": {
        # Load tests may only target these hosts. Dotless names (docker-compose
        # services such as "backend") and private/loopback IPs are always local.
        "local_hosts": ["localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal"],  # noqa: S104 — target hosts, not a bind
        # Hosts that must never be load-tested, even when written without a scheme.
        "forbidden_hosts": [],
        "load_tools": [
            "k6",
            "artillery",
            "locust",
            "vegeta",
            "wrk",
            "autocannon",
            "jmeter",
            "hey",
            "ab",
            "oha",
            "bombardier",
            "siege",
        ],
        "blocked_files": [
            "*.tfstate",
            "*.tfstate.backup",
            "*.tfvars",
            "*.pem",
            "*.key",
            "*.p12",
            ".env",
            ".env.*",
            "secrets.yaml",
            "secrets.json",
            ".venv/*",
            "id_rsa*",
            "*.leak-denylist",
        ],
        "allowed_files": [".env.example", "*.tfvars.example"],
        "block_latest_tag": True,
        # Regexes that must not appear in added lines (e.g. a banned import).
        "forbidden_patterns": [],
    },
}


class ConfigError(Exception):
    """stagegate.toml exists but cannot be read; guards fail closed on it."""


def project_root(cwd: str | os.PathLike[str] | None = None) -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    start = Path(cwd or os.getcwd())
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
        if top:
            return Path(top)
    except (OSError, subprocess.SubprocessError):
        pass
    return start


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(root: Path | None = None) -> dict[str, Any]:
    root = root or project_root()
    path = root / CONFIG_NAME
    if not path.is_file():
        return copy.deepcopy(DEFAULTS)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    return _merge(DEFAULTS, data)
