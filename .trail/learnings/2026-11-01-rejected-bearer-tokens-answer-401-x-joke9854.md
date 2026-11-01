---
title: "Rejected bearer tokens answer 401, X-API-Key stays 403"
author: Joke9854
date: 2026-11-01
branch: CineTrack-API
cost: { minutes: 16, tokens: 63260 }
touches:
  - docs/integrations/nuvio-client-guide.md
  - src/api/authentication.py
  - src/api/tests/test_fork_integration_tokens.py
  - src/api/tests/test_nuvio_conformance.py
  - src/api/tests/test_oauth_app_signin.py
  - ".github/workflows/cinetrack-targeted.yml"
  - src/api/contracts/openapi.yaml
  - src/api/schema_contract.py
  - src/api/tests/test_cinetrack_openapi.py
  - src/api/views.py
---

## Decided
- 2026-11-01, user's call: a presented `Authorization: Bearer|Token` credential that is unknown, revoked, expired or belongs to an inactive user raises `InvalidBearerToken` (src/api/authentication.py): 401, `code: authentication_failed`, `WWW-Authenticate: Bearer error="invalid_token"`. This reverses the earlier "403 is an API break not made" note in nuvio-client-guide.md.
- Why: CineTrack renews or drops its OAuth sign-in only on 401 (FloppyApiClientFactory.kt), so a device signed out from Settings > Connected apps showed a generic permission error instead of asking to reconnect.
- Unchanged on purpose: no credential, `X-API-Key`, and missing scopes stay 403; the authentication matrix (test_authentication) uses X-API-Key.

## Tried and ruled out
- Adding `authenticate_header` to BearerAuthentication: DRF would then answer 401 for every request with no credential too, flipping the whole 403 matrix.
- Subclassing AuthenticationFailed: DRF's APIView.handle_exception downgrades it to 403 when the first authenticator has no challenge. A plain APIException with `auth_header` keeps 401 and DRF's handler sets WWW-Authenticate from it.
