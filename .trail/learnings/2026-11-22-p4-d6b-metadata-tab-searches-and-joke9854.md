---
title: P4-D6b Metadata tab searches and pickers
author: Joke9854
date: 2026-11-22
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/tests/test_track_screen_api.py
  - src/api/track_screen.py
  - src/app/helpers.py
  - src/app/metadata_sync_views.py
  - src/app/music_album_views.py
  - src/app/music_views.py
  - web/src/lib/api/schema.d.ts
---

## Decided
- The Metadata tab's searches answer JSON from the page's own search views ({results}); the select views (remap, library move, Hardcover edition, MusicBrainz release) are wrapped with helpers.answers_json, which turns the flash messages they queue into {saved, message|error, location} and clears them so the next page does not flash them.
- A library move answers the destination page as location; the web navigates there through detailHref.

## Watch out
- Django's test client replaces a URL's own query string when given a data dict: append q to search_url instead.
- music_release_picker in the album tracker context now carries save_url (set_music_release).
