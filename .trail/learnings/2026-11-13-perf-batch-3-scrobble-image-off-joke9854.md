---
title: "Perf batch 3: scrobble image off the request, poll exclusions, SQL snapshot paging, Jellyfin skip"
author: Joke9854
date: 2026-11-13
branch: CineTrack-API
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
  - ct_contract.log
  - src/app/tests/test_interactive_requests.py
---

## Decided
- Scrobble API saves a new title without artwork (apply_playback_event resolve_image=False) and enqueues resolve_playback_image; webhooks keep resolving inline in the worker.
- Polls are excluded from the interactive marker by URL name (app/interactive_requests.py); /api/ paths were already excluded, episode_history_poll was the only gap.
- Sync items snapshot pages with a SQL union of the Movie/TV/Episode id querysets; each part needs .order_by() or SQLite rejects ORDER BY inside the compound query.
- Jellyfin hourly push skips when no library/watched/removed SyncActivity changed since the last full push (state in cache jellyfin_push_state:<user>, full push at least every 24 h). Manual button and webhook pass force=True; a skipped run must not stamp last_sync_at or clear connection_broken.
- Incremental metadata backfill counts only on the nightly run (report_remaining=True).

## Tried and ruled out
- interactive_request_scope on the tracking write views (episode/movie watch, ensure): their broad except turns any provider failure into 404 "Could not resolve season.", so short timeouts would make transient failures look final to clients. Fix the 503 mapping first (board bug, both repos).

## Watch out
- api/helpers.py resolve_episode_coordinate_for_request maps InvalidEpisodeCoordinateError to 404 and deletes detached history for that route; never let a provider failure reach that branch.
- Episode watched changes bump the `watched` SyncActivity category, not `library`.
