---
title: CineTrack bootstrap jobs and GlitchTip error reporting
author: Joke9854
date: 2026-11-01
branch: CineTrack-API
cost: { minutes: 30, tokens: 217472 }
touches:
  - ".github/workflows/cinetrack-targeted.yml"
  - README.md
  - docs/architecture/log-redaction.md
  - docs/integrations/cinetrack.md
  - docs/monitoring.md
  - pyproject.toml
  - src/api/cinetrack_bootstrap_views.py
  - src/api/cinetrack_connection_views.py
  - src/api/contracts/openapi.yaml
  - src/api/fork_urls.py
---

## Decided
- Bootstrap jobs (cinetrack_bootstrap_jobs_v1) keep state in the Django cache, not a model: no migration, and a lost or expired job answers 404 and the client resubmits, which is safe because every ensure is idempotent. The task (api/tasks.py, autodiscovered) reuses parse_*_entries/*_results from cinetrack_bootstrap_views in 50-item chunks; a failed chunk reports "error" per entry, other chunks keep exact outcomes.
- Error reporting is sentry-sdk, off unless SENTRY_DSN; config/error_reporting.py is the credential boundary for events (method + safe_url only, no locals, no source context, no extra, redact_secrets on text).
## Tried and ruled out
- include_local_variables=False alone: the SDK still attaches source lines around each frame, which carried literals in a smoke test; include_source_context=False is required too.
- An Uptime Kuma keyword monitor on "status":"ok": every entry under checks carries that text, so a down dependency still matches; rely on the 500 status.
## Watch out
- A new ChoiceField named like an existing one (kind) makes spectacular --fail-on-warn fail; name both sets in ENUM_NAME_OVERRIDES and mirror them in test_api_contracts.test_settings_publish_stable_project_metadata.
- Git-bash sed -i strips CRLF on this machine; re-run unix2dos after it.
