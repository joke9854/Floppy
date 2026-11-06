---
title: "v2 Settings and Login: grouped nav, integration cards, public login with TMDB wall"
author: Joke9854
date: 2026-11-06
branch: CineTrack-API
touches:
  - src/templates/users/base.html
  - src/templates/users/components/ct_settings_nav.html
  - src/templates/users/components/ct_integrations_grid.html
  - src/templates/users/components/ct_integration_card.html
  - src/templates/users/integrations.html
  - src/templates/users/appearance.html
  - src/templates/users/connected_apps.html
  - src/templates/account/login.html
  - src/templates/allauth/layouts/entrance_v2.html
  - src/templates/base.html
  - src/app/login_wall.py
  - src/app/tasks.py
  - src/static/css/input.css
  - docs/agents/v2_mockup_gaps.md
---

## Decided
- Phase 6 (Apple layout v2) is A5 Settings · Integrations, A22 Settings · Appearance and A15 Login. There is no mobile board for either; phones reuse the pill-row settings nav and a single-column login.
- Every settings page shares the v2 frame (`users/components/ct_settings_nav.html` groups You / Library / Data, content column). Only pages with a board get a `settings_head` block (title + subtitle); the others keep their own headings, so no copy is invented. "Media types" is the existing Sidebar page; Preferences stays in the nav (core options); RSS and About are hidden from the nav only.
- A5 reuses the page's existing `activeIntegration` switch (`?open=` deep links). CineTrack starts on `'grid'` (cards); Manage/Connect open that integration's existing panels. Legacy key, app tokens, sync and Nuvio live in an `'api'` view behind one link; Connected apps links to `?open=api#connected-apps`. Card statuses use stored state only (Emby/Kodi/Stremio have none, so "Set up").
- The user chose: the A15 login is shown to every theme. `base.html` has an `html_theme` block; `entrance_v2.html` sets it to `cinetrack`. The login keeps allauth elements (`element form/fields/button`, provider list, SSO auto-redirect script needs `#providers`).
- Login poster wall: TMDB trending (public) via `app.login_wall`. The page only reads the cache; a miss schedules `refresh_login_wall_posters` once (cache.add lock) and renders placeholder tiles. 24h TTL, 1h on empty.

## Tried and ruled out
- Gating the login on a theme cookie or an instance setting: the user picked "everyone sees v2".
- Library posters on the login wall: private data before sign-in.

## Watch out
- Tests run Celery eagerly and block external HTTP; a login render on a cold cache runs the refresh, which fails fast and caches an empty list. Mock `refresh_login_wall_posters.delay` when asserting scheduling.
- With no users, `IS_FIRST_RUN` makes the login say "Welcome to Floppy"; create a user before asserting "Sign in to Floppy".
- `{% translate "Apps & services" %}` renders a raw `&`, not `&amp;`.
- `.preferences-section` has its own `margin-bottom`; inside the flex `.ct-appearance` it must be zeroed explicitly.
- The Phase 1 `.ct-sidebar-preview` spans had no CSS until this phase.
