---
title: "P4-L1 web detail pages for manga, games, books, comics, board games"
author: Joke9854
date: 2026-11-28
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/details_screen.py
  - src/api/fork_views_details.py
  - src/api/tests/test_detail_screen_api.py
  - web/src/lib/api/schema.d.ts
  - web/src/lib/details/Sections.svelte
  - web/src/lib/details/api.spec.ts
  - web/src/lib/details/api.ts
---

## Decided
- `src/api/details_screen.py` serves the L1 types (`L1_TYPES`) beside movie/tv; anime stays 400 (its next-episode mark posts episode events: own contract check, moved to L3).
- Every new field is additive and empty/null for movie and tv: meta `progress` (the page's `activity_subtitle.primary_text`) and `series` (books); sections `issues`/`issues_more` (comic), `game_lengths` (every game, so a game without figures shows the page's not-available note), `authors`, `studios`, `genres`.
- `_action` returns None for non-movie/tv types; without it a finished book fell through to the episode/completed branch and showed "Watched".
- L1 types use `_SECTIONS_L1` (adds game_lengths, genres, studios); the user's layout family still filters it (game family has no related; comic has Issues and no cast).
- Comic issues: Track opens `comicissue` (the real MediaTypes value), issue links stay Django; "Show ..." re-fetches sections with `episode_page`.
## Tried and ruled out
- Patching the issue page size: `_paginate_detail_episodes` binds `per_page=25` as a default argument, so tests use 26 issues.
## Watch out
- Local manual items have no Time to Beat, issues, authors or series; `/next/dev/components` has a "Detail sections (P4-L1)" fixture block (it must import `#lib/details/details.css`).
- Vitest's browser project fails with `listen EACCES ::1:<port>` on Windows reserved ports: set `VITEST_BROWSER_PORT`.
- The detail page is 113.3 of 115 kB; new detail UI belongs in the lazy Sections chunk.
