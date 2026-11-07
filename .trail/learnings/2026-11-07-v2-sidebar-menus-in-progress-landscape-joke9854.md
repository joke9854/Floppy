---
title: "v2 sidebar menus stuck open after boosted navigation; In Progress row landscape cards and backdrop warming"
author: Joke9854
date: 2026-11-07
branch: CineTrack-API
touches:
  - src/templates/app/components/ct/shell_nav.html
  - src/templates/app/components/ct/home_grid.html
  - src/templates/app/components/ct/progress_card.html
  - src/app/backdrops.py
  - src/app/tasks.py
  - src/app/templatetags/app_tags.py
---

## Decided
- The ct sidebar menu panels start hidden with an inline `style="display: none"`, not `x-cloak`. After an hx-boost body swap, htmx's settle step puts the server-rendered `class`/`style` back on elements whose `id` matches the old page (`htmx.config.attributesToSettle`). That wiped the `display: none` Alpine's `x-show` had just set. Every panel showed while Alpine still held `open: false`, so it looked stuck until a reload.
- On v2 Home, any in-progress TV/season/anime entry gets the landscape progress card. The check button and "S E · N left" appear only when `ct_next_episode` finds an episode to mark. Otherwise the card shows the release year, as the poster card does.
- `ct_card_backdrop` stays cache-only. On a true miss (no key at all; a cached `IMG_NONE` is a known absence) it queues `app.tasks.fetch_backdrop` via `backdrops.queue_backdrop_fetch`. That runs on commit, deduplicated for an hour, so the next render has the wide image.

## Tried and ruled out
- Setting `htmx.config.attributesToSettle` globally without `style`: rejected because it would change settle for every swap in both themes, including inline-width progress bars.

## Watch out
- Any other `x-show` element with an `id` that survives a boosted swap has the same hazard. Render it hidden inline.
- A fully watched season drops out of the default Home rows, so a "caught up" card is easier to test by rendering `ct/home_grid.html` with a `HomeRowEntry(show_progress_controls=False)`.
- Under TestCase, `transaction.on_commit` callbacks never run. Use `captureOnCommitCallbacks(execute=True)` to exercise the backdrop queue.
