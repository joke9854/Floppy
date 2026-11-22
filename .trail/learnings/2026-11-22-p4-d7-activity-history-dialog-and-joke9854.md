---
title: P4-D7 Activity History dialog and the shell-icon budget trap
author: Joke9854
date: 2026-11-22
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/fork_urls.py
  - src/api/fork_views_details.py
  - src/api/scopes.py
  - src/api/tests/test_track_screen_api.py
  - src/api/track_screen.py
  - src/app/views.py
  - web/src/lib/api/schema.d.ts
---

## Decided
- The web Activity History dialog reads the page's history timeline through build_history_context (split from views.history_modal) at GET /api/v1/activity/{type}/{source}/{id}/; Edit reopens the track dialog with instance_id, Delete calls delete_history_record with DELETE and the CSRF header.
- New API views need an entry in api/scopes.py VIEW_SCOPES (web-only screens: NEVER) or the contract test fails on x-required-scope.

## Tried and ruled out
- Moving strings or the opener out of open.svelte.ts / lib/strings.ts to fix the Library budget: no effect.

## Watch out
- A lazy chunk importing a lucide icon the shell also uses (search) splits that icon into its own file and adds ~0.2 kB to every page: keep shell icons out of lazy dialogs or check npm run budgets.
- In TrackHost, {@const x = trackRequest.activity} re-reads as null once you clear it: copy it before clearing.
