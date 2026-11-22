---
title: P4-F1 Calendar screen and moving detail strings out of the shell
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
  - src/events/views.py
  - web/scripts/check-budgets.js
  - web/src/lib/api/schema.d.ts
  - web/src/lib/details/EpisodeRow.svelte
---

## Decided
- The web Calendar reads the page's own context through build_calendar_context (split from events.views.calendar) at GET /api/v1/calendar/screen/; the type/status filter stays in the browser under the page's key yamtrack.calendar.filters.<user id>, so it holds on both pages.
- Detail- and person-only strings live in lib/details/strings.ts (dt); #lib/strings.ts keeps what more than those pages use. That gave every page ~0.6 kB back.

## Watch out
- The Library budget (110 kB) is shared-chunk sensitive: a new page importing a lucide icon the Library's own chunk uses (funnel, settings) splits it into its own file and tips the Library over. Pick icons the Library does not load, and run npm run budgets.
- A new route's ./$types needs npx svelte-kit sync before svelte-check (moving a route folder out and back drops them too).
- Seed browser-only state (the saved filter) with the page's default in a writable $derived, or SSR renders the empty state until hydration.
