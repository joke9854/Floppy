---
title: "P4-G1 web Discover: screen API, discover_action JSON, local rows without a worker"
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
  - src/app/discover_views.py
  - web/scripts/check-budgets.js
  - web/src/lib/api/schema.d.ts
  - web/src/lib/home/home.css
---

## Decided
- GET /api/v1/discover/screen/ (api/discover_screen.py) reads build_discover_context (split from discover_page); /api/v1/discover/rows/ stays the CineTrack contract. Serializers are DiscoverScreen*: DiscoverRow*, DiscoverCandidate* and DiscoverHidden* already exist.
- Each card and hero slide carries the exact discover_action form fields. `image` is the stored candidate image (or IMG_NONE), never the image-cache URL: a Hide seeds a new Item from it.
- discover_action answers JSON for Accept: application/json ({action, message, undo_token, active_media_type}; 400s as {error}) right after apply_cached_action patches the tab cache, so the web re-reads the screen instead of receiving rows. Undo answers after restore_undo_snapshot, which writes the snapshot back to the tab cache.
- The web waits on /api/cache-status/?cache_type=discover (is_refreshing or refresh_scheduled) and reloads when the rebuild ends, like the page's CacheUpdater.
- .ct-row moved from lib/home/home.css to lib/styles/cards.css: Discover reuses lib/home/Row.svelte and must import cards.css.
- The nav link and detailHref /discover pattern flip with G1 because Planning, Hide and Undo work; Add to custom lists waits for the Lists dialog (P4-I).

## Tried and ruled out
- CELERY_TASK_ALWAYS_EAGER on the throwaway server to build Discover rows: every request then runs the middleware warmup and every tab's rebuild inline (minutes per request; a Hide never returned).
- Pixel clicks on the hover-only card buttons while the browser pane is hidden landed on the neighbouring card; check with elementFromPoint and click from script instead.

## Watch out
- Locally, Discover rows need a shared cache: switch the throwaway settings to FileBasedCache, build with app.tasks_discover.refresh_discover_tab_cache(user_id, media_type, force=True) from a script, and run the server with eager off. LocMemCache is per process.
- SvelteKit 3 goto: noScroll/keepFocus are gone; use { reset: false } and replace instead of replaceState.
