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
| P3-A | Container shell: `web/` scaffold, the Node server in the image under supervisord, nginx `/next/`, CI (types, unit and component tests, build, e2e) | Built (`c13156f64`, `ac3d96e17`); CI green; live on beta since 2026-11-17 (`/next/` and `/next/health` answer through the tunnel, Node about 66 MB) |
| P3-B | Session bridge (board item "v2 P3 session bridge", decided 2026-11-15 in P1-G): DRF session auth with CSRF on `/api/`, allauth headless (browser client) for sign-in, the recovery-code password reset; typed API client | Built: Django side `52bdbf259`, web side next; beta check pending |
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

### P3-B Django side (2026-11-17)

- `rest_framework.authentication.SessionAuthentication` is the last API
  authenticator: a request with a token is judged by its token (no CSRF),
  a signed-in browser reaches the API with its session and must send the
  CSRF token on writes, and a request with neither is answered as before
  (403; a rejected Authorization header stays 401). Sessions keep full
  access in `HasScope`, so the session-only (`NEVER`) endpoints of P1-G and
  P1-I are now reachable from the web.
- The contracts leave the session out (`AUTHENTICATION_WHITELIST`), so the
  CineTrack contract is unchanged.
- allauth headless, browser client only, at `/_allauth/browser/v1/`
  (session, login, logout, signup, config, SSO providers). Routes Floppy
  does not use answer 404 before allauth sees them: email and phone
  management and verification, email password reset, login by code, and
  allauth's password change (the API's `user/password/` keeps the demo
  account's guard). Signup follows the same adapter as the web (closed once
  an account exists unless `REGISTRATION`). CSRF failures there answer JSON
  403 instead of the web's redirect.
- `POST /api/v1/auth/password/recover/` (`recoverPassword`): the web's
  recovery form (recovery code, or the authenticator code) for signed-out
  users. Reads no credentials, one answer for a wrong user or code, limited
  to 5 tries an hour per username and 20 per client address (`X-Real-IP`;
  behind the tunnel that is one address for everyone).
- The container smoke test signs in through nginx in production mode,
  reads and writes the API with the session (writes refused without the
  CSRF token) and signs out.

### P3-B web side (2026-11-17)

- **Bridge** (`web/src/hooks.server.ts`, `#lib/server/django.ts`): calls the
  page makes with `event.fetch` to `/api/` and `/_allauth/` on its own origin
  go to Django on 127.0.0.1:8001 with the visitor's Cookie header, the public
  `Host`, `X-Forwarded-Proto` and `X-Real-IP`; any other URL is fetched as
  is, without the cookie. Found while testing against a real Django:
  - Node's fetch drops a custom `Host`, so the bridge uses `node:http`
    (Django needs the public host for `ALLOWED_HOSTS` and absolute image
    URLs). Redirects are not followed.
  - SvelteKit adds the visitor's cookie only inside its own fetch, after
    `handleFetch`, so the bridge passes it on itself.
  - adapter-node's `getClientAddress()` throws without `X-Real-IP`; nginx
    always sends it, and the bridge sends an empty address otherwise.
- **Session:** every page but `/login` and `/health` asks allauth's session
  endpoint first; signed out it redirects to `/next/login?next=...` (`next`
  only a path inside the app), and Django not answering is a 503 page
  (the sign-in page still opens). Signed-in pages are `private, no-store`.
- **Sign-in and sign-out** happen in the browser, straight to Django's
  allauth headless endpoints with the CSRF token, so Django sets and clears
  its own cookies. The sign-in page links to the web's recovery-code page
  for now.
- **Typed client:** `npm run api:types` generates `src/lib/api/schema.d.ts`
  from `openapi-full.yaml` with openapi-typescript 7.13.0 (run through npx:
  it declares TypeScript 5 as a peer, the app uses 6); CI fails when the
  committed types differ from a fresh generation. `#lib/api/client.ts`
  wraps openapi-fetch (bundled into the build). The start page reads
  `user/account/` (session-only) through it.
- SvelteKit 3: `#lib/...` imports take the `.ts` extension, and the hook
  types come from `@sveltejs/kit/hooks`. The base path reaches app code as
  `__FLOPPY_BASE__` (a Vite define), since `$app/paths` no longer exports
  `base`.
- Checked locally against a real Django (runserver, in-memory cache): signed
  out redirects, sign-in, the signed-in page with the username from the API,
  `no-store`, and `next=//evil.example/` sent home. The container smoke test
  repeats this through nginx in production mode.

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
