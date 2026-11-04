---
title: "v2 labelled sidebar: modes in CSS, scroll and preview gotchas"
author: Joke9854
date: 2026-11-03
branch: claude/web-v2-layout-5ea0ea
cost: { minutes: 1, tokens: 2614 }
touches:
  - src/app/tests/views/test_ct_shell.py
  - src/static/css/input.css
  - src/static/css/main.css
  - src/static/js/ctShell.js
  - src/static/js/searchShortcut.js
  - src/templates/app/components/ct/library_links.html
  - src/templates/app/components/ct/shell_nav.html
  - src/templates/base.html
  - src/templates/users/appearance.html
  - src/users/models.py
---

## Decided
- The v2 sidebar (Apple layout phase 1) is one `.ct-rail` nav in `ct/shell_nav.html`; its modes are CSS only, keyed on `data-ct-sidebar` (attached|floating) and `data-ct-floating` (hover|expanded|icons) from `User.sidebar_style` / `User.floating_sidebar` (migration 0138). Below lg it is always the compact icon bar; below md the bottom nav.
- Content padding moved from the template's `md:pl-[88px]` to `.ct-shell-content` in CSS, driven by the nav via the `~` sibling selector.
- From lg the ct top bar is hidden (search is the palette, `/` falls back to the palette) except on the Search page, which has no field of its own until phase 5.
- Library/Lists/More are inline in the sidebar; Collection/Tags/Add custom entry sit behind its More menu on desktop and in the A18 More sheet on phones.
## Watch out
- With many media types the wide sidebar must scroll: `.ct-rail-list` gets `overflow-y:auto`, so its items need `flex-shrink:0` or the `overflow:hidden` group labels collapse to ~1px. Side flyouts inside a scroller get clipped, so the More menu drops down inline in wide modes.
- Local preview on this Windows box: no Redis and no Playwright browser. Use a `src/local_serve.py` (gitignored) with a file cache, `memory://` broker and a copied preview DB, then `runserver`. Drive Playwright with `channel="msedge"` and wait on the URL, not `networkidle`, which never settles.
- `config.tests.test_gunicorn*` error on Windows (`os.sysconf`), and `check_migration_hygiene` needs an `upstream/dev` ref that the worktree lacks. Neither comes from app changes.
