---
title: "P4-K2 web Import: account sources, Trakt and AniList"
author: Joke9854
date: 2026-11-27
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/settings_import_screen.py
  - src/api/tests/test_settings_import_api.py
  - src/integrations/views.py
  - web/src/lib/api/schema.d.ts
  - web/src/lib/settings/import/ImportDialog.svelte
  - web/src/lib/settings/import/sources.spec.ts
  - web/src/lib/settings/import/sources.ts
---

## Decided
- K2 sources (Trakt, AniList, Steam, Last.fm, Koito, Xbox, PSN, Pocket Casts, GPodder) are drawn by the web. The screen's `accounts.<key>` carries each account's state (connected, broken, name, last sync, error, history) and never a key, token, email or password; a test seeds every account type and asserts the secrets are absent.
- Trakt and AniList OAuth starts stay undecorated real form submits (shared OAuthForm with frequency/time/mode, `next=/next/settings/import`, csrf fetched before submit); the other K2 views answer JSON via answers_json.
- After every account action the dialog reloads the page data (invalidate) whether it saved or failed: xbox_connect / psn_connect can save the account and then flash a schedule error, which answers saved:false.

## Watch out
- Connect views call the provider synchronously; locally only Koito and GPodder can be tried (a closed port like http://127.0.0.1:9 shows the error path).
- The test client is plain http on a non-loopback host, so `trakt.redirect_uri` is the OOB device-flow URI there.
- In the browser pane the screenshot image can be larger than the click frame (904 vs 800 px); clicking by image coordinates misses the dialog and closes it via the backdrop. Click from page JS or use the reported frame.
