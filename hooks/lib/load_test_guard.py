# SPDX-License-Identifier: Apache-2.0
"""Load-test guard: load tools may only target local hosts.

Blocks a command when a load tool (k6, artillery, locust, wrk, hey, ab, ...) is
actually run, directly, through wrappers, inside sh -c / eval, or as the image
or service of `docker run` / `docker compose run`, AND it targets a non-local
host, either in the command (URLs, BASE_URL=..., TARGET=...) or inside a
script file the command references.

Local means: configured `guards.local_hosts`, any dotless hostname (a compose
service such as "backend"), and loopback/private/unspecified IPs.
`guards.forbidden_hosts` are blocked whenever mentioned in a load-tool run.

There is deliberately no override flag an agent could add itself. If a human
wants a remote load test, they run it themselves.
"""

from __future__ import annotations

import importlib
import ipaddress
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Sibling modules, loaded after the path is set (no import-order suppressions needed,
# so the installed code passes users' own linters).
config = importlib.import_module("config")
hookio = importlib.import_module("hookio")
shellwords = importlib.import_module("shellwords")

GUARD = "load-test guard"
CONTAINER_TOOLS = {"docker", "podman", "docker-compose", "nerdctl"}
URL = re.compile(r"(?:https?|wss?)://([^/\s:\"'`]+)", re.IGNORECASE)
TARGET_VAR = re.compile(
    r"\b(?:BASE_URL|TARGET|TARGET_URL|API_URL|HOST)\s*=\s*[\"']?([^\s\"']+)", re.IGNORECASE
)
SCRIPT = re.compile(r"[\w./-]+\.(?:js|ts|mjs|py|ya?ml|json)\b")


def is_local(host: str, local_hosts: set[str]) -> bool:
    host = host.strip("[]").lower()
    if not host or host.startswith("$") or host in local_hosts:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host  # dotless = docker-compose service / bare hostname
    return ip.is_loopback or ip.is_private or ip.is_unspecified


def remote_hosts(text: str, local_hosts: set[str], forbidden: list[str]) -> set[str]:
    found = {h.lower() for h in URL.findall(text) if not is_local(h, local_hosts)}
    for value in TARGET_VAR.findall(text):
        m = URL.match(value)
        host = m.group(1) if m else value.split("/")[0].split(":")[0]
        if not is_local(host, local_hosts):
            found.add(host.lower())
    low = text.lower()
    found |= {f.lower() for f in forbidden if f and f.lower() in low}
    return found


def runs_load_tool(argv: list[str], tools: set[str]) -> bool:
    prog = shellwords.program(argv)
    if prog in tools:
        return True
    if prog in CONTAINER_TOOLS:
        # docker run ... grafana/k6[:tag] ...  /  docker compose run ... k6 ...
        return any(a.split(":")[0].split("/")[-1] in tools for a in argv[1:])
    return False


def main() -> None:
    command, cwd = hookio.read_payload()
    try:
        cfg = config.load(config.project_root(cwd))
    except config.ConfigError as exc:
        cfg = None
        error = str(exc)
    tools = set((cfg or config.DEFAULTS)["guards"]["load_tools"])
    hits = [a for a in shellwords.commands(command) if runs_load_tool(a, tools)]
    if not hits:
        hookio.allow()
    if cfg is None:
        hookio.block(GUARD, [error, "Cannot verify the load test targets a local host."])

    guards = cfg["guards"]
    local = {h.lower() for h in guards["local_hosts"]}
    forbidden = list(guards["forbidden_hosts"])
    base = Path(cwd) if cwd else Path.cwd()

    bad: set[str] = set()
    for argv in hits:
        joined = " ".join(argv)
        bad |= remote_hosts(joined, local, forbidden)
        for script in SCRIPT.findall(joined):
            path = Path(script) if Path(script).is_absolute() else base / script
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            bad |= {f"{h} (in {script})" for h in remote_hosts(content, local, forbidden)}
    # A target set earlier in the same command: `export BASE_URL=... && k6 run x.js`.
    active = shellwords.strip_heredocs(command)
    set_vars = " ".join(m.group(0) for m in TARGET_VAR.finditer(active))
    bad |= remote_hosts(set_vars, local, forbidden)

    if bad:
        hookio.block(
            GUARD,
            [
                "load tests run against local hosts only. Remote target(s): "
                + ", ".join(sorted(bad))
                + ".",
                (
                    "Point the test at a local stack (e.g. BASE_URL=http://localhost:8000 or a "
                    "docker-compose service name). A remote load test needs a human to run it."
                ),
            ],
        )
    hookio.allow()


if __name__ == "__main__":
    main()
