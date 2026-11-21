---
title: "P4-D1 web track dialog: JSON mode, exact play times, bundle budget"
author: Joke9854
date: 2026-11-21
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - web/src/lib/csrf.ts
  - web/src/lib/library/BulkBar.svelte
  - web/src/lib/library/CardMenu.svelte
  - web/src/lib/library/ColumnMenu.svelte
  - web/src/lib/library/LazyColumnMenu.svelte
  - web/src/lib/library/LibraryCard.svelte
  - web/src/lib/library/LibraryTable.svelte
  - web/src/lib/library/ViewMenu.svelte
---

## Decided
- The web track dialog posts the Django page's own endpoints (/media_save, /episode_save, /media_delete, /media_rewatch) with Accept: application/json; helpers.wants_json() switches those views to JSON only when the request is not HTMX, so the Django page and HTMX paths are unchanged.
- The dialog's fields come from GET /api/v1/track/<type>/<source>/<id> (src/api/track_screen.py), built from the same form and context the Django dialog renders (build_standard_track_context).
- Django's BaseForm.get_initial_for_field zeroes microseconds for widgets without supports_microseconds, so pressing Update rewrote synced play times. ExactPlayDatesMixin (src/app/forms.py) keeps start_date/end_date exact; it is the first base of every track form.
## Tried and ruled out
- Putting the dialog strings in lib/strings.ts: that module is in every page bundle and pushed pages over 110 kB. Lazy-only strings live in lazy modules (lib/track/strings.ts, lib/library/menu-strings.ts).
- Rendering TrackHost from the app layout: it lands in every page bundle. openTrack() mounts it into document.body on first use.
## Watch out
- Library page is at 109.9 of 110 kB; anything new there must load lazily.
- Never name a Svelte 5 variable state (clashes with the $state rune).
- Select fields: BoundField.value() can be a list; the API sends str(value).
