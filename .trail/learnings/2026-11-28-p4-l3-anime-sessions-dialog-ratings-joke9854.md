---
title: "P4-L3: anime, sessions dialog, ratings graphs, studio page on the web"
author: Joke9854
date: 2026-11-28
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/details_media_screen.py
  - src/api/details_screen.py
  - src/api/fork_urls.py
  - src/api/fork_views_details.py
  - src/api/scopes.py
  - src/api/tests/test_detail_media_screen_api.py
  - src/app/history_views.py
---

## Decided
- Anime checks send `library_media_type: "anime"` from the PAGE type (details_screen `_library_type`, `_check_target`), never from `episode.item`: an unwatched row has no Item, and ensure would file the watch on a plain tv show. Tested end to end and on the local server (one anime-filed TV, exact instant).
- Checks only where `check_source_type("tv", source)` is true. NOTE: `api/fork_helpers.py` widens `helpers.VALID_SOURCES` at import, so tv/season/episode accept tvdb at runtime (reading `VALID_SOURCES` in helpers.py alone says tmdb/manual — misleading).
- Flat MAL anime is read-only on the web (preview rows link to the provider's anime episode pages).
- Anime season read: `details/anime/<source>/<id>/season/`; episode read: `?parent=anime`. Tv answers unchanged.
- Anime episode web route is a literal `[source]/anime/...` folder reusing the tv page (shared loader `web/src/lib/details/episodeLoad.ts`).
- Sessions dialog: `GET /api/v1/history/sessions/` from `build_activity_sessions_context` (Django view split); openers carry `sessions_query`. Graphs: shell lists `graphs` kinds; data from `details/(tv|anime)/<source>/<id>/graphs/`. Studio: `details/studio/<source>/<id>/` + web `studio/[source]/[id]/[[name]]`.
## Tried and ruled out
- A SvelteKit param matcher (`[kind=series]`): Kit 3 needs `src/params/index.ts` with `defineParams`, and it grew EVERY page 0.3-0.4 kB (List went to 115.2/115).
## Watch out
- Budgets: List 114.9, Detail 114.7, Podcast 114.7, Library 114.4 of 115 kB. Any new route grows them all; the next screen needs headroom work or an agreed raise.
- Session notes and the activity calendar are not in the web sessions dialog.
