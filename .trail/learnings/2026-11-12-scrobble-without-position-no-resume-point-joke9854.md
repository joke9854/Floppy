---
title: "Scrobble without position: no resume point, no live time, show card falls back to the year"
author: Joke9854
date: 2026-11-12
branch: CineTrack-API
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
  - ct_contract.log
---

## Decided
- POST /api/v1/scrobble/ stores a resume point (PlaybackProgress) only when it can work out position_seconds: either sent, or derived from progress% AND duration_seconds. A client sending only `progress` gets nothing saved on pause/stop below the watched threshold.
- Without that PlaybackProgress row, a show added by scrobble has no part-watched episode and (no Season rows yet) no next_episode_target, so the Home In Progress card shows the release year instead of "S1 E3 · … left". Fixing the client fixed the card; no server change.
- Live Now Playing anchors view_offset_seconds on each play/pause event. Clients must resend START with position_seconds after a seek; NuvioTV uses seek policy POSITION_UPDATE (START only, never STOP, which would run the scrobble processor and end the session).
## Watch out
- Login inputs: `.ct-login-creds input` overrides Tailwind's pr-10 on the password field; keep the explicit `.relative > input` padding-right for the eye button.
- Editing static/css/areas/*.css needs `node_modules/.bin/tailwindcss -i ./static/css/input.css -o ./static/css/main.css` from src; main.css is committed.
