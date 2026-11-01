---
title: "CineTrack toast Undo, theme-scoped durations, vendored JS eol"
author: Joke9854
date: 2026-11-01
branch: CineTrack-API
cost: { minutes: 27, tokens: 136713 }
touches:
  - ".gitattributes"
  - src/app/save_views.py
  - src/app/tests/views/test_ct_home_cards.py
  - src/static/css/input.css
  - src/static/css/main.css
  - src/static/js/ctShell.js
  - src/static/js/mediaStatusDateHandler.js
  - src/api/cinetrack_connection_views.py
  - src/api/serializers.py
  - src/api/tests/test_cinetrack_connection.py
---

## Decided
- Toast Undo (M5) needs no API change. episode_save already holds the new Episode, so the web view adds showToast.undo {url, instanceId, mediaType} for the CineTrack theme only. Undo posts to the existing media_delete, whose OOB swaps update detail rows. A Home card resets through the ctWatchUndone event, keyed by the data-ct-watched-instance stamped from the HX-Trigger header.
- Durations are mapped onto the motion tokens in CSS under html.cinetrack, not by a template sweep. A sweep would also change classic themes' timing. The unlayered rules beat Tailwind's @layer utilities.
- Vendored src/static/js/libraries/*.min.js are now `text eol=lf`. Tests check their exact byte size, and a Windows `text=auto` checkout added CRLF (+1 byte).
## Tried and ruled out
- Rewriting ~490 duration-* classes in templates: it breaks "classic themes render exactly as before".
## Watch out
- The preview DB's Severance S1 has one hand-made Event numbered E90, so its Home card offers E90 and ✓ returns 404 (episode_save's invalid-coordinate path, which also runs cleanup_episode_history_for_route). For a smoke, renumber it temporarily, then restore it.
- In ct, the toast lasts 2.8 s, but toasts with Undo last 5 s.
