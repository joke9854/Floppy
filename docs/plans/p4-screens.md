# P4: screens on the new web app

Part of `floppy-v2.md`. Started 2026-11-17.

## Goal

Rebuild the Django screens in `web/` one at a time, under `/next/`, on the P3
foundation (session bridge, typed client, tokens, shell, service worker,
budgets). A screen is done when its parity checklist is met, its response time
and bundle are inside budget, and it has been tried on beta. Nothing switches
away from Django in P4: `/` keeps serving the Django pages until the P5
cutover.

## How each slice runs

1. Write the parity checklist from the Django templates and views: every
   section, action, empty state and link the screen has today.
2. Close API gaps first, as their own commit with contract tests. Changes to
   existing operations are additive only (the verified `openapi.yaml` is read
   by MCP clients); a screen that needs a different shape gets its own
   endpoint. Regenerate `web/src/lib/api/schema.d.ts`.
3. Build the screen with one server load per page (no waterfall), the shell's
   strings in `#lib/strings.ts`, and the CineTrack look from `DESIGN.md`.
4. Measure: `npm run budgets` and the smoke test's response-time check.
5. Show screenshots and get approval before pushing (a push deploys beta).
6. Add a board Test item for trying it on beta.

## Slices

| Slice | Screen | Status |
|---|---|---|
| P4-A | Home | Built: API `3a04e8483`, screen `cdefe0815`; follow-up (Now Playing pill, poster widths, TRACK_TIME) approved from screenshots |
| P4-B | Library (movies, shows, anime and the other media lists) | Not started |
| P4-C | Detail pages (title, season, episode, person, studio) | Not started |
| P4-D | Track dialog | Not started |
| P4-E | History | Not started |
| P4-F | Calendar | Not started |
| P4-G | Discover | Not started |
| P4-H | Statistics | Not started |
| P4-I | Lists | Not started |
| P4-J | Settings and integrations | Not started |
| P4-K | Imports | Not started |

### P4-A: Home

Today's Home (`app/home.html`, `components/ct/home_sections.html`, data from
`app/home_sections.build_home_sections`, cached per user and day):

- [x] Header: "Home", the catch-up count ("N episodes to catch up on across M
      shows") and the airing count, joined by a dot; each only when non-zero.
- [x] Now Playing pill beside the title when something is playing; it polls,
      and refreshes In Progress when the playing title changes.
- [x] Notifications bell (phones: the account avatar instead, as A6) linking to the notifications page.
- [x] In Progress: a row of 16:9 cards, latest activity first. Cached
      backdrop (cache only, never a provider call), else the poster cropped;
      progress line along the bottom edge; S/E label and episode title;
      time left or episodes left; Rewatch pill; the ✓ button that marks the
      named episode watched; Movie/Show filter pills when both kinds are
      present.
- [x] Airing This Week: grouped list in two columns of three (one on
      phones), day and time, Premiere/Finale tags, link to the episode, and a
      "Calendar" link.
- [x] Recently Watched: a row of poster cards, one per title, newest first,
      with a "History" link.
- [x] Coming Soon: a row of release cards.
- [x] Empty state when no section has entries.
- [x] Rows scroll horizontally with touch, mouse drag and keyboard.

API (P4-A1): `GET /api/v1/home/` drops what the screen needs (Airing comes
back as bare items without day, time or tag; no catch-up counts; no In
Progress target or progress), and `/continue-watching/` has only In Progress.
Neither CineTrack nor NuvioTV calls `/home/`, but it is in the verified
contract, so it stays as it is. A new read-only operation,
`GET /api/v1/home/sections/`, returns the summary counts and the four
sections in the screen's shape from the same cached sections.

The ✓ button writes through the existing episode ensure endpoint
(`POST /api/v1/media/tv/{source}/{media_id}/episodes/ensure/`) with one
event: the watch time from the browser and a client event id, so a retry
answers `already_satisfied` and a rewatch stays a separate play.

P4-A screen (2026-11-17): `web/src/lib/home/` (cards, rows, styles ported
from `areas/home.css`), the start page `(app)/+page.svelte` with one load.
Checked against the Django Home on a seeded throwaway database: same
sections, order, counts, labels, tags and links; the check saves through the
ensure route (`created`), turns green, and Home reloads with the next
episode. Start page bundle 98.3 kB of 110.

Follow-up (same day): the Now Playing pill (polls
`/api/v1/playback/now-playing/` every 10 s while visible, ticks each second,
reloads Home when the playing title stops or changes; the endpoint gained
`display_image`, the image through the image cache as the Django pill shows
it); poster cards 136 px on wide screens and the user's phone grid setting
(`mobile_grid_layout`) below 768 px; with `TRACK_TIME` off the check sends the
local date, which Floppy reads as that day's midnight exactly as the Django
form. Start page bundle 100.1 kB of 110.

Watch out: a horizontal row must not capture the pointer on press, or every
click lands on the row instead of the card's link or check.
