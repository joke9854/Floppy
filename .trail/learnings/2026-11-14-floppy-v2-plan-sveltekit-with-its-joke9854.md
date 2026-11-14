---
title: "Floppy v2 plan: SvelteKit with its own Node server, complete API, stable/beta; read docs/plans/floppy-v2.md first"
author: Joke9854
date: 2026-11-14
branch: CineTrack-API
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
  - ct_contract.log
  - docs/plans/floppy-v2.md
  - docs/stable-beta.md
---

## Decided
- The Floppy v2 plan is a living doc: docs/plans/floppy-v2.md. Read it before any v2 work and update it (decisions table, phase table, log) when something changes; add a new trail note when a decision changes direction.
- Goal: a tracker people can choose instead of Trakt/Simkl/WeTrakr. The rework must make Floppy lighter, more reactive, smoother and complete.
- Frontend: SvelteKit 3 (Svelte 5) in web/, running its own Node server (adapter-node) in the container as a backend-for-frontend that calls Django on 127.0.0.1. Django stays the only API for CineTrack, NuvioTV and outside apps. New app under /next/ until cutover.
- Backend stays Django: Postgres default, ASGI + server-sent events, OpenAPI generated from code with typed clients.
- Social/federation comes last (user's rule). Testing goes through the beta server (FLOPPY_BETA_MODE, docs/stable-beta.md).

## Tried and ruled out
- A static SvelteKit build (adapter-static): no extra process, but loses first-paint HTML, streaming, server load, form actions and remote functions; Floppy's main cost is round trips over a home uplink, so the server wins.
- React / upstream's React Native Web islands: heavier bundles and a sharing benefit Floppy doesn't need (CineTrack is Kotlin).
- A separate repo or a long rewrite branch: the frontend and API change together; a long branch can't be deployed or tested.

## Watch out
- SvelteKit is 3.x (3.2.0 on 2026-11-14): config in vite.config.js (svelte.config.js unsupported), #lib not $lib, $app/state, goto(url,{shallow:true}), $app/env. Many guides still show SvelteKit 2.
- Remote functions are experimental (experimental.remoteFunctions + compilerOptions.experimental.async); wrap calls in small local modules.
- Use web/, not frontend/ (upstream's React work uses frontend/).
