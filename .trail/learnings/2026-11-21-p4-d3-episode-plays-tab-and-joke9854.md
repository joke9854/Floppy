---
title: P4-D3 Episode Plays tab and bulk plays keeping their times
author: Joke9854
date: 2026-11-21
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/tests/test_track_screen_api.py
  - src/api/track_screen.py
  - src/app/save_views.py
  - src/app/tasks_bulk_plays.py
  - src/app/tests/views/test_episode_bulk_save.py
  - src/app/tests/views/test_music_bulk_save.py
  - src/app/views.py
---

## Decided
- The web Episode Plays tab reads the page's BulkEpisodeTrackForm and domain as the track screen's `plays` (api/track_screen.py _plays, from the context all three builders share) and posts it to episode_bulk_save / music_bulk_save with Accept: application/json; both answer {queued, message, task_id} or {queued: false, error}. The range logic, summary and warnings are ported in web/src/lib/track/plays.ts.
- tasks_bulk_plays.py cut the posted start/end to dates (date.fromisoformat(value.split("T")[0])). date + timedelta(seconds) drops sub-day parts, so every play fell on midnight and the "+1 second" that keeps plays strictly increasing did nothing for same-day episodes. The jobs now read the full value via coerce_episode_datetime (server TIME_ZONE, as the normal save does); date-only values still mean midnight.
- In the page's picker, any commit to start_date (including Start Now / Just Finished pairing from the end) sets manualStartDate; only the Release Date backfill writes the start directly. rules.ts now matches (setPaired marks a manual start; backfillStart does not).
## Watch out
- Local throwaway runs Celery with a memory broker and no worker: bulk saves queue and never run. CELERY_TASK_ALWAYS_EAGER=True runs them, but also every follow-up job inline (Discover refreshes), which holds SQLite for minutes.
- test_music_bulk_save pinned the date-cut artefact; it now asserts exact instants.
