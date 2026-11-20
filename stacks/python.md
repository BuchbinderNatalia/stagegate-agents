<!-- SPDX-License-Identifier: Apache-2.0 -->
# Stack profile: Python

Installed as `.claude/stagegate/stack.md`. Every stagegate agent reads this file
for stack-specific patterns. Keep it short and concrete; project-specific rules
belong in CLAUDE.md.

## Structure
- Follow the package layout that already exists. Find 2–3 similar modules before adding a new one.
- Keep I/O (HTTP, DB, filesystem, external APIs) at the edges; keep logic in plain functions or
  service classes that are easy to unit-test.

## Patterns
- Type hints on every function signature, including the return type.
- Configuration and secrets come from one settings object or environment loader that already
  exists in the project. Never hardcode secrets, tokens or connection strings; never read
  `os.environ` ad hoc if a settings module exists.
- Errors: raise specific exceptions; never swallow exceptions silently. Log with context.
- Logging: use the project's logger (structured if the project uses structured logging). Never log
  secrets or full tokens.
- External services degrade gracefully: timeouts on every network call, a clear error or fallback
  when a provider is down or rate-limited.
- If the project is async, stay async end to end: no blocking calls inside `async def`.
- Dependencies: add only with the human's explicit approval, in the project's dependency file
  (pyproject.toml / requirements*.txt). Never `pip install` ad hoc.

## Tests
- pytest. Test files in the project's tests directory, named `test_<module>.py`.
- Reuse fixtures from `conftest.py` before writing new ones; never weaken an existing fixture.
- Every external client (HTTP APIs, LLM APIs, cloud SDKs, email) is mocked. Tests must not reach
  the network.
- For each new behaviour: success path, failure path (bad input / provider down), and the
  not-found or empty case.
- Never delete, skip or loosen an existing test to make a change pass.

## Review checklist
- [ ] Type hints and return types on new/changed functions
- [ ] No secrets, tokens or connection strings in code, config or tests
- [ ] Network calls have timeouts and handle failure
- [ ] No blocking I/O inside async code
- [ ] New behaviour has tests for success, failure and empty/not-found paths
- [ ] External services mocked in tests
- [ ] No new dependency without the human's approval
