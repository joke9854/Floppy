---
title: "P4-G2 Discover card lists dialog: lists_modal JSON and the episode backfill"
author: Joke9854
date: 2026-11-23
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/discover_screen.py
  - src/api/tests/test_discover_screen_api.py
  - src/lists/views_helpers.py
  - src/lists/views_list_actions.py
  - web/src/lib/api/schema.d.ts
  - web/src/lib/discover/DiscoverCard.svelte
  - web/src/lib/discover/discover.css
---

## Decided
- A Discover card's Add to custom lists reuses the Django lists_modal URL (app_tags.media_view_url("lists_modal", candidate), sent as the card's lists_url) and list_item_toggle; both answer JSON for Accept: application/json. The web dialog is lib/discover/ListsDialog.svelte on lib/ui/Dialog.svelte, which the shell already ships, so it adds little to the bundle.
- lists_modal still creates the Item (provider metadata) when the title has none, as the page does; that open is slow only the first time.

## Tried and ruled out
- Keeping _maybe_backfill_episode_title's force=True for every item: for a movie it fetched SEASON metadata for the movie id, then the movie, on every lists_modal open (and lists add/recommendation views). It now returns early for non-episodes; force only skips the needs-backfill check for episodes.

## Watch out
- Running one test class alone can hang on a real provider call that the full run fails fast on (UnexpectedExternalNetworkAccessError appears in other modules' runs): patch app.providers.services.get_media_metadata and assert it is not called.
- Discover is at 109.7 of its 110 kB budget after G2; the next Discover change needs to save bytes first.
