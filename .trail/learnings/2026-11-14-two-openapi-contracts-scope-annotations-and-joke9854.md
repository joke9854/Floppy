---
title: "Two OpenAPI contracts, scope annotations and the tests to run for API changes"
author: Joke9854
date: 2026-11-14
branch: CineTrack-API
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
  - ct_contract.log
  - src/api/contracts/openapi.yaml
  - AGENTS.md
---

## Decided
- Two committed OpenAPI contracts: src/api/contracts/openapi.yaml is the verified subset promised to MCP and outside integrations (VERIFIED_OPERATIONS in api/schema_contract.py); openapi-full.yaml holds every API operation for generated clients (the SvelteKit typed client). Do not widen openapi.yaml to "fix" coverage.
- Every operation in both contracts must carry x-required-scope (test_every_committed_operation_declares_its_scope). The Static clone in schema_contract._annotate_static_callback keeps the real class name so api.scopes.view_key finds the VIEW_SCOPES key.
- API errors: api/exceptions.py (DRF EXCEPTION_HANDLER) + api/provider_errors.py. ApiJsonErrorMiddleware is only the fallback for errors outside DRF; it already kept tracebacks out of /api/ bodies.

## Watch out
- Any change to an API view, serializer, extend_schema responses or a view docstring changes the generated schema: regenerate BOTH contract files (commands in AGENTS.md), or test_committed_full_contract_is_exact_generation / test_committed_contract_is_exact_verified_generation fail.
- app/tests/test_api_contracts.py (under app/, not api/) pins exact status sets of critical operations (search, media detail, track media...). Run it with api.tests.test_cinetrack_openapi for every API change; skipping it shipped a red "CineTrack API Targeted Tests" run on 04a0145f3.
- beta-update.sh only moves beta when both "Docker Image" and "CineTrack API Targeted Tests" are green, so a red targeted run keeps beta on the previous build.
