---
title: "P3-C /next shell: CineTrack tokens, components, sidebar and phone bar"
author: Joke9854
date: 2026-11-17
branch: CineTrack-API
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
---

## Decided
- The /next shell ports the Django web's CineTrack theme as is (tokens.css: :root merged with html.cinetrack) into Tailwind 4 @theme values; glass utilities only on nav, menus and sheets; ct-card has no blur.
- Default desktop = attached 248px labelled sidebar at lg (sidebar_style default ATTACHED), floating 64px icon rail md-lg, glass bottom bar with Library/More sheets below md. Floating sidebar variants not built yet.
- Links to screens not rebuilt go to Django pages with data-sveltekit-reload.
- GET user/sidebar/ gained library (ordered enabled types with labels, via ct_library_types) because the API had no order or names.

## Tried and ruled out
- Screenshots in the Browser pane while it is hidden: it renders blank; headless Playwright from web/ (signed in against a throwaway Django with LocMemCache) works.
- Dynamic Tailwind classes like bg-{color}: not generated; use literal class strings.

## Watch out
- A form without method=post submits as GET before hydration, putting the password in the URL: sign-in posts and the button waits for the script.
- Vite dev proxy (server.proxy) sends /api, /_allauth, /accounts, /static, /image-cache to FLOPPY_DJANGO_ORIGIN for local runs.
- With many media types the rail and sidebar list must scroll (flex-1 min-h-0 overflow-y-auto), or History/Stats get cut off at 900px.
