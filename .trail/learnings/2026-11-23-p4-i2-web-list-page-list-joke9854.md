---
title: "P4-I2 web list page: list_detail screen API, extra-cards reset"
author: Joke9854
date: 2026-11-23
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/fork_urls.py
  - src/api/fork_views_details.py
  - src/api/scopes.py
  - src/lists/views.py
  - src/lists/views_smart_list.py
  - web/scripts/check-budgets.js
  - web/src/lib/api/schema.d.ts
---

## Decided
- `GET /api/v1/lists/page/<reference>/` reads `build_list_detail_context` (split from `lists.views.list_detail`) and reuses `library_screen._card`, `_Table(... table_type "list")`, `_bulk`, `_column_config`. Grid items go through `_adapt_list_items_for_table` too, so one card builder reads tracked and untracked items.
- Smart lists, read-only lists and missing lists answer `handled: false` + `django_url`; the web loader redirects there (I3 covers smart lists).
- Custom order uses `list_reorder_item` (first/back/next/last); it renumbers the whole list, so infinite scroll stays consistent.
- The grid's `LibraryCard` is lazy (`{#await import(...)}`) to keep the List page under the 115 kB budget (115.5 -> 112.9).

## Tried and ruled out
- Resetting the loaded-past-page-1 cards with `$effect(() => { void screen; extra = []; })`: the effect runs after the render, so a sort change briefly shows new page 1 + old extra cards and the keyed each throws `each_key_duplicate` (a 500 page in dev). Use a writable derived: `let extra = $derived.by(() => { void screen; return []; })`. Fixed on the Lists index too.

## Watch out
- Django `list_detail` and `smart_list_detail` built `bulk_action_data` with a trailing comma, making it a 1-tuple; the Django page's bulk menus read a JSON array and showed no options. Fixed with a comment.
- In the browser pane, clicking a button inside a closed `<details>` by ref clicks whatever is underneath (a card link). Open the menu first.
