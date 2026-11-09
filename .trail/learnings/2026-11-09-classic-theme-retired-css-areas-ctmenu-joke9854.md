---
title: "Classic theme retired: CineTrack only, input.css split into areas, menus on ctMenu"
author: Joke9854
date: 2026-11-09
branch: claude/wonderful-wozniak-239340
touches:
  - src/users/migrations/0140_cinetrack_only_theme.py
  - src/templates/base.html
  - src/static/css/input.css
  - src/static/css/areas/
  - src/app/tests/test_theme_tokens.py
---

## Decided
- CineTrack is the only theme. `users.0140` moves every account to `cinetrack`; `ThemeChoices` has one value. Palettes, theme picker, header light/dark toggle and custom palette editor are gone. The `custom_theme` column is kept, unused, so the upgrade deletes no data.
- `<html>` always has class `cinetrack`. `ct_shell` (base.html) now means only "signed in and not a public view": it gates the v2 nav chrome. Public/anonymous pages (public lists, `?public_view=1` detail links, user profiles) still render their non-shell markup, so `{% if ct_shell %}` branches in templates reachable publicly are intentional, not leftover classic code.
- Non-v2 media types (games, books, music, comics, podcasts) keep the generic detail layout: `ct_v2_detail_type` is about media type, not theme.
- `uses_ct_home_cards` keeps the `CT_HOME_VIEWS` url-name check: detail recommendations of non-v2 types still use the plain card.
- `input.css` is an entry of `@import`s; rules live in `static/css/areas/*.css` in cascade order. Tests that inspect CSS must use `app.tests.test_theme_tokens.stylesheet_source()`, which inlines the imports.
- v2 dropdowns use `x-data="ctMenu"` with `@keydown.escape="close()" @click.outside="close(false)" @focusout="onFocusOut($event)"` and `x-ref="toggle"`/`x-ref="panel"`. Discover's More-types pill stays inline (its panel must sit outside the clipped `.ct-type-switch`).

## Tried and ruled out
- A shared `ct/menu.html` partial: Django includes have no slots and the menus' trigger/panel markup differs; not worth the contortion.

## Watch out
- Running Django tests from several agents at once on this Windows machine deadlocks at "Creating test database"; run them serially. `FLOPPY_TEST_FAST_DB=1` is fast (~80 s for ~440 tests) but skips data migrations, so tests needing migration-created rows (e.g. the built-in `cinetrack` OAuth app from `integrations.0049`) fail only in fast mode.
- `django.setup()` with `config.settings` retries Redis forever when Redis isn't running; use `config.test_settings` for template-compile checks.
- `logo_style` no longer shows anywhere for signed-in users: the logo lived only in the deleted classic sidebar.
- The repo is not `ruff format` clean at HEAD; don't reformat files you didn't otherwise change.
