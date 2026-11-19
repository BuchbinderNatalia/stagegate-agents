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
    "project": {"name": "", "description": "", "default_branch": "main"},
    "stack": {
        "language": "python",
        # Agent guidance profile: stacks/<profile>.md (python, python-fastapi, react-ts, ...)
        "profile": "python",
        "backend_dir": ".",
        "frontend_dir": "",  # empty = no frontend; frontend agents are not installed
        "tests_dir": "tests",
        "test_command": "pytest -q",
        "lint_command": "ruff check .",
        # Prefix for running commands in a container, e.g. "docker compose run --rm app"
        "run_prefix": "",
    },
    "git": {"branch_prefix": "feat/", "commit_style": "per-step"},
    "review": {"require_green_ci": True},
    # Model aliases track the current model versions; a full model ID pins one.
    "models": {"fast": "haiku", "default": "sonnet"},
    "sandbox": {
        "enabled": True,
        # true = Claude Code refuses to run if the sandbox can't start (evals force this).
        "fail_if_unavailable": False,
        "allowed_domains": [
            "github.com",
            "api.github.com",
            "codeload.github.com",
            "objects.githubusercontent.com",
            "pypi.org",
            "files.pythonhosted.org",
        ],
        "deny_read": [
            "~/.aws",
            "~/.ssh",
            "~/.kube",
            "~/.config/gh",
            "~/.config/gcloud",
            "~/.azure",
            "~/.docker/config.json",
            "~/.netrc",
            "~/.npmrc",
            "~/.pypirc",
        ],
        # Run outside the sandbox (still with permission prompts): they need your
        # git/GitHub credentials. `gh pr merge` stays behind the merge gate.
        "excluded_commands": ["git fetch *", "git pull *", "git push *", "gh pr *"],
    },
    "infra": {
        "enabled": False,
        "cloud": "aws",
        "region": "us-east-1",
        "cluster": "",
        "registry": "",
        "iac_dir": "terraform",
        "k8s_dir": "k8s",
        "gitops": "argocd",
        "secrets": "vault",
        "tf_state_bucket": "",
        "tf_lock_table": "",
        "app_name": "",  # Kubernetes deployment / ArgoCD app name; defaults to project.name
        "namespace": "",  # app namespace; defaults to project.name
        "health_path": "/health",
        "app_port": "8000",
        "environment": "production",  # GitHub environment that gates deploys (required reviewers)
        # Name of the GitHub Actions secret holding the IAM role ARN CI assumes via OIDC.
        "deploy_role_secret": "AWS_DEPLOY_ROLE_ARN",
        # Mentor mode: infra agents end with "Learning notes" (why, risks, what seniors check).
        "learning_notes": False,
    },
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


def validate(
    cfg: dict[str, Any], defaults: dict[str, Any] | None = None, path: str = ""
) -> list[str]:
    """Return human-readable problems: unknown keys and values of the wrong type."""
    defaults = DEFAULTS if defaults is None else defaults
    problems: list[str] = []
    for key, value in cfg.items():
        where = f"{path}{key}"
        if key not in defaults:
            problems.append(f"unknown key: {where}")
            continue
        expected = defaults[key]
        if isinstance(expected, dict):
            if not isinstance(value, dict):
                problems.append(f"{where} must be a table")
            else:
                problems.extend(validate(value, expected, f"{where}."))
        elif isinstance(expected, bool):
            if not isinstance(value, bool):
                problems.append(f"{where} must be true or false")
        elif isinstance(expected, list):
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                problems.append(f"{where} must be a list of strings")
        elif isinstance(expected, str) and not isinstance(value, str):
            problems.append(f"{where} must be a string")
    return problems
