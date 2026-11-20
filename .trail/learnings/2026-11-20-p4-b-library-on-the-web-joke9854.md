---
title: "P4-B Library on the web: writes, entry grouping, budget"
author: Joke9854
date: 2026-11-20
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/fork_views_library.py
  - src/api/library_screen.py
  - src/api/tests/test_library_api_parity.py
  - web/src/lib/api/schema.d.ts
  - web/src/lib/csrf.ts
  - web/src/lib/library/LibraryCard.svelte
  - web/src/lib/library/library.css
---

## Decided
- The web Library's writes post the Django page's own endpoints as forms (djangoForm in web/src/lib/csrf.ts): /bulk/status, /list/bulk-add, /bulk/collection, /tag_bulk_toggle, /list/share-view, /medialist/<type>/entry-grouping/. No new write API for these.
- Table cells come from the page's own cell templates rendered with a plain Context (no context processors), split into text and the small text-xs note; genres and tags are lists, tags read in one query. A parity test compares every cell with the Django table.
- Music artists and albums are trackers without an Item: api/library_screen.py builds their cards separately (_tracker_card); their tables use table_type artist / album, so the web draws columns by `role`, not key.

## Tried and ruled out
- Calling build_media_list_context directly without entry_grouping_mode: the Django media_list view wraps the list in the user's "show each play" mode, so the API grouped plays the page shows separately. build_library_screen now applies the same mode.

## Watch out
- The Library page sits at the 110 kB budget (109.8). New Library UI must load on first use (lazy.ts, {#await import()}), as the table, menus and bulk bar do.
- Vite dev only proxies the Django paths listed in web/vite.config.ts; a new Django endpoint the web posts to 404s in dev until it is added there (production is same-origin behind nginx).
- The Next ep link (next_episode_url) costs one Event query per show without a tracked next season, as media_card.html does; pinned at one per card.
