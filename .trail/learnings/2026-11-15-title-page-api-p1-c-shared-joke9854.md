---
title: "Title-page API (P1-C): shared page builders and what the API leaves to the client"
author: Joke9854
date: 2026-11-15
branch: CineTrack-API
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
  - ct_contract.log
  - src/app/people_data.py
---

## Decided
- Person and studio page data lives in `src/app/people_data.py` (`build_person_page`, `build_studio_page`). The web views (`app/people_views.py`) keep only filters, sorting and template state; `api/fork_views_pages.py` serializes the same dicts. Change the data there, once.
- API views for pages let provider errors escape to `api.exceptions.api_exception_handler` (404 for provider not-found, 503 `provider_unavailable` otherwise, Http404 to 404 `not_found`) instead of their own try/except.
- Responses carry data only: no colors, legends, sort menus or `current_*` filter state. The client filters and sorts the full credit list.
- `tracked_item` in the builders is a global `Item` lookup, not "this user tracks it": the API exposes it as `item_id`; `watched` is the per-user flag.
- The ratings graph GET queues `populate_trakt_episode_ratings_for_season` only while Trakt ratings of aired episodes are missing, guarded by `cache.add` (10 min per season) so polling does not re-queue.

## Tried and ruled out
- A separate endpoint for the watch-sessions modal: `GET history/` already takes media_id/source/logging_style; it only lacked per-entry `notes` (`attach_session_notes`).

## Watch out
- `app.tests.test_query_counts` media-list budgets (e.g. movie list 15 vs 14 queries) already fail on `ac14bc4a4` locally, before P1-C; not caused by these endpoints.
- Provider fetchers are patched in tests as `app.providers.tmdb.person` etc.; the builders look them up at call time, so moving code between modules keeps those patches working.
