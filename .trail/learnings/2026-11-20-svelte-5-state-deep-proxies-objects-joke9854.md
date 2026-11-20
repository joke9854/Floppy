---
title: "Svelte 5 $state deep-proxies objects: identity checks need $state.raw"
author: Joke9854
date: 2026-11-20
branch: CineTrack-API
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
  - web/scripts/check-budgets.js
---

## Decided
- Web state that remembers which data it belongs to (`{ for: data.x, ... }` then `state.for === data.x`) is `$state.raw`. `$state` deep-proxies plain objects, so `state.for` is a proxy that never `===` the original; the derived falls back silently.
- Applied in the Library (`more`, infinite scroll) and the detail page (`fresh`, `resolved`, `seasonState`, `heroDone`, `trailers`).
## Tried and ruled out
- Trusting the earlier screenshots: the Library had 6 movies (one page), so the bug never showed until 46 were seeded. Seed more than one page (32) when testing lists.
## Watch out
- Symptom: data is fetched (network shows page 2, trailers 200) but never appears; nothing errors.
- The pane's browser can run as a hidden background page where IntersectionObserver does not fire; check scroll behaviour in headless Chromium (Playwright) instead.
- Bundle budgets (web/scripts/check-budgets.js) count static imports only: put what appears later (menus, dialogs, the sections below a hero) behind `import()` to stay inside 110 kB.
