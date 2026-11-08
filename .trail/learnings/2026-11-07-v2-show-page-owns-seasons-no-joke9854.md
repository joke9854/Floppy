---
title: "v2 show page owns seasons: no season page, season info modal, TVDB character photos"
author: Joke9854
date: 2026-11-07
branch: claude/sad-varahamihira-8cc9c9
cost: { minutes: 1, tokens: 2363 }
touches:
  - src/app/home_sections.py
  - src/app/season_details_views.py
  - src/app/templatetags/app_tags.py
  - src/app/tests/test_home_sections.py
  - src/app/tests/test_templatetags.py
  - src/app/tests/views/test_media_details.py
  - src/app/views.py
  - src/static/css/input.css
  - src/static/css/main.css
  - src/static/js/ctShell.js
---

## Decided
- There is no season page. `season_details` redirects every non-fragment GET to the show page with `?season=N` (other query params kept); its `?fragment=secondary` still renders the season and is what the show page loads into `#ct-episode-list`. `app_tags.media_url` and the episode page's `season_url` use `season_page_url()` to skip the hop.
- The show page picks the selected season from `request.GET.season`, else the next episode's season; pills push `?season=N`.
- Per-season "X of Y episodes watched" is `series_progress_card.html` inside the season fragment (`id=ct-season-progress`, `data-ct-live-src` = the fragment URL). The `ctShell.js` live refresh groups `[data-ct-live]` parts by `data-ct-live-src`. The header shows only "X% watched" (`#ct-show-percent`, always rendered, `hidden` at 0 so the refresh can fill it in).
- Season info modal: each pill's info button `htmx.ajax`es the season fragment with `select: '#ct-season-info'` into one teleported dialog; the fragment renders that block in a `hidden` wrapper.
- The Characters tab uses TVDB character pictures via `ct_character_images` (existing `tvdb.character_images`, cached a week), matched to the TMDB cast by actor name; Cast keeps the TMDB photo.
- Home "Airing This Week" rows link to the episode (`AiringEntry.url`).
## Tried and ruled out
- A `max-width` on the flex-basis-100% episode overview: it clamps the flex basis, so the overview sat beside the row on wide screens. The measure now comes from right padding.
## Watch out
- A title's first Characters render reads TVDB once (0.5-1.9 s) inside the secondary fragment.
- Locally, FileBasedCache on Windows can 500 under concurrent requests (WinError 32); not app code.
- Tailwind CLI is the main checkout's `node_modules/.bin/tailwindcss`; rebuild main.css after input.css edits.
- P8 Trailers (approved without the Photos row): `?fragment=trailers` on movie/show pages renders `ct/trailers.html` from `carousel.resolve_trailers` (title videos, then the 6 newest seasons' trailers/teasers; TMDB carousel payloads now carry `videos`, cache key `tmdb_carousel_v2_`). The hero Trailer button is an OOB swap into `#ct-trailer-slot`, so it only shows when a trailer exists.
- On Windows, `runserver` can share a port with a stale earlier server (SO_REUSEADDR); kill by port listener before trusting a restart.
- Detail hero: the watch button is always green (`--ct-status-completed`), untracked movies get one-click Mark Watched, the backdrop is the sharp landscape art under a light veil (no poster fallback). "Watch on" falls back to the browser's country when the user's region is UNSET, and the secondary fragment OOB-fills `#ct-watch-on` because the shell has no providers for untracked titles.
- `IMG_NONE` stays the persisted value; `image_url` renders it as `static/img/ct-placeholder.svg`, and a CSS `content:` rule catches templates that print it raw (not Firefox).
- P9 person page: `ct/person_page.html` behind `ct_shell` in `person_detail.html` (classic body kept for other themes); Known For = most-voted cast credits; filmography tabs/sort/cap are CSS + Alpine only.
