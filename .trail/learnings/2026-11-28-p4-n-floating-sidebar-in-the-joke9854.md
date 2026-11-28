---
title: "P4-N: floating sidebar in the web shell"
author: Joke9854
date: 2026-11-28
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/fork_views_users.py
  - src/api/tests/test_fork_users.py
  - web/src/lib/api/schema.d.ts
  - web/src/lib/shell/NavLink.svelte
  - web/src/lib/shell/Shell.svelte
  - web/src/lib/shell/ShellHost.test.svelte
  - web/src/lib/shell/shell.svelte.spec.ts
---

## Decided
- `GET /api/v1/user/sidebar/` carries `sidebar_style` and `floating_sidebar` (web-only endpoint, not in openapi.yaml, not used by CineTrack). The (app) layout loader `depends('floppy:settings')`, which Appearance already invalidates, so the shell switches without a reload.
- The lg modes live in one plain-CSS block, `web/src/lib/shell/shell.css`, keyed on `data-ct-sidebar` / `data-ct-floating` on `nav.ct-rail` (as Django's shell.css), with semantic classes (ct-rail-link, ct-rail-label, ct-rail-section, ct-shell-content...). Below lg the Tailwind md classes are untouched.
- Hover mode stays open while a portalled menu is open: `:has([data-state=open])`.
## Tried and ruled out
- A Tailwind v4 `@custom-variant wide`: the long selector is repeated for every utility, +0.5 kB gzip on every page (Detail, List, Podcast went over 115).
## Watch out
- Tailwind 4's `sr-only` hides with `clip-path: inset(50%)`; a hand-written un-hide must reset `clip-path: none` (resetting `clip` alone left every label invisible).
- Elements styled through a shared class constant (Shell's `railButton` for the More and account menu triggers) need the semantic class too.
- Budgets after P4-N: List 115.0 (at the limit), Detail and Podcast 114.8, Library 114.5. P4-M and P4-O need headroom work or an agreed raise first.
