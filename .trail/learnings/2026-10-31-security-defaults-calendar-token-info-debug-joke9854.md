---
title: "Security defaults: calendar token, info debug, closed registration"
author: Joke9854
date: 2026-10-31
branch: CineTrack-API
cost: { minutes: 17, tokens: 80364 }
touches:
  - README.md
  - scripts/install/docker.sh
  - scripts/install/finish.sh
  - scripts/install/source_common.sh
  - src/api/contract_serializers.py
  - src/api/contracts/openapi.yaml
  - src/api/serializers.py
  - src/api/tests/helpers.py
  - src/api/tests/test_public_endpoints.py
  - src/api/views.py
---

## Decided
- iCal uses `User.calendar_token`, never the API token; old subscription URLs were deliberately broken (user choice) so the API key stops working as a calendar URL.
- REGISTRATION defaults to False, but `NoNewUsersAccountAdapter` opens sign-up while no non-demo user exists, with a direct query (is_first_run is cached 60s, which would let a second visitor in). The template `REGISTRATION` var is the same effective value.
- /api/v1/info no longer returns `debug`.

## Tried and ruled out
- Plain `migrations.AddField` in a fork-only migration: `check_migration_hygiene --strict` (run by config.tests.test_migration_hygiene) rejects it; copy the local `AddFieldIfNotExists` + `_column_exists` helper into the migration.
- AddField with a callable default for a unique column: the default is evaluated once for all rows. Add nullable, fill per row, then AlterField to unique.

## Watch out
- The installer (scripts/install/docker.sh, source_common.sh), Unraid templates/floppy.xml and README examples each hard-code REGISTRATION; they override the settings default.
- The hygiene management command itself needs an `upstream/dev` ref, which a fork checkout may not have; the test still runs.
