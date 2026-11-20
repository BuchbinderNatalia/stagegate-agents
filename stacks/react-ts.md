<!-- SPDX-License-Identifier: Apache-2.0 -->
# Stack profile: React + TypeScript (frontend)

Append to the backend profile when the project has a frontend (`stack.frontend_dir`).
Installed as part of `.claude/stagegate/stack.md`.

## Structure
- One API client module (e.g. `src/lib/api.ts`). Components never call `fetch` directly.
- Auth/session context is read, never modified, by feature work.
- Pages compose components; components stay presentational where possible.

## Patterns
- TypeScript for new files: `.tsx` for components, `.ts` for utilities.
- Environment variables through the bundler's mechanism (Vite: `import.meta.env.VITE_*`), never
  `process.env` in browser code. Never put secrets in frontend env vars: they ship to the browser.
- Every data fetch handles **loading**, **error** and **empty** states.
- Use the data-fetching library and UI components the project already has; don't add another.
- Consume the API exactly as the backend documents it. If the contract is wrong, report it; don't
  patch around it in the UI.

## Tests
- Vitest (or the project's runner) + Testing Library: query by role/label, assert what the user sees.
- Mock the API client module and auth context; tests never call a real backend.
- Each new component: renders with data, loading state, error state, empty state.
- E2E (Playwright) only against a local stack; load tests only against local hosts.

## Review checklist
- [ ] API calls only through the API client module
- [ ] Loading, error and empty states on every fetch
- [ ] No secrets in frontend env vars; no `process.env` in browser code
- [ ] Auth context not modified by feature work
- [ ] Production build would pass (no type errors in the diff)
- [ ] Component tests cover data, loading, error and empty states
