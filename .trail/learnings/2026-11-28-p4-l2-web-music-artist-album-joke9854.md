---
title: "P4-L2: web music artist, album and podcast show pages"
author: Joke9854
date: 2026-11-28
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/fork_urls.py
  - src/api/fork_views_details.py
  - src/api/scopes.py
  - src/app/media_details_views.py
  - src/app/music_views.py
  - web/scripts/check-budgets.js
  - web/src/lib/api/schema.d.ts
---

## Decided
- Three one-phase read endpoints, registered in api/fork_urls.py BEFORE the generic `details/<type>/<source>/<id>/` route (which would swallow them): `details/music/artist/<id>/`, `.../album/<id>/`, `details/podcast/<source>/<uuid>/?episode_page=N` (N>1 answers only the episodes page). Builders in api/details_media_screen.py.
- The Django renderers were split, not reimplemented: `build_music_artist_context`, `build_music_album_context`, `resolve_music_album` (music_views.py) and `build_podcast_show_context` (media_details_views.py). Page and API share them, so canonicalize/merge/sync behave the same. Any HttpResponse from them -> 400 `_REDIRECTED`, and the web loader falls back to the Django URL, which redirects.
- The podcast RSS refresh runs only on the page's first read (`refresh_feed=episode_page == 1`); it is an uncached 30 s request.
- Actions reuse existing JSON twins unchanged: tracker dialog (`track/artist|album|podcast`), `music/songs/plays`, `podcasts/episodes/plays`, `history/<music|podcast>/<history_id>` (the simple_history id, same as fill_track_song.html), sync-discography, albums resync.
- Web pages are their own routes (static `music` / `podcast` segments beat `[source]/[type]`), so each has its own bundle; budgets added at 115 kB (artist 113.3, album 113.7, podcast 114.1; detail page now 114.1).
## Watch out
- The music GETs make live MusicBrainz calls (get_artist, release, genre lookups): locally with made-up MBIDs the album read took ~18 s. Seed with discography_synced_at/members_synced_at=now and tracks_populated=True, and expect the slowness.
- Deleting a song's latest play (history delete) leaves Music.end_date on the deleted play, so the album/artist date range still ends there. Pre-existing, Django page too.
- record_song_play treats a play within 5 minutes of the last as a duplicate (201, no new history row).
- record_podcast_play needs `episode_uuid` passed explicitly, even with `episode=`.
- Browser pane: with resize_window emulation, ref clicks can land outside a dialog and close it; click via JS for dialog buttons.
