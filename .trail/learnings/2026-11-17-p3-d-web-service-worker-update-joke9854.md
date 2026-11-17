---
title: "P3-D web service worker, update prompt and bundle budgets"
author: Joke9854
date: 2026-11-17
branch: CineTrack-API
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
  - web/src/service-worker/index.ts
  - src/static/js/serviceworker.js
  - web/scripts/app-version.js
  - web/scripts/check-budgets.js
---

## Decided
- The /next service worker (web/src/service-worker/index.ts) caches only floppy-web-<version>: precache immutable files, cache-first for them, network-first navigations with an inline offline page (503, no-store). No automatic skipWaiting; the update prompt posts 'floppy-web:activate'.
- The legacy worker (src/static/js/serviceworker.js) passes /next/ through and leaves floppy-web-* caches alone on activate.
- App version is a content hash (web/scripts/app-version.js), not the git SHA, so a rebuild with no web change does not prompt users.
- Bundle budgets live in web/scripts/check-budgets.js (per page, found through the generated client nodes), run in CI after the build.
- nginx sends /next/service-worker.js as no-cache, no-store, must-revalidate and version.json as no-cache.

## Tried and ruled out
- Plain no-cache on the worker: Cloudflare rewrote it to max-age=14400 and cached it (cf-cache-status REVALIDATED). no-store makes it pass through.
- A literal newline inside curl -w in the docker workflow YAML: it broke the workflow file. Use \n inside the quoted string.
- Triggering the update prompt in Playwright with the worker active: block service workers, route **/_app/version.json, then dispatch focus on window.

## Watch out
- Check worker headers through the public beta URL, not only in CI: the CDN changes them.
- Vitest browser runner needs base '' (paths.base is empty under VITEST).
