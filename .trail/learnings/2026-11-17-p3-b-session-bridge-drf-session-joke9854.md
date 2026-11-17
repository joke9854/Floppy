---
title: "P3-B session bridge: DRF session auth, allauth headless, SvelteKit bridge"
author: Joke9854
date: 2026-11-17
branch: CineTrack-API
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
---

## Decided
- API session auth: rest_framework SessionAuthentication is LAST in DEFAULT_AUTHENTICATION_CLASSES (token wins, no CSRF for tokens; no credentials still 403). SPECTACULAR AUTHENTICATION_WHITELIST keeps the cookie scheme out of both contracts (openapi.yaml unchanged).
- allauth headless (browser client) mounted at /_allauth/; routes Floppy does not use (email, phone, email password reset, login by code, allauth password change - bypasses the demo guard) answer 404 from patterns placed before the include. csrf_failure answers JSON 403 for /_allauth/.
- POST /api/v1/auth/password/recover/ reuses users.forms.PasswordRecoveryForm; authentication_classes=[] and throttled per username (5/h) and per X-Real-IP (20/h).
- Web bridge: handleFetch sends /api/ and /_allauth/ to Django on 127.0.0.1:8001 via node:http with the visitor cookie, public Host, X-Forwarded-Proto, X-Real-IP. Sign-in/out happen in the browser straight to allauth (Django sets its own cookies).

## Tried and ruled out
- Node fetch for the bridge: undici drops a custom Host header.
- Relying on event.fetch for the cookie: SvelteKit adds it only inside its inner fetch, after handleFetch.
- openapi-typescript as a devDependency: 7.13.0 peers TypeScript 5; run it through npx at a pinned version.

## Watch out
- adapter-node getClientAddress() throws without X-Real-IP (local runs without nginx).
- Signed-in test clients now reach /api/ (a test expecting 403 from a logged-in self.client got 200).
- SvelteKit answers a redirect for a form POST as 200 with a JSON body, not 303.
- Local Django without Redis: a settings module with LocMemCache works for runserver checks.
