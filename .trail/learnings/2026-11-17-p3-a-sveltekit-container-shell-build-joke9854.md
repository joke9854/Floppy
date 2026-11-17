---
title: "P3-A SvelteKit container shell: build, supervisord, nginx /next"
author: Joke9854
date: 2026-11-17
branch: CineTrack-API
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
  - web/package.json
  - entrypoint.sh
---

## Decided
- web/ (SvelteKit 3.2, adapter-node 6) is built in a Dockerfile web_builder stage with Alpine's own nodejs/npm; the runtime image apk-adds nodejs and copies only web/build plus web/package.json (marks ES modules). The adapter-node output needs no node_modules.
- supervisord program web runs node on 127.0.0.1:8002 with PROTOCOL_HEADER/HOST_HEADER/ADDRESS_HEADER; FLOPPY_START_WEB is decided in entrypoint.sh (on when FLOPPY_BETA_MODE, else off; explicit value wins).
- nginx proxies location = /next and /next/ unchanged; SvelteKit itself 308-redirects /next to /next/, so nginx adds no redirect.
- P3-B is the board item 'v2 P3 session bridge' (DRF session auth with CSRF on /api/, allauth headless browser sign-in), decided in P1-G.

## Tried and ruled out
- Vitest browser component tests with paths.base /next: Chromium never connects ('Failed to connect to the browser session'); vite.config uses base '' when process.env.VITEST.
- TypeScript 7: Kit 3.2 peer-depends on ^6.

## Watch out
- Without X-Forwarded-Proto adapter-node assumes https and refuses same-origin form posts over plain http with 403; nginx maps an empty header to $scheme for /next.
- Node RSS is about 66 MB (smoke test and beta).
- Local Windows: vitest browser mode fails with EACCES listening on ::1; config tests using os.fchmod fail on Windows only.
