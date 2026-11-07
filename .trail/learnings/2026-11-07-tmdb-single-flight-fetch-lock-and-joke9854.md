---
title: TMDB single-flight fetch lock and season page fallback
author: Joke9854
date: 2026-11-07
branch: claude/quizzical-einstein-d2b379
cost: { minutes: 1, tokens: 2383 }
touches:
  - src/app/providers/tmdb.py
  - src/app/season_details_views.py
  - src/app/tests/views/test_media_details.py
  - src/app/tests/providers/test_tmdb_fetch_lock.py
---

## Decided
- `tmdb.tv()`, `tmdb.movie()` and `tmdb.tv_with_seasons()` (uncached seasons) go through `_single_fetch` in `src/app/providers/tmdb.py`: `cache.add` lock keyed `<cache key>_fetch_lock` (seasons: show key + season list). A second caller polls the cache every 0.25 s for up to `FETCH_WAIT_SECONDS` (10 s); it fetches itself once the holder releases without filling the cache or the cap passes. The holder releases in `finally`; the 60 s TTL is only a safety net.
- The season page wraps its `tv_with_seasons` call in `interactive_request_scope()` and on `ProviderAPIError` renders from stored show/season rows (re-raises to `ProviderAPIErrorMiddleware` when there are none). A provider error is never persisted as `LOCAL_ONLY_MISSING_SEASON` (`provider_unavailable` flag).

## Tried and ruled out
- Smaller or concurrent batches in `fetch_and_cache_seasons`: skipped. Multi-batch fetches now run only in the `fetch_tmdb_seasons` Celery task (the season page asks for one season = one batch), and prod's failure mode was Wi-Fi body stalls, which more, smaller requests don't fix.

## Watch out
- In lock tests, don't patch `app.providers.tmdb.time.monotonic`: it is the global `time` module, and fakeredis TTLs read it, so the held lock "expires". Patch `FETCH_WAIT_SECONDS` instead.
- Running tests from a worktree on Windows: the repo pins uv 0.12.3; put a shim `uv` (`exec uvx --offline uv@0.12.3 "$@"`) first on PATH and set `UV_PROJECT_ENVIRONMENT` to the main checkout's `.venv`, or `uv run` creates an empty `.venv` in the worktree. `test_metadata`'s 11 `@tag("network")` tests run when given as a label; add `--exclude-tag network` after the labels.
