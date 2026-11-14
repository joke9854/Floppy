---
title: "Perf batch 2: nginx sends cached posters (X-Accel-Redirect) and native lazy loading"
author: Joke9854
date: 2026-11-13
branch: CineTrack-API
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
  - ct_contract.log
  - entrypoint.sh
---

## Decided
- Cached posters (/image-cache/<token>) are answered by app.middleware.ImageCacheMiddleware right after SecurityMiddleware: no session, user, language or activity marker per poster (0 queries).
- Behind the container nginx the view returns X-Accel-Redirect to the internal /_floppy-image-cache/ location. entrypoint.sh links /var/lib/nginx/floppy-data to the resolved FLOPPY_DATA_DIR and only then exports FLOPPY_IMAGE_CACHE_ACCEL_REDIRECT; an explicit value (even empty) wins. Source installs, runserver and tests keep Django's FileResponse.
- Measured before the change on the live server (Cloudflare tunnel): one cached poster 0.4-0.8 s, 12 in parallel 5.4 s, against 1.0 s for 12 nginx static files.
- Card posters cap at w342 (tmdb_srcset default w185,w342); the approved Progress card keeps w500 explicitly. lazysizes is gone: every <img> uses loading="lazy".
- Service worker cache is floppy-v3 and keeps one version per static file (storeLatestVersion).

## Tried and ruled out
- Shrinking fanart.tv art when the image cache is off: the only fix changes which artwork detail pages show; the cache already shrinks it (500 px posters) when on.

## Watch out
- nginx keeps Content-Type and Cache-Control from an X-Accel response and builds its own ETag, so it answers repeat If-None-Match itself.
- app.tests.test_query_counts (6 budgets), test_data_paths and test_container_bootstrap fail on Windows on a clean tree too; they are not in the CI targeted set.
- User's live server has the image cache ON and most Library posters are fanart.tv copies (not TMDB), so the w342 change matters less there than the nginx hand-off.
