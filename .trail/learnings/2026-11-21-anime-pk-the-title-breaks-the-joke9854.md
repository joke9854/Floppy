---
title: "Anime pk: the title breaks the tie, it does not filter"
author: Joke9854
date: 2026-11-21
branch: CineTrack-API
touches:
  - src/api/tests/test_track_screen_api.py
  - src/app/models/manager.py
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
---

## Decided
- get_media's anime branch uses media_id/source as a tie-breaker, not a filter: it loads the Anime row and the anime-filed TV row with that pk, returns the one whose Item matches the title, else Anime first, then TV, as before. Only the collision case changes behaviour.
## Tried and ruled out
- Filtering by item__media_id/item__source (commit 971c23729): any caller whose media_id/source differ from the row's Item (episode_save rewrites source from the route, provider overrides in the builder) missed and raised DoesNotExist, so saves 500ed and the dialog opened as Add.
## Watch out
- progress_edit and media_status post the item's own type (tv), so they never take the anime branch for a TMDB show.
