---
title: "v2 audit, remaining items: plays, calendar, absolute numbering, canon row, Add defaults, stats, Library perf, quick status, P7 sheet"
author: Joke9854
date: 2026-11-06
branch: CineTrack-API
touches:
  - src/app/history_cache.py
  - src/app/history_cache_day_builder.py
  - src/app/history_cache_index.py
  - src/app/home_sections.py
  - src/events/views.py
  - src/app/models/manager.py
  - src/app/discover/trakt_candidates.py
  - src/app/track_modal_views.py
  - src/app/statistics_aggregator.py
  - src/app/media_list_views.py
  - src/app/save_views.py
  - src/templates/app/components/detail_action_buttons.html
  - src/templates/app/components/detail_track_action.html
  - src/templates/app/components/detail_episode_hero_track_button.html
  - src/templates/users/integrations.html
  - src/templates/lists/components/list_form.html
---

## Decided
- A Planning Movie row is never a play, whatever dates an import left on it: History (`_fetch_movie_data`, the day builder, the day index), Home Recently Watched and the detail "Your Plays" (`ct_plays` filter) exclude it. `HISTORY_CACHE_VERSION` went 21 → 22, so every user's History rebuilds once after deploy.
- A planned movie gets a v2 hero "Mark Watched": a plain POST to `media_save` with `save_as_new_entry=1` and `status=Completed`. The new row takes the plan's score and notes (`prepare_completed_entry`) and the plan row is removed.
- Calendar: a season with no Season row (a new season of a tracked show) had status None, rendered as `data-release-status="None"`, and the client status filter hid every episode. The view now gives such seasons the show's TV status, and templates render a missing status as "".
- Absolute-numbered shows (One Piece S11 = E382–E407): `_annotate_tv_released_episodes` counts a season with no Season row as `max − first + 1`, using the first `content_number` from all events. Tracked seasons keep the highest number, because `Season.progress` is the furthest episode number, so the two still cancel.
- All-Time Greats: `_trakt_canon_candidates` drops titles from the last 3 years and Trakt ratings below 7.0. Undated candidates pass. `MOVIE_CANON_ROW_SCHEMA_VERSION` 2 → 3.
- v2 Add (track modal, untracked title) defaults to Planning, and Delete is hidden. The classic theme keeps the Completed default and a disabled Delete.
- Stats: a day with more than 24 h of plays is an import stamping its run time (prod: 4,768 plays on Mon 12 Oct). It stays in totals but leaves hour counts, the weekday/hour charts and Most Active Day.
- Library perf: list pages call `annotate_max_progress(..., cached_only=True)`. TMDB seasons read their provider length from the season cache only, and a miss falls back to the DB released count. Model logic (rewatch, completion) still fetches, since 7 rewatch tests depend on the real length. The ~900-entry provider catalog (120 KB of JSON) is dropped from `filter_data` when the providers panel is hidden. Media cards use `Alpine.data("mediaCard")` from bulkSelection.js instead of a 1 KB inline x-data.
- Quick status (A2/A10): on CineTrack a tracked title's status button opens a pull-down. Each status is one POST to the new `media_status` view, which changes only the status (plus end_date now for dated, non-TV entries becoming Completed). "Edit details" opens the old window. CineTrack movies now use `detail_track_action.html` instead of the classic split button.
- Episode page (v2): an unwatched episode marks in one click (form → `episode_save?next=<episode page>`). The wrapper is `data-ct-live`, so the toast's Undo flips it back.
- P7 phones: the secondary icon row becomes a bottom sheet. `.ct-more-items` is `display: contents` elsewhere, so desktop is unchanged. Fix match is copied into the sheet and the hero copy hidden. The sheet must not get a transform or filter, because the items' own modals are `position: fixed`.

## Tried and ruled out
- Home active-playback "several polls at once" did not reproduce on prod: one request per 10 s after three boosted round trips and a forced `visibilitychange`. The network panel lists each request twice (request + response).
- Matching identical timestamps to detect imports: the prod import stamped plays across ~90 min, not one instant.
- Swapping the season metadata length for the DB count everywhere: it changes "caught up" and rewatch logic.

## Watch out
- `scripts/test.sh --exclude-tag network` runs **zero** tests (the flag is taken as a label). The fast suite already excludes network; pass the flag only after labels.
- `.ct-detail-actions .ct-action-bar > a` sits later in input.css than the phone rules, so a hide rule for an action-bar link needs one more class to win.
- Sticky footers inside a padded scroll container stick at the padding edge: use `-bottom-6` with `p-6`.
- `StatisticsStaleResultTests.test_lightweight_statistics_reads_refresh_retained_stale_results` is flaky before this change too (fails about 1 in 3 runs).
