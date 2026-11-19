<!-- SPDX-License-Identifier: Apache-2.0 -->
# Stack profile: Python + FastAPI

Installed as `.claude/stagegate/stack.md`. Includes everything in the plain Python
profile plus FastAPI conventions proven in production.

## Structure
- `routers/` — thin route handlers: validate input, call **one** service method, return the result.
  No business logic, no direct database access.
- `services/` — all business logic.
- `schemas/` — Pydantic v2 request/response models.
- `models/` — persistence models / collection access.
- Settings — one Pydantic `BaseSettings` class; everything reads `settings.X`.

## Patterns
- Type hints on every function signature, including the return type.
- Pydantic v2 only: `model_config = ConfigDict(...)`, `@field_validator`; never `class Config`
  or v1 `@validator`.
- If the app is async (async DB driver, async HTTP client), every route and service is `async def`
  and every I/O call is awaited. Never call a sync DB driver from async code.
- Auth: protected routes use the project's auth dependency (`Depends(...)`). Every write endpoint
  is protected unless the brief explicitly says public.
- Errors: raise `HTTPException` (or the project's error type) with the right status; error bodies
  are `{"detail": "message"}`.
- List endpoints: follow the project's existing list shape (e.g. `{"items": [...], "total": N}`);
  never mix shapes.
- Secrets via settings only; never hardcoded; never `os.getenv` scattered in modules.
- Outbound APIs: timeouts, check rate-limit headers where the provider sends them, degrade
  gracefully (partial results or a clear error, never an unhandled 500).
- Health/metrics endpoints must keep working after every change.

## Tests
- pytest (+ pytest-asyncio for async code); FastAPI `TestClient` or `httpx.AsyncClient`.
- Override auth with `app.dependency_overrides` in a fixture; clear overrides in teardown.
- Every new endpoint: success, 401/403 (auth), 404 (not found), validation error (422), and the
  empty-list case.
- Mock every external client. Integration tests may use a local database container only, in a
  throwaway database that is dropped in teardown; never a shared or remote database.

## Review checklist
- [ ] Business logic in services, not routers
- [ ] Pydantic v2 idioms only
- [ ] Async end to end where the app is async
- [ ] Write endpoints protected by the auth dependency
- [ ] Errors use the project's error shape and correct status codes
- [ ] List endpoints use the project's list shape
- [ ] Secrets via settings; nothing hardcoded
- [ ] Outbound calls have timeouts and graceful degradation
- [ ] Tests: success, auth failure, not-found, validation and empty cases; externals mocked
