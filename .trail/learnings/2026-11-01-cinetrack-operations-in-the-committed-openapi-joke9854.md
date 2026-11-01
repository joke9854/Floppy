---
title: CineTrack operations in the committed OpenAPI contract
author: Joke9854
date: 2026-11-01
branch: CineTrack-API
cost: { minutes: 18, tokens: 175875 }
touches:
  - ".github/workflows/cinetrack-targeted.yml"
  - src/api/contracts/openapi.yaml
  - src/api/schema_contract.py
  - src/api/tests/test_cinetrack_openapi.py
  - src/api/views.py
  - src/app/tests/test_api_contracts.py
  - AGENTS.md
---

## Decided
- The committed contract (src/api/contracts/openapi.yaml) is the VERIFIED_OPERATIONS subset in src/api/schema_contract.py. CineTrack's 25 app-facing operations live in CINETRACK_OPERATIONS and are unioned in; add a new app endpoint there, then regenerate with the command in AGENTS.md.
- Kept `x-floppy-scope: verified-mcp-and-grounding-subset` unchanged (a test and possibly clients read it); only TITLE/DESCRIPTION mention CineTrack.
- HealthView got an explicit HealthApiResponseSerializer because HealthResponseSerializer has no fields (to_representation only) and generates "No response body", which test_all_successful_scoped_operations_have_truthful_body_presence rejects.

## Watch out
- Fixing a view's schema removes it from EXPECTED_SCHEMA_ERRORS in schema_contract.py, and test_reviewed_baseline_has_expected_unique_counts pins that count; update both.
- Regeneration re-sorts paths, so the yaml diff looks huge. Compare parsed operations/components against HEAD to prove only additions.
- schema_contract.py, views.py and test_api_contracts.py were already not ruff-format clean at HEAD; CI only runs ruff check.
