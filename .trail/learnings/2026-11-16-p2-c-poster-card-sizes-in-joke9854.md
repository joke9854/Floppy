---
title: P2-C poster card sizes in the image cache
author: Joke9854
date: 2026-11-16
branch: CineTrack-API
touches:
  - ".github/workflows/cinetrack-targeted.yml"
  - docs/plans/floppy-v2.md
  - docs/plans/p2-backend-foundations.md
  - src/app/image_cache.py
  - src/app/templatetags/app_tags.py
  - src/app/tests/test_image_cache.py
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
---

## Decided
- P2-C card sizes cover only non-TMDB images (fanart.tv, TVDB, IGDB, MAL...): TMDB already serves sizes. /image-cache/<token>?w=N makes a copy on first request, stored as <key>.<version>.wN.img; version = original content-hash prefix + VARIANT_RECIPE.
- Templates did not change: tmdb_size returns SizedImageUrl (str subclass carrying card_width) for non-TMDB URLs, image_url passes the width on, tmdb_srcset lists the copies.
- Only ?v= equal to the current version gets immutable caching; a failed resize or stale v keeps max-age=86400.
- API payloads are unchanged (rewrite_payload_images adds no width).

## Tried and ruled out
- Eager copies at download time: one file per width per poster even when never drawn.
- A URL fragment to carry the width: it leaks to the provider URL when the cache is off.

## Watch out
- Immutable URLs stop browser requests, which were the only 'used' signal; rendering a versioned URL touches the metadata (once a day) so the retention cleanup keeps posters on screen.
- Copies use the .img suffix so the *.data / *.json globs in cleanup and revalidation never see them; _remove_stale_variants drops copies of changed or removed originals.
- str subclasses cannot have non-empty __slots__ (ruff SLOT000 is silenced on SizedImageUrl).
