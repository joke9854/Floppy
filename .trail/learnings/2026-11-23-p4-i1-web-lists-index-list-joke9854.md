---
title: "P4-I1 web Lists index: list form JSON, imports API, budget to 115 kB"
author: Joke9854
date: 2026-11-23
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/fork_urls.py
  - src/api/fork_views_details.py
  - src/api/scopes.py
  - src/lists/views_list_actions.py
  - src/lists/views_list_browse.py
  - web/scripts/check-budgets.js
  - web/src/lib/api/schema.d.ts
---

## Decided
- GET /api/v1/lists/screen/ reads build_lists_context (split from lists()); covers are the first four posters per list from one Window(RowNumber) query instead of the page's lazy list_cover_image per card.
- The web create/edit dialog posts to the Django form views (list_create, list_edit), which now answer JSON for Accept: application/json: list_edit_form returns every field and the dialog posts every field back, because CustomListForm saves all of them (a missing field is cleared, smart rules included). Edit errors come back per field (the page drops them silently). Collaborators go by exact username (collaborator_usernames, resolved to ids in the view) since the page's select2 search has no usable endpoint.
- Imports use the existing list imports API (session auth passes every scope check): CSV via lists/import (202 queued), MDBList and Trakt. The web always uses Trakt's device code flow, so it shows the OOB redirect URI.
- Page budgets went from 110 to 115 kB (the user's call): every new route grows the shared route table and re-splits shared code; an empty Lists route alone put Discover over.

## Tried and ruled out
- build.rollupOptions.output.manualChunks to keep the Svelte runtime in one chunk: this Vite build is Rolldown and ignores manualChunks when codeSplitting is set.

## Watch out
- Trakt and MDBList were only exercised up to their forms locally (no real credentials); check them on beta.
- Heredoc patterns that were grepped with blank lines filtered out miss the real file: anchor edits on text read with blank lines kept.
