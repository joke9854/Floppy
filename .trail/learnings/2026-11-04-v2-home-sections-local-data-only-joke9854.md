---
title: "v2 Home: fixed sections from local data, cache-only backdrops"
author: Joke9854
date: 2026-11-04
branch: claude/web-v2-home-16edba
touches:
  - src/app/home_sections.py
  - src/app/views.py
  - src/app/templatetags/app_tags.py
  - src/templates/app/home.html
  - src/templates/app/components/_scrollable_row.html
  - src/templates/app/components/home_rest_fragment.html
  - src/templates/app/components/ct/home_sections.html
  - src/templates/app/components/ct/progress_card.html
  - src/static/css/input.css
---

## Decided
- Home phase 2 (Apple layout v2, boards A1/A6) is CineTrack only. The user-configured rows keep their data and get a v2 heading (title, muted sort toggle, "See All"). Airing This Week, Recently Watched and the header's catch-up count are fixed sections in `app/home_sections.py`, rendered at the top of `home_rest_fragment`.
- The sections read only local data: `Event.objects.get_user_events` for the week, episode/movie `end_date` for recent watches, and aired events minus distinct watched episodes for the catch-up count. They are cached per user and day under the `home_row` registry, so `clear_home_row_cache_for_user` clears them with the rows.
- The finale tag reuses `events.notifications.annotate_finale_events` (highest known episode = finale); premiere is E1.
- In Progress cards are 16:9 and read the backdrop from the cache only (`ct_card_backdrop` → `backdrops.cached_backdrop`). A miss shows the poster cropped; Home never waits on TMDB.

## Tried and ruled out
- `resolve_backdrop` on Home: a cold cache means one TMDB call per card on the first group.
- A "Synced with Plex" subtitle: no such timestamp exists (only the Plex watchlist sync time).

## Watch out
- The local preview DB has almost no Event rows, so Airing is empty and the catch-up count is 0 there. Production stores every episode with an air date (`events/calendar/tv.py`).
- `user_event_time` returns "at 21:00"; the airing row slices off the "at ".
- Locally, `/home/rest/` takes 35–47 s because the existing rows call TMDB on the preview DB. That is not the sections; verify with a `requests.Session.request` spy.
