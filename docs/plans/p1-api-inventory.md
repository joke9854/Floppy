# P1: what the web can do that the API can't

Inventory for phase P1 of `docs/plans/floppy-v2.md` ("Complete API"), taken
2026-11-14 on `CineTrack-API` at `397cb5c51`. Keep it updated: when a gap
closes, strike it here and note the commit.

## Counts

| | Count |
|---|---|
| Web actions that change state (outside `/api/`) | 243, of which 8 inbound webhooks and 5 file downloads |
| Web pages (plus 48 htmx fragments folded into them) | 59 |
| API operations (`/api/v1`, ListenBrainz, root `/api/`) | 189 |
| In the verified contract (`src/api/contracts/openapi.yaml`) | 68 |
| API operations with documented responses | 184 |
| API views without a scope | 0 |

Most of tracking, history, lists, music, podcasts, collection, tags,
Discover, Home, calendar, statistics, sync and scrobbling already has an API.
Provider metadata for any title, tracked or not, is `GET media/{type}/{source}/{id}/`.

## Rule for every new endpoint

- A documented DRF view in `api/`, listed in `api/scopes.py` (`VIEW_SCOPES`),
  with `@extend_schema` responses. A view missing from `VIEW_SCOPES` answers
  403 to every scoped token.
- Provider failures go through `api/provider_errors.py`: 404 only for a real
  "not found", 503 `provider_unavailable` with Retry-After otherwise, never
  exception text.
- Account and security actions (passwords, tokens, app revocation, admin)
  accept the signed-in web session only, never an app token, like
  `user/token/regenerate/` (scope `NEVER`) does today.
- The SvelteKit server calls these endpoints; it never becomes a second API.

## Slices, in the order the SvelteKit screens need them

### A. Error codes everywhere (done)

- Tracking write routes and episode ensure/translate (`a40ab14a4`).
- `04a0145f3`: DRF exception handler `api/exceptions.py` for whatever a view
  does not handle (provider 404/503, tracked-media 409, typed 500); media
  detail, provider search, podcast lookup, search by id, list
  recommendations, episode score, MusicBrainz artist, discography sync and
  playback progress answer 503 on provider outages and no longer echo
  exception text. `ApiJsonErrorMiddleware` stays as the fallback outside DRF.
- Kept: consumption PATCH routes return `validate_body`'s field message under
  `errors` (validation text, not an exception).

### B. One contract, generated from code (done)

- `0fb7f764e`: the 30 verified-contract operations without `x-required-scope`
  have it now (the `Static<Name>` clone kept its real class name).
- `2d8cc2b9b`: `src/api/contracts/openapi-full.yaml` holds every API operation
  (184). A test fails when it drifts from the code and names the regeneration
  command; another requires `x-required-scope` on every operation of both
  contracts. `openapi.yaml` stays the verified subset promised to MCP and
  outside integrations. Regenerate with the commands in AGENTS.md.
- Clean-up: the unrouted ensure views in `fork_views_tracking.py` are gone and
  two copy-paste docstrings are fixed.
- Not done, on purpose: renaming the URL names `api_list_add_item` (GET only)
  and `api_list_remove_item` (also GET). No client sees URL names, the paths
  stay the same, and the rename would only churn `reverse()` calls in tests.
- Typed clients (openapi-typescript) are generated from `openapi-full.yaml` in P3.

### C. Title pages (done)

All read-only, scope `watchlist:read`, in `api/fork_views_pages.py`. The page
data is built once in `app/people_data.py` (person, studio) and
`app.history_views.collect_history_genres`, and the web pages call the same
functions. Responses carry data only: no colors, sort menus or filter state;
the client filters and sorts the full lists.

| Web | API |
|---|---|
| `person_detail` | `GET people/{source}/{person_id}/`: profile, every credit (with `item_id`, genres, `watched`, minutes), watched credits, known for, watched totals. 400 for a source without person pages, 404/503 from the provider |
| `studio_detail` | `GET studios/{source}/{studio_id}/`: profile (IGDB) and credited titles. 404 for an unknown studio, 503 when IGDB is down |
| `history_genres` | `GET history/genres/`: values for the history `genre` and `implied_genre` filters |
| `trakt_series_graph_fragment` (and the provider and IMDb graphs) | `GET media/{tv,anime}/{source}/{id}/ratings-graph/?rating_source=provider\|trakt\|imdb&season=N`: stored season and episode scores; `pending` while Trakt ratings of aired episodes are missing, and a pending poll queues the season fetch at most every 10 minutes |
| `activity_sessions_modal` | `GET history/?media_type=&source=&media_id=&logging_style=sessions` already had the filters; history entries now carry `notes`. The modal's streak and gap figures are derived from the days on the client |

### D. Tracking actions (done)

| Web | API |
|---|---|
| `media_rewatch` | `GET/POST/DELETE media/{tv,anime}/{source}/{id}/rewatch/` and `.../{season}/rewatch/` (`329717e3c`). `started_at` is an exact date-time with offset; 409 when there is nothing to rewatch |
| `create_entry` | Already covered: `POST media/{type}/` with source `manual`. Its provider branch now answers 503/404 instead of a bare 500, and so does `PATCH media/{type}/{source}/{id}/` (`92c339dfb`) |
| `update_metadata_language_preference`, `remap_metadata_provider` | `PATCH media/{type}/{source}/{id}/provider-preference/` (`language`, `provider` + `provider_media_id`); GET returns the language; codes from `GET metadata/languages/` (`582b03c66`) |
| `move_library_item` | `POST media/{tv,anime}/{source}/{id}/move/` (`d8de3019c`) |
| `migrate_grouped_anime` | `POST media/anime/mal/{id}/migrate-grouped/` (`d8de3019c`) |
| `set_hardcover_edition` | `GET/PUT media/book/hardcover/{id}/edition/` (`582b03c66`) |
| `set_music_release` | `GET/PUT music/albums/{id}/release/` (`582b03c66`) |
| `tag_bulk_toggle` | `POST tags/{id}/items/` (`582b03c66`) |
| `bulk_collection_quick_add` | `POST collection/bulk/` (`582b03c66`) |
| `collection_fields_save` | `GET/PUT collection/fields/` (`582b03c66`) |
| `sync_album_metadata` | `POST music/albums/{id}/resync/` returns the album holding the plays (another id after a duplicate merge). Rebuilds now keep track rows by recording id, so plays stay linked (`11974a08b`) |

The shared changes live in `app/library_actions.py`; the web views call it.

Still missing: reading and writing the custom field values of one
collection entry (`collection/{entry_id}/` has no field values).

### E. Lists

| Web | Missing in the API |
|---|---|
| `list_share_view` | Publish the current view as a public smart list |
| `list_import_csv` / `list_export_csv` | List CSV import and export |
| `bulk_list_add` | Add many items to a list |
| Trakt lists and MDBList (`trakt_lists_*`, `mdblist_*`) | List imports: connect, disconnect, sync now, import by URL |

### F. Preferences the screens keep

| Web | Missing in the API |
|---|---|
| `medialist_columns`, `list_detail_columns` | Table columns |
| `medialist_entry_grouping` | Entry grouping |
| `toggle_pinned_provider` | Pinned watch providers |
| `update_statistics_preferences`, `update_statistics_compare_mode`, `update_top_talent_sort`, `update_genre_sort`, `update_studio_sort` | Statistics display settings |
| `appearance` | Check which fields `user/preferences/` already covers |
| `convert_anime_library` | Queue the anime library conversion |

Proposal: fold these into `user/preferences/` (one PATCH), not one endpoint each.

### G. Account and security (web session only)

| Web | Missing in the API |
|---|---|
| allauth login, logout, signup, password recovery, 2FA, social logins | Use allauth's headless API rather than writing our own |
| `account` | Username and password change |
| `revoke_app_session`, `revoke_connected_app`, `connected_apps` page | App sessions and OAuth app access |
| `create_integration_token`, `revoke_integration_token` | Scoped API tokens |
| `create_catalog_grant`, `revoke_catalog_grant` | Add-on install credentials |
| Onboarding wizard (`setup/*`) | Wizard state and choices |

### H. Integrations management

The API can queue one-off imports for mal, anilist, kitsu, steam, yamtrack,
hltb, grouvee, imdb, goodreads, hardcover and storygraph, and read import
activity. Missing:

- Connection state for every service (the `integrations` settings page).
- Connect, disconnect and settings for Radarr, Sonarr, Jellyfin, Plex,
  Audiobookshelf, Storyteller, KOReader, Stremio, Xbox, PSN, Pocket Casts,
  gPodder, Last.fm and Koito; Plex usernames, libraries and webhook shares;
  Jellyfin webhook events, push and pull now, Playback Reporting import;
  Seerr settings.
- Imports not in the dispatch list: Trakt (public, export file, collection
  CSV), TV Time, CLZ, Plex, Simkl and AniList through OAuth.
- Import and export schedules; rollback or cancel an import run.
- Match fixes (`match_fix`, `match_reference_status`).
- Sync direction and pause per connection (conflicts already have an API).
- Letterboxd CSV export.

OAuth callbacks and device-code pages stay web routes; the screens link to them.

### I. Instance administration (superuser, web session only)

Instance and personal provider credentials, default provider per media type,
TMDB proxy, image cache settings and purge, server port, cache clearing, bulk
delete by type or import source, log download, crash report download.

## Not needed in the API

Inbound webhooks (Plex, Jellyfin, Emby, Kodi, Seerr, Stremio add-on,
ListenBrainz ingest), OAuth callbacks, public feeds (list RSS/JSON, iCal,
Discover RSS, Stremio manifest and catalog), image proxies, the startup retry
page, `jsi18n` and the service worker.

## Later, with social (P6)

Public user profiles and recommending to a public list without an account.
