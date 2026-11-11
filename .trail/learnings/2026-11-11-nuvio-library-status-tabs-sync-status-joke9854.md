---
title: Nuvio library = status tabs; sync/status none removes without history
author: Joke9854
date: 2026-11-11
branch: CineTrack-API
touches:
  - docs/integrations/nuvio-client-guide.md
  - src/api/fork_views_sync_writes.py
  - src/api/serializers.py
  - src/api/tests/test_sync_writes.py
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
  - ct_contract.log
---

## Decided
- Nuvio TV's Floppy library uses Simkl-style status tabs (Planning=Watchlist, In progress=Watching, Paused=On hold, Completed, Dropped), read from GET sync/items/snapshot + changes (status, in_library) and written with POST sync/status/. Floppy lists as extra tabs are deferred: they need lists:read/write, which the app scope preset (api/scopes.py TRACKING_PRESET) does not include.
- POST sync/status/ status "none" (capability sync_status_remove_v1): removes the user's Movie/TV rows only when there is no history (movie: any MoviePlay or end_date; show: any Season row). With history -> conflict/has_history and nothing deleted. Not in library -> already_satisfied. Never creates an Item or calls the provider.
## Tried and ruled out
- Deleting via MediaDetailView DELETE: plays hang off the Movie row (MoviePlay FK) and seasons off TV, so it wipes history.
## Watch out
- Rows are deleted one by one with row.delete() so the post_delete signals keep the sync-items index right; a queryset delete would skip them.
- sync/items only indexes users with an emit_changes sync connection (WatchStateSequence); the client must register via sync/connections first.
