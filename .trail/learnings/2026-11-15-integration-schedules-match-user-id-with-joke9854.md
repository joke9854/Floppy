---
title: "Integration schedules: match user_id with user_kwargs_regex; connect logic lives in integrations/connections.py"
author: Joke9854
date: 2026-11-15
branch: CineTrack-API
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
---

## Decided
- Find a user's PeriodicTask with `kwargs__regex=user_kwargs_regex(user.id)` (`integrations/task_filters.py`), or with the delimiter-safe Q helpers in `integrations/connections.py`.
- Never use `kwargs__contains='"user_id": N'`. It also matches users N0 to N9. Disconnecting Audiobookshelf, Storyteller, KOReader, Stremio, Pocket Casts, GPodder or Koito used to delete those users' schedules, and the Export page listed their backups (fixed 8ed289d46).
- Connect, disconnect, settings and import logic for key- and password-based integrations is in `integrations/connections.py`; the web views and `api/fork_views_integration_connections.py` both call it.
- `IntegrationError.message` is safe to return from the API. `web_message` can hold remote error text, so only the web may show it. `unreachable=True` maps to 503 `integration_unreachable`.
- Import runs and import/export schedules go through `users/data_management.py`.
- Anything that stores or removes credentials, or approves sync direction, is scoped `NEVER`, so only session logins reach it, and those come with P3's session bridge.

## Watch out
- Tests that patch `integrations.views.<client>` still work through re-exports in `views.py`. A call made from `connections.py` has to be patched as `integrations.connections.<name>`.
- On this machine 47 integrations/users tests fail without TMDB/MAL network access, the same on the base commit. Compare with a stash before blaming a change.
