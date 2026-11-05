---
title: "v2 Discover and Search: mockup-first, hidden features logged both ways"
author: Joke9854
date: 2026-11-05
branch: CineTrack-API
touches:
  - src/templates/app/components/ct/discover_header.html
  - src/templates/app/components/ct/discover_hero.html
  - src/templates/app/components/ct/search_header.html
  - src/templates/app/components/ct/search_row.html
  - src/templates/app/components/discover_row.html
  - src/templates/app/search.html
  - src/static/css/input.css
  - docs/agents/v2_mockup_gaps.md
---

## Decided
- Phase 5 (Apple layout v2) is A8 Discover, A9 Search and A19 Discover (mobile), CineTrack only. From this phase on, live features the boards lack are hidden (template ct branch or CSS), not deleted, and logged in `docs/agents/v2_mockup_gaps.md`. That file also has a "Mockup parts not built" table for board features with no backend data (See All, hero overview/runtime/rank, Search "All"+counts, People).
- Discover rails reuse the shared `media_card.html` inside `.ct-rail-row.ct-library-grid`, so the Library card restyle applies and the hover actions (planning, hide, lists) stay. Each card is wrapped with a `ct-library-sub` "Type · Year" line.
- The hero's "Add to Planned" posts the existing `discover_action` `planning` with an empty `row_key`, which re-renders the whole `#discover-rows` fragment (hero included).
- Search has its own GET field, a type segment (`get_search_media_types`) and a Source segment shown only when a type has more than one source. Results are `ct/search_row.html` list rows; Add opens the same `track_modal` as the classic list card.
- The ct top bar is hidden on Discover and Search at every width (`main[data-ct-page]`); Discover phones get a search button that fires `ct-palette-open`.

## Watch out
- Flex rail items need `min-width: 0`: a nowrap title makes `min-width: auto` exceed `flex-basis`, and the card (poster included) stretches to the title's width.
- `.ct-page-bell` is hidden below md (Home's bell), so it cannot be reused for a phone-only button.
- `search.html` had two never-closed wrapper divs (djlint H025, preexisting); the `<div {% if %}class=…>` split-tag pattern hid them. Fixed by putting the whole tag in each branch.
- Discover candidates (`CandidateItem`) have genres and a release date but no overview, exact runtime or tracking state; don't fake them in the hero or cards.
