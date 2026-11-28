---
title: "P4-K3 web Import: Plex, Radarr/Sonarr, readers; Plex token kept server-side"
author: Joke9854
date: 2026-11-28
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/settings_import_screen.py
  - src/api/tests/test_settings_import_api.py
  - src/integrations/views.py
  - src/users/views.py
  - web/src/lib/api/schema.d.ts
  - web/src/lib/settings/import/AccountPanel.svelte
  - web/src/lib/settings/import/ImportDialog.svelte
---

## Decided
- Every Import source is now drawn by the web (WEB_SOURCES covers all tiles). K3 panels: Plex, Radarr/Sonarr (instances), Stremio and Audiobookshelf (generic account panel), Storyteller (device login with polling), KOReader (connect, settings, sync).
- Plex sign-in from the web is a real form submit with `next` and `auto_import=0`; plex_callback queues the wizard's default import only when the flag is absent (the setup wizard keeps it).
- `_decorate_plex_sections` drops each section's `uri` and `access_token`: they were reaching the browser through plex_sections_json and import_data_plex_sections. The cached sections in the DB keep them for imports.
- The screen carries Storyteller's pending login without the device code, KOReader settings without the password, and Radarr/Sonarr instances without API keys (tested).

## Watch out
- Opening a connected Plex dialog calls plex.tv (status and libraries); don't seed a fake Plex account locally, it would send a made-up token to Plex.
- A Storyteller pending login lives in the session: to see it locally, write `storyteller_pending_auth` into the user's sessions with a closed-port server_url and an ISO `expires_at`.
