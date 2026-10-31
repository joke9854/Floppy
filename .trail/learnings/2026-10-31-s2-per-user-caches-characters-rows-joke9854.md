---
title: "S2 per-user caches: characters rows and Home row TTL"
author: Joke9854
date: 2026-10-31
branch: CineTrack-API
cost: { minutes: 47, tokens: 356370 }
touches:
  - src/api/tests/test_zz_scratch_ensure.py
  - ".gitattributes"
  - src/api/fork_urls.py
  - src/api/fork_views_tracking.py
  - src/api/serializers.py
  - src/api/tests/test_fork_tracking.py
  - src/app/media_list_filters.py
  - src/integrations/tests/mock_data/import_yamtrack.csv
  - src/integrations/tests/mock_data/import_yamtrack_with_lists.csv
  - src/static/img/anilist-logo.svg
---

## Decided
- CineTrack characters endpoint: cache the computed rows in `tvdb.character_images` (7 d, `tvdb.characters_cache_key`), not in `api/`. The provider calls under it were already cached; prod slowness was cold or 12 h-expired TVDB extended payloads.
- Refresh invalidation goes through `tvdb.metadata_cache_keys` / `tmdb.metadata_cache_keys`; refresh callers `delete_many` the whole list and read only `keys[0]` (the TTL guard), so append extra keys at the end. The TMDB side looks up the TVDB id from the cache only, never the network.
- Home rows (`cache_utils.HOME_ROW_CACHE_TTL`) went from 60 s to 10 min (user choice). `clear_media_list_cache_for_user` now also clears Home rows, and Discover quick actions (saves with cache signals suppressed) clear both.
## Tried and ruled out
- A per-request hotspot on a Home miss: none; misses are 12-28 queries, and the lever is how often they happen.
## Watch out
- The 60 s TTL used to hide missing invalidation: preference changes and item title/metadata refreshes still don't clear Home rows (up to 10 min stale, accepted).
- Home config save recreates rows with new ids, so old row keys go stale on their own.
