---
title: "P4-B Library: the web reads the Django page's own list builder"
author: Joke9854
date: 2026-11-18
branch: CineTrack-API
touches:
  - ".github/workflows/docker-image.yml"
  - web/scripts/check-budgets.js
  - web/src/lib/home/StatusChip.svelte
  - web/src/lib/home/home.css
  - web/src/lib/shell/LinkMenu.svelte
  - web/src/lib/shell/NavLink.svelte
  - web/src/lib/shell/Shell.svelte
  - web/src/lib/shell/nav.spec.ts
  - web/src/lib/shell/nav.ts
  - web/src/lib/strings.ts
---

## Decided
- The web Library reads GET /api/v1/library/{type}/ (api/library_screen.py), built on build_media_list_context, which was split out of app.media_list_views.media_list as a pure extraction. Parity with the page is by construction, including saved preferences and page size.
- The builder saves sort, direction, layout and status preferences like the page, so the route is scope NEVER (session or account token). The web never sends `layout` until the table exists, and sort/status are buttons, not links, so hover preloading cannot save a preference.
- The card's sorted-by line is the grid's own template (ct/library_sort_detail.html) rendered and sent as text.
- GET /api/v1/media/{type}/ was aligned with the page: descending keeps ties A to Z; TV Time Left uses app.tv_sort._sort_tv_media_by_time_left; TV Start Date ignores TV.start_date's In Progress "added" fallback. test_library_api_parity holds it to the page for every offered sort, status and search.

## Tried and ruled out
- Building the web Library on get_media_list_entries (the API's list): it is a second implementation and differed from the page on 14 sort/type pairs.
- Comparing the page's sorts naively: the page only offers some sorts per type (sort_choices, critic rating and author gated) and falls back to Title for the rest.

## Watch out
- The Episode Air Date sort loaded unstarted seasons per show (193 queries on beta); manager._preload_show_season_events now does it in one query. Keep new per-show lookups out of _next_episode_air_date_value.
- test_query_counts pins were already over budget before P4-B; the full suite runs only on pull requests, and CineTrack-API is pushed directly (board Bug).
- Timing on beta: run the view inside transaction.atomic() and raise to roll back (it writes preferences); give it a private LocMemCache for cold runs instead of deleting beta's cache keys. Pipe scripts through PowerShell ssh and strip the BOM on the server (sed '1s/^\xEF\xBB\xBF//').
- A first request saves the sort preference and creates the settings row (5 extra queries); warm up before comparing query counts.
