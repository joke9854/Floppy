---
title: "Percent progress: an unchanged percentage keeps the exact page count"
author: Joke9854
date: 2026-11-21
branch: CineTrack-API
touches:
  - docs/plans/p4-screens.md
  - src/api/tests/test_track_screen_api.py
  - src/app/save_views.py
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
---

## Decided
- media_save (app/save_views.py) keeps the stored progress when the posted percentage equals round(stored / max * 100, 1), the value the track dialog showed; any other percentage converts as before. Applies to the Django dialog and the web dialog (same view). Approved by the user 2026-11-21.
## Tried and ruled out
- Leaving it: 0.1% steps are wider than a page past 1000 pages, so every untouched Update in percent mode could move a long book a page (337/1500 -> 22.5% -> 338). This supersedes the Watch out in the P4-D2a learning.
## Watch out
- The display rounding (app/track_modal_views.py, round(..., 1)) and the save check must use the same max_progress and rounding; change both together.
