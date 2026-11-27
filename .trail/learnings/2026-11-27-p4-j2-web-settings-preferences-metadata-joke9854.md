---
title: "P4-J2 web settings: Preferences, Metadata, Export, Advanced, Connected apps"
author: Joke9854
date: 2026-11-27
branch: CineTrack-API
cost: { minutes: 29, tokens: 257025 }
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/settings_screen.py
  - src/api/tests/test_settings_screen_api.py
  - src/app/helpers.py
  - src/users/metadata_views.py
  - src/users/views.py
  - web/src/lib/api/schema.d.ts
  - web/src/lib/settings/settings.css
---

## Decided
- The web posts the Django settings forms with Accept: application/json. Redirecting views get `helpers.answers_json`; it now fails a bare 403/404 with its status and leaves GET alone (it used to answer both as `{"saved": true}`). A view can add answer fields through `request.answer_extra` (Metadata's anime conversion count).
- Preferences returns `values` keyed by POST name and the web posts all of them: the view resets the auto-pause rules, region and language when they are missing. A stored value the option list lacks (UNSET region) is offered as "Not set" so it shows and posts back unchanged.
- When TMDB's region or language list fails to load, a Preferences save keeps the stored values (it used to reset them to the fallback).
- Export's CSV comes back from the form post itself: the web reads it as a blob and downloads it; only the errors answer JSON.
- Credential and proxy values never come back: providers carry only the masked preview, the TMDB proxy only `tmdb_proxy_configured`. Save stays off until something is typed; Remove is its own button, because a blank field deletes.
- The settings route sets the page component and its screen together (`view`), so a page never renders the next page's screen.

## Tried and ruled out
- `{#await loader()}` with `<Page {screen} />`: moving between pages handed the old page the new screen for one update and it crashed reading `screen.preferences.sections`.

## Watch out
- Locally (no Redis) every cache clear and the media-type delete answer 500: `cache.delete_pattern` is django-redis only. Not a code bug; the server tests cover them.
- Never save a made-up provider key from the browser: the validators probe the real provider. Patch `credentials._probe` in tests.
- Every new Django POST path the web uses must be listed in the dev proxy in `web/vite.config.ts`.
