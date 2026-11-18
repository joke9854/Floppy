---
title: "P4-C1 web detail page: page builders split, three detail reads"
author: Joke9854
date: 2026-11-18
branch: CineTrack-API
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
  - src/api/details_screen.py
  - web/src/lib/details/link.ts
---

## Decided
- `build_media_details_context(request, ..., secondary=bool)` and `build_season_details_context(...)` are split from `media_details` / `season_details`; the views keep the carousel/trailer fragments and the render. The API (`src/api/details_screen.py`) reads the page's own context, so it matches the page.
- Three reads: `/api/v1/details/{type}/{source}/{id}/` (hero, shell phase, caches only), `.../sections/` (secondary phase, may hit the provider), `/api/v1/details/tv/{source}/{id}/season/?season=N` (one season; runs the show's shell phase, warm after sections). Scope NEVER: the page's GET can store resolved metadata.
- The v2 sections (`.ct-detail-sections`) are `display: block`, so the user's detail layout only hides sections; `order` never moves them. The API returns visible keys in template order.
- Movie Mark as watched posts the Django `media_save` form (save_as_new_entry, ctWatchNow wall time), not `/api/.../watch/` (that adds a MoviePlay instead of the Completed row the page creates).
- Web card links go through `detailLink()` (`web/src/lib/details/link.ts`): movie/show pages in place with preload on tap; everything else full load.
## Tried and ruled out
- Reading hero meta from the shell context alone looked broken locally (no genres/year): the shell uses `stored_metadata_fallback` (Item fields only) once `metadata_fetched_at` is set; the Django hero shows the same, so it is parity, not a bug.
## Watch out
- A form submit before hydration posts an empty CSRF token and time; Floppy's CSRF failure answers 302 to `/`, not 403. Disable such buttons until mounted.
- Locally Vite proxies only /api, /_allauth, /accounts, /static, /image-cache; a Playwright forward of /media_save to :8001 must send Django's own Origin or CSRF origin checking rejects it.
- Test fixtures returning metadata must deep-copy per call: the page enriches `related` lists in place. `next_episode_target` needs calendar `Event` rows to see aired episodes.
- The throwaway `runserver --noreload` needs a restart after API edits.
