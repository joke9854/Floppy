# Floppy v2: plan and decisions

Living document. Update it whenever a decision or a phase's status changes,
and record the change in the log at the bottom. Sessions working on Floppy v2
read this first.

## Goal

Make Floppy something a person can **choose instead of Trakt, Simkl or
WeTrakr**: not a Trakt clone, but a complete tracker they own.

The rework has to make Floppy **lighter, more reactive, smoother and
complete**. Every step is judged against those four words:

- **Lighter:** less JavaScript and fewer bytes per page, fewer queries per
  request, nothing slow inside a request. Budgets are checked in CI.
- **Reactive:** changes show instantly (optimistic updates) and live data
  arrives by push, not polling.
- **Smoother:** animated page changes, preloading, kept scroll and filter
  state, no layout jumps.
- **Complete:** everything the web can do is also in the API, so every client
  (web, CineTrack, NuvioTV, outside apps) can do it.

## Decisions

| Date | Decision |
|---|---|
| 2026-11-14 | Frontend: **SvelteKit** (Svelte 5), not React. Small bundles, built-in motion, simple code. Upstream's React Native Web rework is not adopted. |
| 2026-11-14 | The SvelteKit app **runs its own Node server (adapter-node)** in the Floppy container, as a backend-for-frontend in front of Django. See "Why a SvelteKit server". |
| 2026-11-14 | Backend stays **Python and Django**. Changes: Postgres as the default database, ASGI for live updates (server-sent events), the OpenAPI contract generated from code with typed clients generated from it. |
| 2026-11-14 | One repository: the SvelteKit app lives in `web/` in the Floppy repo (not `frontend/`, which upstream uses). Short branches into `CineTrack-API`; no long rewrite branch. |
| 2026-11-14 | New screens are built next to the Django pages and switched over one at a time. |
| 2026-11-14 | **Social and federation come last**, only when everything else works. |
| 2026-11-14 | Testing happens on a **beta server** with a copy of the real data and connected services paused (`FLOPPY_BETA_MODE`, `docs/stable-beta.md`). Stable only gets promoted, tested commits. |
| 2026-11-14 | Versions are plain **X.Y.Z**. A release is a `vX.Y.Z` tag on a commit that went through beta (`promote-stable.sh`); beta builds read `X.Y.(Z+1)-beta.N`. First stable release: 1.0.0. The SvelteKit cutover can be 2.0.0. Upstream's date tags (`v26.11.12`) are never pushed to the fork and are ignored by the scripts. |
| 2026-11-14 | A separate repository (detaching the fork) only when Floppy becomes its own product open to other people. License stays AGPL-3.0. |

## Why a SvelteKit server

A static build would need no extra process, but SvelteKit's best features
need its server, and Floppy's main weakness is latency: a phone on mobile data
reaches a home server through a tunnel, so every round trip is expensive.

With the SvelteKit server next to Django in the container:

- **First paint:** the first response is finished HTML with the data in it,
  instead of an empty page that then loads JavaScript and then data.
- **One round trip instead of several:** a page's data is gathered on the
  server over localhost (Django is in the same container), so the phone makes
  one request.
- **Streaming:** the page shows immediately and slower parts fill in as they
  arrive.
- **Remote functions:** components call typed server functions directly.
  `command` and `form` can refresh the affected data in the same response
  ("single-flight mutations"): tick an episode and the progress, Up Next and
  counts come back in one round trip.
- **Form actions and server load:** forms work and pages render even before
  JavaScript has loaded.

Costs and how they are handled:

- One more process (Node 22.17+, about 50 to 100 MB of memory). It runs under
  supervisord like the others, and the resource-tier probe accounts for it.
  Measure it on the minimal tier.
- A bigger image (Node runtime). Measure and keep an eye on it.
- Remote functions are still experimental in SvelteKit 3. Use them where they
  clearly pay off and keep the calls behind our own small modules, so an API
  change is a local edit.

Clients other than the web (CineTrack, NuvioTV, outside apps) keep calling
Django's API directly. The SvelteKit server never becomes a second API.

## Architecture

```
phone/browser ── Cloudflare tunnel ── nginx (in the container)
                                        ├─ /api/, /o/, /admin/, webhooks ─────► Django (gunicorn, later ASGI)
                                        ├─ posters (/image-cache/ → X-Accel) ─► files on disk
                                        ├─ Django pages not yet replaced ─────► Django
                                        └─ SvelteKit pages ───────────────────► SvelteKit (Node)
                                                                                  └─ calls Django on 127.0.0.1
```

- **Auth:** same origin, so Django's session cookie works for both. The
  SvelteKit server forwards the user's cookie to Django on localhost
  (`handleFetch`) and handles CSRF for writes.
- **Data:** a typed client generated from the OpenAPI contract
  (openapi-typescript + openapi-fetch). Every endpoint the web needs is a
  documented Django API endpoint, never a private shortcut.
- **During the transition:** the new app is served under `/next/` so it can be
  built and tried (first on beta) without touching the current site. At
  cutover it moves to `/` and the Django templates are removed.
- **Live updates:** Django pushes events (server-sent events over ASGI); the
  web subscribes once instead of polling every few seconds.
- **Images:** posters stay files served by nginx; later stored in the card
  sizes with a content hash in the name, so browsers never revalidate them.

## Frontend stack (checked 2026-11-14)

SvelteKit 3.2, Svelte 5.57, Vite 8, `@sveltejs/adapter-node`. SvelteKit 3
specifics: configuration in `vite.config.js`, `#lib` instead of `$lib`,
`$app/state`, `goto(url, { shallow: true })`, environment through `$app/env`.

Use:

| Package | For |
|---|---|
| Tailwind 4 | Styling with the existing Floppy/CineTrack tokens (`DESIGN.md`) |
| bits-ui 2 | Accessible unstyled primitives: dialogs, popovers, menus, tabs, sliders |
| openapi-typescript + openapi-fetch | Typed API client from the OpenAPI contract |
| TanStack Query (Svelte) | Client-side cache where remote functions don't fit (only if needed) |
| virtua | Virtualized long lists and grids (library, history) |
| Paraglide 3 | Compiled translations |
| LayerChart | Statistics charts |
| Lucide | Icons |
| Valibot | Validation for remote functions and forms (Standard Schema) |
| Vitest, Testing Library, Playwright, svelte-check | Tests and type checks |
| Svelte AI tools (MCP, svelte-autofixer) | Checking generated Svelte code |

Built-in tools to lean on for smoothness: View Transitions through
`onNavigate`, `crossfade`, `animate:flip`, `Spring`/`Tween` with
`prefersReducedMotion`, link preloading (`data-sveltekit-preload-*`),
`snapshot()`, shallow routing for detail sheets, overridable `$derived` and
`$state.eager` for optimistic updates, the native service worker
(`$app/service-worker`, `$app/manifest`) and new-version detection.

Not used: Drizzle and better-auth (Django owns data and accounts),
enhanced-img (build-time images only), @vite-pwa (the native service worker is
enough), full component kits (they fight the CineTrack look), svelte-motion
(built-in motion is enough).

## Phases

| Phase | Content | Status |
|---|---|---|
| P0 | Stable and beta servers, beta mode, versioned images, scripts (`docs/stable-beta.md`) | Live since 2026-11-14: stable 1.0.0, beta 1.0.1-beta.N on a data copy, cron updates; beta at https://floppybeta.bingehub.stream |
| P1 | Complete API: inventory of web-only actions, endpoints for them, OpenAPI generated from code, typed error codes (503 for provider failures), scopes | Started. Inventory and slices A-I in `docs/plans/p1-api-inventory.md` (board items P1-A to P1-I). Done: P1-A typed errors, provider outages answer 503 `provider_unavailable` (`a40ab14a4`, `04a0145f3`); P1-B full contract `src/api/contracts/openapi-full.yaml` checked against the code (`2d8cc2b9b`). Next: P1-C |
| P2 | Backend foundations: Postgres default (SQLite kept for minimal installs), ASGI and server-sent events, priority job queues, poster size variants | Not started |
| P3 | SvelteKit foundation in `web/`: adapter-node in the image under supervisord, nginx routing, `/next/`, auth bridge, design tokens, base components, API client, service worker, CI (svelte-check, Vitest, Playwright), bundle and response-time budgets | Not started |
| P4 | Screens, one at a time, each with a parity checklist, measured and tried on beta before it switches: Home, Library, detail pages, Track dialog, History, Calendar, Discover, Statistics, Lists, Settings and integrations, Imports | Not started |
| P5 | Cutover: SvelteKit serves `/`, Django templates removed | Not started |
| P6 | Social and federation (last) | Not started |

Product work that runs alongside, from the "replace Trakt" list: lossless
imports from Trakt, Simkl, TV Time, Letterboxd, IMDb and MAL; notifications
and a calendar feed; automatic tracking from more players; complete export and
tested restore; a status page.

## Open questions

- Hosting for people who don't self-host: install packages only, community
  servers, or a hosted Floppy.
- iOS client: build one or partner with an existing app.
- Moving existing SQLite installs to Postgres: automatic migration or opt-in.
- Node memory on the minimal resource tier.
- How far to adopt remote functions while they are experimental.

## Rules that always apply

The CineTrack/Floppy invariants in `CLAUDE.md` of the CineTrack repo stay in
force: exact watch times, rewatches are separate plays, ACK only known
outcomes, classify HTTP failures, never delete user data to debug.

## Log

- 2026-11-14: Plan created. SvelteKit with its own Node server chosen; P0
  built.
- 2026-11-14: X.Y.Z versions; stable follows releases (`stable-update.sh`),
  beta follows green CI (`beta-update.sh`); the old `update-floppy.sh` (which
  deployed every green commit to the real server) is retired.
- 2026-11-14: Released 1.0.0 (`f47238c07`). Server switched: stable runs
  `ghcr.io/joke9854/floppy:1.0.0` (FLOPPY_VERSION in ~/floppy/.env), beta
  runs in ~/floppy/beta on a copy of the data, cron runs beta-update.sh every
  15 minutes and stable-update.sh at 04:30.
- 2026-11-14: P1 started with typed provider errors: TMDB timeouts, 429s and
  5xx answer 503 `provider_unavailable` with Retry-After instead of 404 on the
  tracking write and episode ensure/translate routes (`a40ab14a4`); CineTrack
  no longer acknowledges an unwatch on the old 404 (`52cce24`).
- 2026-11-14: P1 inventory (`docs/plans/p1-api-inventory.md`): 243 web actions
  and 59 pages against 189 API operations (68 in the verified contract). Gaps
  grouped into slices A-I in the order the SvelteKit screens need them;
  account, security and admin endpoints accept the web session only.
- 2026-11-14: P1-A done (`04a0145f3`): a DRF exception handler gives every API
  error a code; provider outages answer 503 on all routes that call a
  provider; no response echoes exception text.
- 2026-11-14: P1-B done: every API operation is in the committed
  `openapi-full.yaml` (184), tested against the code and required to carry
  `x-required-scope`; the verified `openapi.yaml` keeps its meaning for MCP.
  The P3 typed client is generated from the full file.
