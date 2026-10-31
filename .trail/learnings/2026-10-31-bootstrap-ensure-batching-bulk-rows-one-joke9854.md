---
title: "Bootstrap ensure batching: bulk rows, one projection per movie"
author: Joke9854
date: 2026-10-31
branch: CineTrack-API
cost: { minutes: 31, tokens: 77405 }
touches:
  - src/api/cinetrack_bootstrap_views.py
  - src/api/tests/test_cinetrack_bootstrap_performance.py
---

## Decided
- `api/cinetrack_bootstrap_views.py` ensure paths bulk_create Movie/TV rows and run movie writes under `suspend_projection()`, then project once per touched movie after the status/end_date bulk_update, inside one transaction.
- Every signals.py receiver on Movie/TV returns on `raw`; the old `save_base(raw=True)` only ever triggered the watch-state receivers, so bulk_create is equivalent once projection and `refresh_sync_items` are run explicitly.
## Tried and ruled out
- Bulk-creating Items: skips the Item post_save backfill receiver (runtime/genre/credit enqueues gated per item). Left per row.
- Plain create for MoviePlay instead of get_or_create: loses race safety on the unique (movie, external_id).
## Watch out
- bulk_update fires no signals: a status-only movie change used to leave WatchState stale. Anything that bulk_updates Movie status must reproject.
- Growth budgets live in `api.tests.test_cinetrack_bootstrap_performance` (16/5 base, 29/5 with the sync index).
