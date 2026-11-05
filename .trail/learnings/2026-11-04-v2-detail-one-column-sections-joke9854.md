---
title: "v2 Detail pages: one-column ct sections, client-driven primary action"
author: Joke9854
date: 2026-11-04
branch: CineTrack-API
touches:
  - src/templates/app/components/ct/detail_hero.html
  - src/templates/app/components/ct/detail_secondary.html
  - src/templates/app/components/ct/episode_row.html
  - src/templates/app/components/ct/episode_sections.html
  - src/templates/app/components/ct/watch_on.html
  - src/templates/app/components/detail_secondary_content.html
  - src/templates/app/episode_details.html
  - src/app/providers/tmdb.py
  - src/app/templatetags/app_tags.py
  - src/static/js/ctShell.js
  - src/static/css/input.css
---

## Decided
- Phase 3 (Apple layout v2, boards A2/A7/A10/A11) is CineTrack only. Movies, shows, seasons and anime get the v2 hero (`ct/detail_hero.html`, gated by `ct_v2_detail_type`); other media types keep the W3 hero.
- The detail sections are `ct/detail_secondary.html`, branched at the top of `detail_secondary_content.html`, because the season and media views render that partial directly for `?fragment=secondary`. The history and collection blocks were extracted unchanged into `detail_history_section.html` and `detail_collection_section.html` so both layouts share them.
- The show page loads the selected season's episodes from that season page's own `?fragment=secondary` with `hx-select="#ct-episode-list"`, so rows, ids and track buttons are the season page's. No new backend data.
- The primary "Mark Sx Ey Watched" button is client-driven (`syncMarkNext` in `ctShell.js`): it marks the first `[data-ct-episode-check][data-watched='0']` on the page, exactly as W does, and relabels on `htmx:afterSettle`.
- "Watch on" comes from `tmdb.watch_on_providers`: subscription (flatrate/free), then rent/buy, then TMDB's JustWatch link. TMDB gives no prices, so a chip names the offer only.

## Tried and ruled out
- A server-side next episode via `TV.next_episode_target()` for the button: it depends on local Event rows (empty on the preview DB), and the shell render has no episode list.

## Watch out
- The shell (non-fragment) render reads `stored_metadata_fallback`, which has no `providers`, runtime or certification, so "Watch on" falls back to `Item.watch_providers`.
- `detail_section_attrs` emits an inline `order`, so `.ct-detail-sections` uses block flow, not flex, to keep the mockup's order.
- Filter arguments inside `{% url %}` must resolve: `media.source|default:source` raises VariableDoesNotExist when `source` is not in the context.
