---
title: "P4-A web Home on /next: screen-shaped API, check through ensure, Now Playing"
author: Joke9854
date: 2026-11-17
branch: CineTrack-API
touches:
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/fork_views_playback.py
  - src/api/home_screen.py
  - src/api/tests/test_fork_playback_progress.py
  - src/api/tests/test_home_screen_api.py
  - web/src/lib/api/client.ts
  - web/src/lib/api/schema.d.ts
  - web/src/lib/home/ProgressCard.svelte
  - web/src/lib/home/check.spec.ts
---

## Decided
- A new web screen gets its own read endpoint when the existing one is in the verified contract and lacks what the screen shows: GET /api/v1/home/sections/ (api/home_screen.py) builds every display value with the same app_tags helpers the Django templates use, so both Homes say the same thing. /api/v1/home/ stays as it is.
- The In Progress check writes through POST media/tv/{source}/{media_id}/episodes/ensure/ (path media type is always tv; anime goes in library_media_type), one event with a client event id kept for retries, so a retry answers already_satisfied. The plain .../episodes/{n}/watch/ route is not idempotent: a retry records a second play.
- watched_at: the exact ISO instant, or the browser's local YYYY-MM-DD when TRACK_TIME is off; the ensure route parses it with parse_completion_datetime, the same reader as the Django form, so the stored value matches.
- Now Playing: /api/v1/playback/now-playing/ gained display_image (through the image cache); the pill polls every 10 s while visible and reloads Home when the playing title stops or changes.
- Poster card widths follow Django: 136 px from 1024 px, 176 px between, and below 768 px the user's mobile_grid_layout (sent in the Home payload).

## Tried and ruled out
- setPointerCapture on pointerdown for mouse drag-scrolling a row: every click then lands on the row, so card links and the check do nothing. Capture only once the pointer has moved past the drag threshold.
- npx prettier in web/ without options: web/ has no prettier config, so it rewrites to double quotes and spaces. Use --use-tabs --single-quote --print-width 100 --trailing-comma none.

## Watch out
- The throwaway local Django keeps live playback in LocMemCache, so a seed script cannot start Now Playing; POST /api/v1/scrobble/ from the signed-in page (session + CSRF) does.
- Vite re-optimises dependencies on the first visit after new imports and reloads the page; a scripted click right after can land before hydration.
- The phone header wraps for the pill; give the title flex-basis 0 on phones only, or the avatar drops a line (and on tablets the title squeezes).
