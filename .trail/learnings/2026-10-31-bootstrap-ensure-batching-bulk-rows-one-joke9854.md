---
title: "Bootstrap ensure batching: constant queries per movie/show batch"
author: Joke9854
date: 2026-10-31
branch: CineTrack-API
cost: { minutes: 31, tokens: 77405 }
touches:
  - src/api/cinetrack_bootstrap_views.py
  - src/api/tests/test_cinetrack_bootstrap_performance.py
  - src/app/services/watch_state.py
  - src/app/signals.py
---

## Decided
- Movie/show ensure batches cost a constant number of queries per batch: Items, Movie/TV rows and MoviePlays are bulk-created, legacy play adoption is bulk-updated, and movies are projected with `watch_state.project_movie_watch_states` (2 derive queries, bulk create/update of WatchState) after the status/end_date bulk_update, in one transaction.
- `signals.queue_backfills_for_new_items` queues the runtime/genre/credit backfills that Item's post_save would queue on create, one enqueue call each. A new item has no credits or backfill state, so the receiver's per-item checks are no-ops.
- Every signals.py receiver on Movie/TV returns on `raw`, so bulk_create skips only the watch-state receivers, which are run explicitly. `Item.save` sets `library_media_type` when empty; bulk paths must set it.
- `existing_plays` is authoritative: it holds every stored play for the batch's movies and external ids, and a watch always carries a non-empty client_event_id.
## Tried and ruled out
- Calling the Item post_save receiver per bulk-created item: brings back 4 queries per row.
## Watch out
- bulk_update fires no signals: a status-only movie change used to leave WatchState stale. Anything that bulk_updates Movie status must reproject.
- With the change log on (`WatchStateSequence.emit_changes`), each moved movie still records its own change (12.7 queries per new movie), by design.
- Growth budgets in `api.tests.test_cinetrack_bootstrap_performance`: 0/0 base, 14/0 with the sync index.
