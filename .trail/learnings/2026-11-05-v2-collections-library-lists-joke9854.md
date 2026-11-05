---
title: "v2 Collections: Library restyles the shared card, Lists splits mine/shared"
author: Joke9854
date: 2026-11-05
branch: CineTrack-API
touches:
  - src/templates/app/components/ct/library_header.html
  - src/templates/app/components/ct/library_status.html
  - src/templates/app/components/filter_toolbar.html
  - src/templates/app/components/filter_menu.html
  - src/templates/app/components/media_grid_items.html
  - src/templates/app/components/media_card_status_chip.html
  - src/templates/app/media_list.html
  - src/templates/lists/custom_lists.html
  - src/templates/lists/components/list_grid.html
  - src/templates/lists/components/ct_list_card.html
  - src/templates/lists/components/ct_list_cover.html
  - src/lists/views_list_browse.py
  - src/app/templatetags/app_tags.py
  - src/static/css/input.css
---

## Decided
- Phase 4 (Apple layout v2) is A3 Library · Shows, A16 Library (mobile) and A13 Lists, CineTrack only. A4 History, A12 Calendar, A14 Stats and A17 Calendar (mobile) are in no phase yet.
- The Library grid keeps the shared `media_card.html`, so hover actions and bulk select still work. `.ct-library-grid` restyles it in CSS: the title moves below the poster, the status chip becomes a 26px badge at top-right (colour from a new `data-status` on the chip icon), and the progress line is inset. The subtitle is `ct_library_subtitle`, which reads the next episode from the seasons and events the Library query already prefetches, so it adds no queries.
- The status segment (`ct/library_status.html`) and `filter_toolbar.html` (`ct_toolbar=True`) share `.ct-library-bar`. From md the toolbar's Status menu is hidden in favour of the segment; on phones it is the status pull-down (A16).
- Lists: `?scope=mine|shared` filters the page. CineTrack defaults to `mine`; other themes keep one combined grid. The CineTrack cover endpoint returns a strip of the first four item posters (`ct_list_cover.html`) instead of the TMDB/IGDB backdrop lookup.

## Watch out
- `ct_shell` exists only in full-page renders (set in `base.html`). Partials that HTMX re-renders, such as `media_grid_items.html` and `list_grid.html`, must test `user.theme == "cinetrack"`.
- The `.search-result-card …` rules come later in `input.css` with the same specificity, so the v2 card overrides need the extra `.search-result-card` class (and `[title]` on the title).
- On Windows, stopping a background `runserver` task can leave the Python process alive. Several processes can then listen on the same port and serve stale code: "count must be a number" from a view that was already fixed. Kill them by command line before restarting.
- Playwright full-page captures misplace the sticky ct top bar on phones. Use a viewport capture at scroll 0 for the side-by-side images.
- Preview-DB events make `next_episode_target()` return odd numbers (S1 E92). That is the data, not the tag.
