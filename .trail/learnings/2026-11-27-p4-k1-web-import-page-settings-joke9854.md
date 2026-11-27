---
title: "P4-K1 web Import page: settings, tiles, activity, file and username imports"
author: Joke9854
date: 2026-11-27
branch: CineTrack-API
touches:
  - docs/plans/floppy-v2.md
  - docs/plans/p4-screens.md
  - src/api/contracts/openapi-full.yaml
  - src/api/settings_screen.py
  - src/api/tests/test_settings_screen_api.py
  - src/integrations/views.py
  - src/users/views.py
  - web/src/lib/api/schema.d.ts
  - web/src/lib/settings/settings.css
  - web/src/lib/settings/types.ts
---

## Decided
- The Import page is one settings screen (`import`, serialized as `import_`): settings, tiles (`web` marks the dialogs the web draws; the rest link to Django `?open=<key>`), the K1 sources' state and the first activity snapshot.
- Every import form posts the page's `frequency`, `time` and `mode`: several views hard-index them (`request.POST["mode"]`) and fail without them.
- Simkl is OAuth: the web submits a real form (with csrfmiddlewaretoken and `next=/next/settings/import`), never fetch.
- The activity panel polls `import_data_activity` with Accept: application/json; the same builder feeds the screen.

## Watch out
- `user.get_import_tasks()` asks Celery's result store about PENDING/STARTED rows. Without Redis (local) it raises once an import is queued, so the screen catches it and returns `activity: null`.
- Serializer names must not clash: `ImportActivity` already exists in the API (fork_views_integrations), so these are `SettingsImport*`.
- New Django POST paths need the dev proxy in web/vite.config.ts (`/import/`, run and schedule actions).
