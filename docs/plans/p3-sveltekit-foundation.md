# P3: SvelteKit foundation

Part of `floppy-v2.md`. Started 2026-11-17.

## Goal

The new web app exists and ships in the container, so P4 can build screens
on it: `web/` (SvelteKit 3, adapter-node) served under `/next/`, signed in
through Django's session, calling Django's documented API through a typed
client, with the CineTrack look, a service worker and CI gates.

## Slices

| Slice | Content | Status |
|---|---|---|
| P3-A | Container shell: `web/` scaffold, the Node server in the image under supervisord, nginx `/next/`, CI (types, unit and component tests, build, e2e) | Built; CI and beta check pending |
| P3-B | Session bridge (board item "v2 P3 session bridge", decided 2026-11-15 in P1-G): DRF session auth with CSRF on `/api/`, allauth headless (browser client) for sign-in, the recovery-code password reset; typed API client | Not started |
| P3-C | Design tokens, base components, app shell | Not started |
| P3-D | Service worker, new-version detection, bundle and response-time budgets | Not started |

### P3-A: container shell (2026-11-17)

- `web/` made with `sv create` (SvelteKit 3.2, Svelte 5.57, Vite 8,
  adapter-node 6, Tailwind 4, Vitest 4 with browser component tests,
  Playwright). TypeScript stays on 6.x: Kit 3.2 does not accept 7 yet.
  `paths.base` is `/next`.
- `/next/health` answers `{"status": "ok"}` for the smoke test.
- **Image:** a `web_builder` stage builds with Alpine's own `nodejs`/`npm`
  (the same Node 24 the runtime gets with `apk add nodejs`). The
  adapter-node output is self-contained: the runtime copies only
  `web/build` and `web/package.json` (which marks it as ES modules), no
  `node_modules`.
- **supervisord** program `web`: `node /floppy/web/build` on 127.0.0.1:8002
  only, because it trusts the forwarded headers (`PROTOCOL_HEADER`,
  `HOST_HEADER`, `ADDRESS_HEADER`) that nginx sets. Runs as `abc`.
- **Start switch:** `FLOPPY_START_WEB`, set by `entrypoint.sh`: on for beta
  servers (`FLOPPY_BETA_MODE`), off elsewhere until there are screens to
  use; an explicit value wins. Node's memory on the minimal tier is still to
  be measured (the smoke test prints the RSS).
- **nginx:** `location = /next` and `location /next/` go to the Node server
  unchanged (SvelteKit itself redirects `/next` to `/next/`, so nginx adds no
  redirect). `X-Forwarded-Proto` is always sent (the tunnel's, else the
  connection's scheme): without it the Node server assumes https and refuses
  same-origin form posts over plain http with 403 (checked locally).
- The Django service worker leaves `/next/` alone; the new app will bring its
  own (P3-D).
- **CI:** a `web` job in "CineTrack API Targeted Tests" (svelte-check, unit
  and component tests in Chromium, build, Playwright against the built
  server), so beta only deploys a commit whose web app passed. The Docker
  smoke test starts the web program and checks `/next/health`, the `/next`
  redirect, the page and that a plain-http form post is not refused.

### Notes for the next slices

- **P3-B auth bridge:** `handleFetch` sends the user's cookie only to
  Django on 127.0.0.1:8001, never to other hosts, and forwards `Host`,
  `X-Forwarded-Proto` and `X-Real-IP` (allauth refuses requests without the
  client IP header in production, and Django builds absolute image URLs
  from the host). CSRF for writes. Server-side calls count against the ASGI
  request cap (`GUNICORN_THREADS` per worker).
- **Login and signup:** decided in P1-G (2026-11-15): allauth headless with
  the browser client only, keeping the Django pages; the authenticator code
  is used only for recovery, not at sign-in. Session auth with CSRF on
  `/api/` makes the P1-G session-only endpoints reachable from the browser.
  See `docs/plans/p1-api-inventory.md` section G.
- **Typed client:** openapi-typescript + openapi-fetch generated from
  `src/api/contracts/openapi-full.yaml`; CI fails when the generated types
  are stale.
