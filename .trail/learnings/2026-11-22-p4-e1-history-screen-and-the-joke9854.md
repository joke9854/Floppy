---
title: P4-E1 History screen and the shared-CSS budget trap
author: Joke9854
date: 2026-11-22
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/fork_urls.py
  - src/api/fork_views_details.py
  - src/api/scopes.py
  - src/app/history_views.py
  - web/scripts/check-budgets.js
  - web/src/lib/api/schema.d.ts
  - web/src/lib/details/Sections.svelte
---

## Decided
- The web History screen reads the page's own context through build_history_context (split from history_views.history) at GET /api/v1/history/screen/; rows are built server-side as ct/history_row.html writes them, with the track dialog target for Edit tracking.
- history_day_fragment answers JSON (the screen's day shape) for Accept: application/json, for Load more.
- detailHref maps /history (any query) to the web screen; /history/sessions stays Django.

## Watch out
- New screens: Tailwind utility classes are compiled into the one global stylesheet every page loads; a handful of new ones put the Library (at its 110 kB budget) over. Put a screen's layout in its own CSS file.
- Importing Library modules (actions.ts, bits-ui DropdownMenu) from another page splits them into a shared chunk and grows the Library; the History row posts bulk_list_add directly and uses a native select.
- Svelte state seeded in $effect.pre is empty during SSR: use a writable $derived for lists that Load more replaces.
- Serializer names must be unique across the API (HistoryDay already existed): the screen's are HistoryScreen*.
