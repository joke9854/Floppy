---
title: "P4-I3 web smart lists: post every rule back, serialize autosaves"
author: Joke9854
date: 2026-11-24
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/list_detail_screen.py
  - src/api/tests/test_list_page_api.py
  - src/lists/views.py
  - src/lists/views_recommendations.py
  - src/lists/views_smart_list.py
  - web/src/lib/api/schema.d.ts
  - web/src/lib/lists/lists.css
---

## Decided
- `/api/v1/lists/page/<ref>/` serves smart lists for editors via `build_list_detail_context(..., smart_context=True)` -> `build_smart_list_detail_context` (split from `_smart_list_detail_response`; the Django render path is unchanged). It adds `smart`: every saved rule (`SMART_FILTER_DEFAULTS` keys + media_types), summary chips, and builder options (`_filter_options({"filter_data": smart_filter_data})` reuses the Library filter shape).
- The web builder reuses the Library's LazyFilterMenu for the shared rules (map with `rulesFilters`/`applyRuleChanges` in `lib/lists/smart.ts`); a "Ranges & Lists" panel covers rating min/max, release/date-added ranges and windows, linked lists.
- Edit mode is page state, not URL: the preview is the saved rules after each save (`invalidate` via `refresh()`).
- Recommendations and Activity History are lazy dialogs on the list route (no new routes: every route costs the other pages' budgets). Add Recommendation stays the Django search page.

## Tried and ruled out
- A response counter for autosave: the risk is a stale *write* landing last, not a stale read. `saveQueue` keeps one request in flight and only the latest pending.

## Watch out
- `smart_rules_update` rebuilds `smart_filters` from the payload with defaults: post every rule back, or the ones left out are cleared. Test: post the screen's rules unchanged, compare `normalize_rule_payload` before/after (raw `smart_filters` differs because a save writes every key).
- `CustomList.can_recommend` is a method (templates call it implicitly); `bool(custom_list.can_recommend)` is always true.
- A Svelte variable named `state` breaks the `$state` rune in the same component.
- `str.replace` on a shared trailing line (`failed: '...'\n};`) hit the first strings object in strings.ts, not `ld`; anchor on a line unique to the target.
