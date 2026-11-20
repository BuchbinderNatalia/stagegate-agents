# SPDX-License-Identifier: Apache-2.0
"""The opt-in network guard template blocks outside hosts and fails the test, offline."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SUITE = """
import socket
import urllib.request

def test_dns_to_outside_host_fails():
    socket.getaddrinfo("api.example.com", 443)

def test_swallowed_error_still_fails():
    try:
        urllib.request.urlopen("https://api.example.com/v1", timeout=1)
    except Exception:
        pass  # app code "degrading gracefully" must not hide the call

def test_public_ip_connect_fails():
    s = socket.socket()
    try:
        s.connect(("8.8.8.8", 53))
    finally:
        s.close()

def test_local_and_compose_hosts_allowed():
    socket.getaddrinfo("localhost", 80)
    from network_guard import is_allowed
    assert is_allowed("db") and is_allowed("10.1.2.3") and is_allowed("::1")
    assert is_allowed("minio.internal")  # via NETWORK_GUARD_ALLOW
    assert not is_allowed("pypi.org")
"""


def test_network_guard_template(tmp_path: Path) -> None:
    shutil.copy(ROOT / "templates/tests/network_guard.py", tmp_path)
    (tmp_path / "conftest.py").write_text('pytest_plugins = ["network_guard"]\n')
    (tmp_path / "test_suite.py").write_text(SUITE)
    p = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
            "-q",
            "-rA",
            str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
        env={
            "PATH": "/usr/bin:/bin",
            "NETWORK_GUARD_ALLOW": "minio.internal",
            "PYTHONPATH": str(tmp_path),
        },
    )
    out = p.stdout
    assert p.returncode != 0, out
    # Direct calls fail the test; the guard's teardown check reports blocked calls as an
    # ERROR even when the code under test swallowed the exception.
    assert "FAILED test_suite.py::test_dns_to_outside_host_fails" in out
    assert "FAILED test_suite.py::test_public_ip_connect_fails" in out
    assert "ERROR test_suite.py::test_swallowed_error_still_fails" in out
    assert "PASSED test_suite.py::test_local_and_compose_hosts_allowed" in out
    assert "ERROR test_suite.py::test_local_and_compose_hosts_allowed" not in out
