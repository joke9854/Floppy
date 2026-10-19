# CineTrack integration

[CineTrack](https://github.com/joke9854/CineTrack) is an Android movie and TV tracker
that syncs with this fork's `CineTrack-API` branch. This page lists what CineTrack calls
and the rules both sides keep. The client side is described in CineTrack's
`docs/floppy-integration.md`. For a general third-party client, start from
[nuvio-client-guide.md](nuvio-client-guide.md) instead.

## Connecting

CineTrack connects in one of two ways:

- **API key**: the user's token, sent as `Authorization: Bearer <token>`.
- **Sign in with Floppy**: OAuth authorization code with PKCE at `/o/`, using the
  built-in public app `cinetrack` with redirect URI `cinetrack://floppy`.

The preflight is `GET /api/v1/cinetrack/connection/` (needs `watchlist:read`) plus
`GET /api/v1/info/`. CineTrack falls back to `GET /api/v1/user/preferences/` only when an
older server returns 404 for the connection probe. Preferences are never a prerequisite.

CineTrack reads its capabilities from `api_extensions` in `/api/v1/info/`, never from the
Floppy version:

| Flag | Enables |
|---|---|
| `cinetrack_bootstrap_v2` | Bounded `ensure` batches for the first sync |
| `cinetrack_episode_events_v1` | Explicit episode watch events with exact `watched_at` |
| `cinetrack_episode_translate_v1` | Episode numbering translation (anime) |
| `sync_items_v1` | Item snapshot and change feed (Floppy as main tracker) |
| `cinetrack_characters_v1` | Character names and TVDB pictures |
| `cinetrack_crash_reports_v1` | Crash and ANR report upload |

A server without a flag keeps the legacy behaviour for that feature. For example, a
server without `cinetrack_bootstrap_v2` gets the old contiguous-range episode writes.

## Endpoints

All paths are under `/api/v1/`.

| Endpoint | Used for |
|---|---|
| `GET cinetrack/connection/` | Preflight: account identity and capabilities |
| `POST cinetrack/bootstrap/movies/ensure/` | First sync, about 50 movies per request, no synchronous metadata fetch |
| `POST cinetrack/bootstrap/shows/ensure/` | First sync, about 50 shows per request |
| `POST media/tv/{source}/{media_id}/episodes/ensure/` | Episode plays as explicit `events[]` (season, episode, `watched_at`, `client_event_id`), about 50 per request |
| `POST media/tv/{source}/{media_id}/episodes/translate/` | Read-only numbering translation (`from=tracker` or `tmdb`) |
| `GET media/{type}/{source}/{media_id}/characters/` | Characters for the cast row |
| `POST cinetrack/crash-reports/` | Crash and ANR reports (needs `watchlist:write`) |
| `POST`/`DELETE sync/connections/` | Registers CineTrack as a pull connection, which turns on the change index |
| `GET sync/items/snapshot/`, `GET sync/items/changes/?cursor=` | Floppy as main tracker: full snapshot first, then the change feed |
| `media/...` status and watch routes | Live writes after the first sync (status changes, single plays, removals) |
| `GET health/` | Server health |

## Rules both sides keep

- **Exact timestamps.** The `watched_at` CineTrack sends is the instant Floppy stores.
  It is never truncated to a date, spread over a range, or replaced by the sync time.
- **Rewatches are separate plays.** Episodes are never deduplicated by
  show/season/episode alone. Sending the same event again returns `already_satisfied`.
- **Client event IDs** have the form
  `cinetrack:<provider-instance-id>:<sync-operation-id>:<operation-version>`.
- **Completed shows don't create history.** Marking a show completed never creates
  episode plays.
- **Per-item outcomes.** A batch reports a result for each item, so CineTrack can
  acknowledge the successes and retry only the failures.
- **One account, one instance.** A different account or server is a new provider instance
  and never receives old bootstrap operations.
- **No global history scans.** The modern path never scans an account's whole history.
- **Contract changes ship in both repositories** in the same task, and CineTrack
  ships them in a release.

## Testing

On `CineTrack-API` pushes, the "CineTrack API Targeted Tests" workflow runs the CineTrack
test modules. To run one locally:

```bash
SECRET=test-only scripts/test.sh api.tests.test_fork_tracking
```
