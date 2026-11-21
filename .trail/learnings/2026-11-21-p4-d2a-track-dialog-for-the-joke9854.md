---
title: "P4-D2a track dialog for the other standard types: card targets, anime pk, game time"
author: Joke9854
date: 2026-11-21
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/fork_urls.py
  - src/api/fork_views_details.py
  - src/api/library_screen.py
  - src/api/tests/test_track_screen_api.py
  - src/api/track_screen.py
  - src/app/services/bulk_episode_tracking.py
  - src/app/templatetags/app_tags.py
---

## Decided
- Library cards carry `track` (api/library_screen.py `_track_target`): the kwargs the page's own card button reverses (`app_tags.media_view_kwargs("track_modal", item)`) plus the entry as `instance_id`. The web dialog opens exactly that; no URL parsing on the web.
- Django opens a TMDB show filed as anime as media_type `anime` (route_media_type, set only in the anime list). `get_media(user, "anime", pk)` tries the Anime table first, so a MAL anime with the same pk opens instead: the card drops `instance_id` whenever the route type differs from the item's type, and the builder finds the show by media_id.
- Game progress is text ("3h 35min", minutes_to_hhmm); the web ports syncStartDateFromProgress as `settle()` in lib/track/rules.ts: rerun on any change to progress or end, never on opening an edit.
- A manual anime's metadata has `related.seasons = None`; `_standard_grouped_domain` crashed (Django page too). Guarded with `or []`.
## Tried and ruled out
- `django.urls.resolve(media_view_url(...))` to get the kwargs: breaks under BASE_URL (FORCE_SCRIPT_NAME). Split `media_view_kwargs` out instead.
- Widening the web URL regex for targets: Django's route takes `<path:media_id>`, and the anime route type differs from the card's type.
## Watch out
- Percent mode (books/comics/manga) rounds to 0.1%: books over 1000 pages can gain or lose a page on an untouched Update (337/1500 -> 22.5% -> 338), in Django too.
- The track API route takes `media_id` as `.+?` (IDs with slashes).
- Chrome draws number inputs in the browser locale ("9,0"); the posted value stays "9.0".
