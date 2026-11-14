---
title: "Provider failures answer 503, not 404, on tracking and ensure routes"
author: Joke9854
date: 2026-11-14
branch: CineTrack-API
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
  - ct_contract.log
  - src/api/contracts/openapi.yaml
  - AGENTS.md
---

## Decided
- API write routes that resolve a title through TMDB use api/provider_errors.py: 404 only when the provider says not found (ProviderAPIError.status_code == 404), 503 + code provider_unavailable + Retry-After: 30 for any other provider failure (timeout, 429, 5xx, EpisodeMetadataUnavailableError), 500 without exception text for anything else.
- Ensure/translate request-level metadata failures raise EpisodeEnsureError(kind="metadata", code="provider_unavailable") as 503; fork_views_sync_writes still maps kind to its own reason.
- Tracking write routes stay on normal provider timeouts (no interactive_request_scope): sync clients are background, a slow answer beats more 503 retries.

## Watch out
- The routed episodes/ensure, movies/ensure and shows/ensure views live in cinetrack_bootstrap_views.py. The same-named classes in fork_views_tracking.py are not routed (fork_urls.py), so fixing only those changes nothing.
- CineTrack's unwatch push treats any 404 as "no plays left" and ACKs it; never return 404 from DELETE .../episodes/N/watch/ for a transient failure.
- test_cinetrack_openapi pins the documented status set of the ensure routes; regenerate src/api/contracts/openapi.yaml with the command in AGENTS.md when responses change.
