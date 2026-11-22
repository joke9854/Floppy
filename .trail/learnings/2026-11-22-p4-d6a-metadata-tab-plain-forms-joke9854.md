---
title: P4-D6a Metadata tab plain forms in the web track dialog
author: Joke9854
date: 2026-11-22
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/tests/test_track_screen_api.py
  - src/api/track_screen.py
  - src/app/metadata_sync_views.py
  - web/src/lib/api/schema.d.ts
  - web/src/lib/track/CollectionTab.svelte
  - web/src/lib/track/TrackDialog.svelte
  - web/src/lib/track/TrackDialog.svelte.spec.ts
---

## Decided
- The web Metadata tab (D6a) reads the track context's provider, language, image and manual metadata form as the track screen's `metadata`; the searches and identity-changing conversions are later slices.
- image_url is part of the General form on the page (form= attribute), so the web adds metadata.image.field to the General form state: untouched it posts the current image (no change), and an untracked title saves it on Add.
- ManualMetadataForm is prefixed: the API sends bound.html_name (metadata-<field>) and the JSON arm re-prefixes error keys.

## Watch out
- metadata_item is None for a title not in the DB yet: only the image section applies then.
- Custom date fields have widget input_type 'date' but _kind returns text; _metadata sets kind=date.
- The local throwaway Django runs with --noreload: restart it after server edits before checking in the browser.
