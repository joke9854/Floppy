---
title: "P4-H3 web Statistics: overviews, talent API, nav flip"
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
  - src/api/statistics_screen.py
  - src/api/tests/test_statistics_screen_api.py
  - src/app/statistics_views.py
  - web/src/lib/api/schema.d.ts
---

## Decided
- The nine Django overview templates map to one shape in api/statistics_overviews.py (charts: single series by year/month/day; lists: ranked entries with the templates' captions), drawn by lib/statistics/Overviews.svelte. Visibility follows statistics.html (has_data plus the *_enabled flags for manga, books, comics, music, podcasts).
- GET /api/v1/statistics/talent/ (api/statistics_talent_screen.py) reads build_talent_fragment_context (split from statistics_talent_fragment, cached as before). media_type re-aggregates leaders, featured player and studios like update_top_talent_sort; person_source + person_id feature a person like select_featured_person. The three sort views already answer JSON: the web posts sort_by and re-reads the talent API.
- A picked person is kept per media type in the web, so switching type shows that type's top player, as the page does.
- The nav's Stats link and /statistics links open the web page; /statistics/recap stays Django.

## Watch out
- Stored images can be TMDB's none.jpg in a size other than IMG_NONE (e.g. w342/none.jpg); image_url passes those through and they render broken. The overviews treat any /none.jpg as no image.
- Statistics sits at 109.6 kB with the talent and overview sections lazy-loaded; anything new on the page must load lazily too.
