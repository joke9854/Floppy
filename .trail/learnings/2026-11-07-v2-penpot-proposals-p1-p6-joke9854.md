---
title: "v2 Penpot proposals P1–P6: Discover ⋮ and Hidden view, settings nav, log-out confirm, Lists menu, Home row menu, detail ⋮ on desktop"
author: Joke9854
date: 2026-11-07
branch: CineTrack-API
touches:
  - src/templates/app/components/ct/discover_header.html
  - src/templates/app/components/discover_rows.html
  - src/templates/app/components/ct/logout_confirm.html
  - src/templates/app/components/_scrollable_row.html
  - src/templates/app/components/detail_action_buttons.html
  - src/templates/app/components/detail_lists_button.html
  - src/users/home_screen.py
  - src/app/templatetags/app_tags.py
---

## Decided
- P1/P7: the detail ⋮ applies at every width (dropdown from md, bottom sheet on phones). Menu labels come from each item's `title` attribute. Add to list lives in `detail_lists_button.html`, rendered beside ⋮ in v2 and after Tags in classic (a test asserts the classic order).
- P2: the Home row menu posts to `update_home_screen_row_view` (`users.home_screen.update_home_row_view` validates the sort against the row's allowed choices and the progress filter via `validate_library_row_filters`).
- P6: the log-out confirmation is `ct/logout_confirm.html`, `x-teleport`ed to `<body>` because the glass tab bar's backdrop-filter traps fixed children; its ids come from Alpine `$id` because two copies render (More sheet and rail menu).
- More-sheet counts (`ct_more_counts`) are cached per user for 60 s. Stats hours and History "Today" were skipped: there is no cheap per-page source.
- Emby/Kodi/Stremio "last play received" needs a migration; deferred to a Todo on project #2.

## Tried and ruled out
- Hiding Collection when empty (P1): its empty state holds the only "Add collection data" button, so it needs a ⋮ entry first.

## Watch out
- A view that re-renders a Home row must be listed in `app_tags.CT_HOME_VIEWS`, or the row comes back with classic cards and header.
- Tailwind utilities win over `input.css` component rules regardless of specificity; in v2, drop the utility classes instead of overriding them.
- A negative horizontal margin on an inline-flex child shrinks its flex parent's content width and truncates the text inside.
- `users.helpers.is_first_run` caches "no users" for 60 s; a test that creates a user and renders the login page must delete `IS_FIRST_RUN_CACHE_KEY`.
- In Git Bash, `/path` arguments to Python scripts are rewritten to Windows paths; set `MSYS_NO_PATHCONV=1`.
