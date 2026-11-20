# SPDX-License-Identifier: Apache-2.0
"""pytest network guard: fail any test that tries to reach a non-local host.

Part of stagegate-agents (opt-in). Tests must never call LLM APIs, GitHub, cloud
SDKs, email or webhooks for real: that costs money, burns rate limits and makes
tests flaky. Mock the client instead.

Enable it by copying this file next to your tests and adding to conftest.py:

    pytest_plugins = ["network_guard"]      # or: from network_guard import *  # noqa

Allowed: loopback, private-network IPs (docker-compose networks), dotless hostnames
(compose services such as "db"), and anything in NETWORK_GUARD_ALLOW (comma-separated
hostnames, e.g. "testserver,minio"). Everything else raises
OSError("NETWORK BLOCKED IN TESTS: <host> ...").

Because application code may catch that OSError and degrade gracefully (which would
hide the leak), every blocked attempt is also recorded and the autouse fixture FAILS
the test that made it.

Limitation: modules that did `from socket import getaddrinfo` before this guard was
installed keep the real function. Common clients (httpx, requests/urllib3, boto3,
asyncio, pymongo) look it up through the socket module, so they are covered.
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Iterator
from typing import Any

import pytest

_ALLOWED = {"localhost"} | {
    h.strip().lower() for h in os.environ.get("NETWORK_GUARD_ALLOW", "").split(",") if h.strip()
}
_BLOCKED: list[str] = []
_real_getaddrinfo = socket.getaddrinfo
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def is_allowed(host: object) -> bool:
    if host is None:
        return True  # AF_UNIX and similar
    if isinstance(host, bytes):
        host = host.decode(errors="replace")
    name = str(host).strip("[]").lower()
    if name in _ALLOWED:
        return True
    try:
        ip = ipaddress.ip_address(name)
    except ValueError:
        return "." not in name  # dotless: a compose service or a local alias
    return ip.is_loopback or ip.is_private or ip.is_unspecified


def _block(host: object) -> None:
    _BLOCKED.append(str(host))
    raise OSError(f"NETWORK BLOCKED IN TESTS: {host} — mock the client")


def _target(address: object) -> object:
    return address[0] if isinstance(address, tuple) and address else None


def _guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
    if not is_allowed(host):
        _block(host)
    return _real_getaddrinfo(host, *args, **kwargs)


def _guarded_connect(self: socket.socket, address: Any) -> Any:
    if not is_allowed(_target(address)):
        _block(_target(address))
    return _real_connect(self, address)


def _guarded_connect_ex(self: socket.socket, address: Any) -> Any:
    if not is_allowed(_target(address)):
        _block(_target(address))
    return _real_connect_ex(self, address)


socket.getaddrinfo = _guarded_getaddrinfo
socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
socket.socket.connect_ex = _guarded_connect_ex  # type: ignore[method-assign]


@pytest.fixture(autouse=True)
def _fail_on_blocked_network_calls() -> Iterator[None]:
    """Fail any test that attempted an outbound call, even if the code under test caught it."""
    _BLOCKED.clear()
    yield
    if _BLOCKED:
        hosts = sorted(set(_BLOCKED))
        _BLOCKED.clear()
        pytest.fail(
            f"NETWORK BLOCKED IN TESTS: tried to reach {hosts} — mock the client", pytrace=False
        )
