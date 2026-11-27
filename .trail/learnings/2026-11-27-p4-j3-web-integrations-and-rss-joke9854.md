---
title: P4-J3 web Integrations and RSS settings
author: Joke9854
date: 2026-11-27
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - web/src/lib/settings/Integrations.svelte
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
---

## Decided
- The settings screen returns the legacy key and the webhook URLs built on it, as the Django page renders them. It is `NEVER`-scoped: session only, never an API token (test_settings_j3_api checks it).
- A new app token's secret comes back once in the create answer (`request.answer_extra["new_token"]`), not the session; the Django page keeps its session pop.
- Integrations forms that clear a missing field (Jellyfin events and settings, Seerr, sync direction, Plex share toggle) always post every field.
- RSS is a settings page reached from Notifications, not in the nav; the preview answers JSON for `Accept: application/json`.

## Tried and ruled out
- Keeping the open panel in `page.state` (shallow routing): `invalidate` after a save resets it and the page fell back to the grid while the URL still said ?open=. The tag lives in component state, set on click, on popstate and when `page.url.search` changes.

## Watch out
- About 30 webhook and scrobble tests (Emby, Jellyfin, Kodi, Stremio, generic scrobble, anime mappings) and the import tests fail locally on the last pushed commit too: they need provider network. CI passes them.
- The Stremio addon URL carries the newest install credential, as on Django; grants never return their token otherwise.
