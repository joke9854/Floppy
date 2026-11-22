---
title: P4-D5 Collection tab in the web track dialog
author: Joke9854
date: 2026-11-22
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/tests/test_track_screen_api.py
  - src/api/track_screen.py
  - src/app/collection_views.py
  - web/src/lib/api/schema.d.ts
  - web/src/lib/track/TrackDialog.svelte
  - web/src/lib/track/TrackDialog.svelte.spec.ts
  - web/src/lib/track/strings.ts
---

## Decided
- The web Collection tab reads the page's collection_context (build_collection_modal_context) as the track screen's `collection`; the page has it for single episodes only, so the season/episode audit lists are never sent.
- Existing-copy summaries are built server-side as strings (_collection_entry_lines), matching collection_entry_summary.html with show_date=False; title_preserve_acronyms turns Blu-ray into Blu-Ray, as on the page.
- collection_add / collection_remove answer JSON for Accept: application/json before any messages.success; HX-Request answers are unchanged.

## Tried and ruled out
- Reusing track_screen._field for CollectionEntryForm: the form swaps only the widget to Select and keeps a CharField, so bound.field.choices raises; _collection_field reads widget.choices.

## Watch out
- Checkbox fields (is_3d, custom checkbox) are read by presence (`name in POST`): the web must omit them when unticked, never post =false or empty.
- The Django track_modal URL takes the season number in the path and episode_number as a query param.
- The dev Vite proxy forwards /collection/ for add and remove.
