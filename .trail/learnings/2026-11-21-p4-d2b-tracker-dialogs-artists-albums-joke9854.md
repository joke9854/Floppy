---
title: "P4-D2b tracker dialogs: artists, albums, podcast shows"
author: Joke9854
date: 2026-11-21
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/fork_views_details.py
  - src/api/library_screen.py
  - src/api/tests/test_track_screen_api.py
  - src/api/track_screen.py
  - src/app/helpers.py
  - src/app/music_album_views.py
  - src/app/music_views.py
---

## Decided
- Artists, albums and podcast shows use the page's shared tracker dialog (fill_track.html via build_music_tracker_context / build_podcast_show_track_context, split from their renders; the views render with _render_track_shell). The web reads them on the same track route: `artist|album/music/{id}` and `podcast/{source}/{podcast_uuid}` (api/track_screen.py tracker_context, build_tracker_screen). Songs and podcast episodes use fill_track_song.html (a play-history list) and still open the page.
- artist/album/podcast_show save and delete answer JSON for Accept: application/json (helpers.wants_json; errors via helpers.form_errors, moved from save_views) and skip messages.* in JSON mode, so no stray toast appears on the next Django page.
- The tracker forms have no instance_id field. mediaStatusDateHandler.js counted every tracker as new and filled an empty end date with now on opening. fill_track.html now carries data-existing-entry; the script reads it only when the form has no instance_id field (the standard dialog is unchanged). The web dialog passes !tracked to initialState.
## Tried and ruled out
- A new route or empty `source` for trackers: the web builds /api/v1/track/{type}/{source}/{id}; "music" as the source of artist/album keeps one route and no web change.
## Watch out
- The dev Vite proxy must list every Django path the web posts to (/music/artist/save etc.); a missing one shows as "That did not save" locally only.
- Opening an artist's dialog (page or API) enqueues populate_album_tracks_batch; tests patch its .delay.
