---
title: Album tracklist rebuilds must keep Track rows (plays link via SET_NULL)
author: Joke9854
date: 2026-11-15
branch: CineTrack-API
cost: { minutes: 36, tokens: 653175 }
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
  - docs/plans/floppy-v2.md
  - docs/plans/p1-api-inventory.md
  - src/api/contracts/openapi-full.yaml
  - src/api/fork_urls.py
  - src/api/fork_views_list_imports.py
  - src/api/scopes.py
  - src/api/tests/test_list_imports_api.py
  - src/app/tests/test_api_contracts.py
  - src/api/fork_views_list_actions.py
---

## Decided
- `Music.track` is `on_delete=SET_NULL`, and the tracklist is shared by every user. Never delete and recreate an album's Track rows: it unlinks every user's plays of that album.
- All rebuilds go through `services.music.replace_album_tracklist`, which keeps a Track row when its MusicBrainz recording id is still on the release and moves it to the new position. A track without a recording id is kept only at the same position. Only tracks whose recording is gone get deleted.
- `relink_album_plays(album)` links track-less plays by `item.media_id`, which is the recording id. It runs after every rebuild and after a duplicate-album merge, because `album.delete()` cascades the old tracks.
- The web "Sync album" body is now `services.music.resync_album`, which the API (`POST music/albums/{id}/resync/`) shares. When the group lookup finds nothing, it keeps the stored release.

## Tried and ruled out
- Matching old to new tracks by (disc, track number): another pressing reorders tracks, so plays would point at a different song.

## Watch out
- `unique_track_per_album_disc` applies only when `track_number` is not null. Null the kept rows' `track_number` before assigning final positions, or swapped tracks collide.
- `musicbrainz.get_release_for_group` swallows errors and returns None, so a MusicBrainz outage there looks like "no release".
- The per-user `MusicReleasePreference` still reshapes the shared tracklist for everyone.
