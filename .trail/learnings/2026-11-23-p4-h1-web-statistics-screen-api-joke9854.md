---
title: "P4-H1 web Statistics: screen API, SVG charts, budget and chunk splits"
author: Joke9854
date: 2026-11-23
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/fork_urls.py
  - src/api/fork_views_details.py
  - src/api/scopes.py
  - src/app/statistics_views.py
  - web/scripts/check-budgets.js
  - web/src/lib/api/schema.d.ts
  - web/vite.config.ts
---

## Decided
- GET /api/v1/statistics/screen/ (api/statistics_screen.py) reads build_statistics_context, split from statistics() with its OperationalError fallback (database_error). The web forwards only start-date, end-date and compare; media-type switches in the browser, as on the page (all types' summaries and highlights come at once). Serializers are StatisticsScreen*.
- Charts are plain SVG components (lib/statistics/StackedBars.svelte, Heatmap.svelte): Chart.js does not fit the 110 kB page budget. Played Hours by Media Type ports chooseBucket/aggregateDailyToBucket from statistics-charts.js into lib/statistics/types.ts (tested), with English labels so server and browser render the same.
- The media type is a writable $derived seeded from page.url and set on pick: a shallow replaceState does not update page.url.
- Nav stays on the Django Statistics page until H3.

## Tried and ruled out
- Importing the bar chart and the preferences sheet statically: the Statistics page alone was 1 kB over, and it pushed the Library and Discover over too (shared chunks re-split when a new route imports modules they share). Lazy-loading both (dynamic import in {#await}) and dropping bind:clientWidth (fixed SVG viewBox) brought every page back under. An empty route with its loader costs the others nothing.
- Shell heredocs and the Edit tool both mangle a "–" escape; write such fixes from a script file using chr().

## Watch out
- Library, Discover and the detail page sit at 109.8-110.0 kB: H2 and H3 must lazy-load their sections. Measure the other pages, not only Statistics (scratchpad chunks.mjs lists a page's chunks and who shares them).
- The throwaway FileBasedCache needs OPTIONS MAX_ENTRIES high (statistics writes ~1,500 day keys; the default 300 culls a third, entries vanish mid-check). Build ranges with app.statistics_cache.refresh_statistics_cache(user_id, range_name) from a script.
- Locally a Refresh leaves the range "refreshing" (no worker); the page shows the banner as Django would.
