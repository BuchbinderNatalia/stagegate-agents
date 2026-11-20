# SPDX-License-Identifier: Apache-2.0
"""Load-test guard regression suite (ported from production, plus new cases).

"api.prod.example.com" stands in for a real production host. No network,
no Docker: the guard only parses the command and referenced script files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

PROD = "https://api.prod.example.com"

ALLOW = [
    "ls -la",
    "git commit -m 'add k6 scenario for prod later'",  # mention, not a run
    "echo hey there",
    "docker run --rm -i grafana/k6 run - < load/library.js",
    "docker compose run --rm -e BASE_URL=http://backend:8000 k6 run /load/library.js",
    "k6 run -e BASE_URL=http://localhost:8000 load/x.js",
    "k6 run -e BASE_URL=http://host.docker.internal:8000 load/x.js",
    "k6 run -e BASE_URL=http://10.0.0.12:8000 load/x.js",  # private IP
    "k6 run load/local.js",  # script targets a compose service
    f"grep -n k6 NOTES.md && echo {PROD}",
    f"python3 - <<'EOF'\ns = 'k6 run -e BASE_URL={PROD}'\nEOF",
    f"cat > notes.md <<EOF\nk6 run against {PROD} is forbidden\nEOF",
    f"git commit -m 'docs: k6 never against {PROD}'",
    "k6 run -e BASE_URL=$TARGET_FROM_ENV load/x.js",  # unresolved variable: not judged
]
BLOCK = [
    f"k6 run -e BASE_URL={PROD} load/x.js",
    f"BASE_URL={PROD} k6 run load/x.js",
    "docker run --rm grafana/k6 run -e BASE_URL=https://example.com script.js",
    "k6 run load/prod.js",  # remote host inside the referenced script
    "docker run --rm -v $PWD/load:/load grafana/k6 run /load/x.js -e TARGET=prod.example.com",
    f"hey -n 1000 {PROD}/",
    f"ab -n 1000 -c 50 {PROD}/ready",
    f"wrk -t4 -c100 {PROD}/health",
    f"artillery quick --count 50 {PROD}/ready",
    f"bash -c 'k6 run -e BASE_URL={PROD} x.js'",
    f"export BASE_URL={PROD} && k6 run load/x.js",
    f"sudo env BASE_URL={PROD} /usr/local/bin/k6 run x.js",
    f"docker run --rm grafana/k6:0.54.0 run -e BASE_URL={PROD} /s.js",
    f"docker compose run --rm k6 run -e BASE_URL={PROD} /load/x.js",
    f'eval "k6 run -e BASE_URL={PROD} x.js"',
    f"timeout 60 k6 run -e BASE_URL={PROD} x.js",
    "k6 run -e BASE_URL=http://8.8.8.8 x.js",  # public IP
]


@pytest.fixture(autouse=True)
def scripts(project: Path) -> None:
    (project / "load").mkdir()
    (project / "load" / "prod.js").write_text(
        f"export default function () {{ http.get('{PROD}/ready'); }}"
    )
    (project / "load" / "local.js").write_text(
        "const BASE = __ENV.BASE_URL || 'http://backend:8000';"
    )


@pytest.mark.parametrize("command", ALLOW)
def test_allows(run_hook, command: str) -> None:
    result = run_hook("load-test-guard.sh", command)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("command", BLOCK)
def test_blocks(run_hook, command: str) -> None:
    result = run_hook("load-test-guard.sh", command)
    assert result.returncode == 2, f"expected block: {result.stderr}"
    assert "BLOCKED by stagegate load-test guard" in result.stderr


def test_forbidden_host_without_scheme(run_hook, project: Path) -> None:
    (project / "stagegate.toml").write_text('[guards]\nforbidden_hosts = ["shop.internal"]\n')
    result = run_hook("load-test-guard.sh", "k6 run -e SITE=shop.internal x.js")
    assert result.returncode == 2 and "shop.internal" in result.stderr


def test_extra_local_host_allowed(run_hook, project: Path) -> None:
    (project / "stagegate.toml").write_text(
        '[guards]\nlocal_hosts = ["localhost", "staging.lan.example"]\n'
    )
    assert (
        run_hook(
            "load-test-guard.sh", "k6 run -e BASE_URL=http://staging.lan.example x.js"
        ).returncode
        == 0
    )


def test_custom_load_tool_from_config(run_hook, project: Path) -> None:
    (project / "stagegate.toml").write_text('[guards]\nload_tools = ["gatling"]\n')
    result = run_hook("load-test-guard.sh", f"gatling -s Sim -e BASE_URL={PROD}")
    assert result.returncode == 2
