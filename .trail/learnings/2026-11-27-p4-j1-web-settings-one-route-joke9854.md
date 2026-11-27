---
title: "P4-J1 web settings: one route, Django forms answer JSON, P1 settings APIs mismatch"
author: Joke9854
date: 2026-11-27
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/fork_urls.py
  - src/api/fork_views_details.py
  - src/api/fork_views_users.py
  - src/api/scopes.py
  - src/users/views.py
  - web/scripts/check-budgets.js
  - web/src/lib/api/schema.d.ts
---

## Decided
- One web route `/next/settings/[page]` (slug = Django path's last segment) with each page component lazy-loaded through a loader map; an empty route cost ~0.1 kB on other pages. `GET /api/v1/settings/screen/<slug>/` returns the nav (items flagged `web`) and the page; unbuilt pages answer `handled: false` and the loader redirects to Django.
- Saves go through the Django views' own forms with `Accept: application/json` (`_json_saved` in users/views.py), not the P1 settings endpoints, because those differ from the pages: no media-type order on `user/sidebar`, preferences PATCH lacks ui_language/watch_provider_region/metadata_language/hide_episode_overviews/auto_pause_rules, appearance GET returns raw (not resolved) layouts.
- Authenticator setup and recovery codes stay on the Django Account page (secret and codes shown once).
- Vite dev proxy needs every Django path the web posts to (`/settings/`, `/notifications/search/`); production is same-origin.

## Tried and ruled out
- Using `PATCH /api/v1/user/notifications/` as-is: it bound three of the form's four fields, so every PATCH turned the premiere digest off. Fixed (reads and writes all four).

## Watch out
- Form pages reset what is left out: the sidebar POST turns off any type not posted; appearance without `detail_layouts` resets every layout; notifications checkboxes save False when absent. Post everything back; each page has a round-trip test.
- When inserting a helper above a decorated view with str.replace, the decorator stays on the helper (`@require_http_methods` landed on `_json_form_errors`). Anchor on the decorator line.
- The legacy account token is only readable via POST `user/token/regenerate` (which rotates it); J3 (Integrations/RSS) needs a read path or must stay on Django.
