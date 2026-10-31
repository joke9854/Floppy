---
title: Episode track button OOB renders from the Episode model
author: Joke9854
date: 2026-10-31
branch: CineTrack-API
cost: { minutes: 16, tokens: 112512 }
touches:
  - src/app/save_views.py
  - src/app/tests/views/test_crud.py
  - src/config/tests/test_login_required.py
  - src/config/urls.py
---

## Decided
- Season-page track buttons are rendered from provider metadata dicts on page load, but every OOB re-render (episode_save, media_delete, episode_history_poll) passes the `Episode` model. `save_views._render_episode_track_buttons_oob` copies media_type/media_id/source/season_number/episode_number/library_media_type from `episode.item` onto the instance and passes `detail_return_url` (the request's `next`, or the season `media_url` for the poll).
- Local non-prod static is served by `django.contrib.staticfiles.views.serve` with `insecure=True` so package static (django_select2, admin) resolves through the finders.

## Tried and ruled out
- Passing only `episode_number` in the context: `media_view_url` and `component_id` return "" for any object without `source`/`media_type`, so the swapped button also lost its hx-get and hx-target.

## Watch out
- The season-progress/track-action fragment in the same response also contains the return URL, so count assertions on `"return_url": ...` alone see 3, not 2. Assert on the return_url + episode_number pair.
- The page's own render puts `?org.htmx.cache-buster=...` into the button's return_url (detail_return_url comes from the secondary-content htmx request path). Not fixed.
