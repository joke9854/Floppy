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
| P4-B | Library (movies, shows, anime and the other media lists) | B1 built: the poster grid for TV, seasons, movies, anime, manga, games, books and board games (API `8eb00953a`, screen approved from screenshots). Later sub-slices below |
| P4-C | Detail pages (title, episode, person, studio; there is no season page) | C1 built: the movie and show page (API `ef4be8e18`), screen awaiting approval from screenshots |
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

### P4-B: Library

Today's Library (`app/media_list.html`, view `app.media_list_views.media_list`,
2,270 lines): header, type switch, status segment, toolbar (Status, Filter,
Sort, layout, settings), grid or table, infinite pages, bulk select, card
hover actions.

- [x] Header: "Library" on phones, the type's plural from md; "N titles · M in
      progress"; Shows/Seasons when both TV views are on.
- [x] Type switch on phones (the shell's sidebar lists the types from md).
- [x] Status segment from md, Status menu on phones; All sends `status=all`
      as the Django tabs do.
- [x] Sort menu with the page's sorts for the type, and the direction.
- [x] Search (in the URL, 300 ms after typing).
- [x] Grid: crisp poster, status badge, inset progress line, title,
      subtitle ("S2 E5 next" or the status), the sorted-by value.
- [x] Pages load as the grid scrolls.
- [x] The URL holds the state; sort and status are saved as the user's
      preferences, as the page saves them.
- [ ] B2: the filter menu (rating, collection, progress, genre, year, dates,
      release, source, language, country, platform, origin, format, author,
      provider, tags) and its option data.
- [ ] B3: the table layout and its columns (the web never sends `layout`
      until then, so the Django choice is kept).
- [ ] B4: bulk select (status, lists, collection, tags).
- [ ] B5: card actions (hover menu, progress +1, next episode).
- [ ] B6: music (artists, albums, tracks), podcasts and comics, which have
      their own grids; until then their Library links open Django.
- [ ] Share view.

API (P4-B1): `GET /api/v1/library/{media_type}/` returns the page's own list:
`build_media_list_context` was split from the `media_list` view (a pure
extraction), so filters, sorts, saved preferences and page size are the
page's. Because it saves preferences it takes the session or the account
token only. Cards come from the template helpers; the sorted-by line is the
grid's own template (`ct/library_sort_detail.html`), sent as text.

Backend fixes found on the way:
- `GET /api/v1/media/{type}/` (CineTrack's list, which sends no sort) now
  orders like the page: ties stay A to Z when sorting descending, TV Time
  Left uses the page's grouping (`app.tv_sort`), TV Start Date ignores the
  "added" fallback. A parity test compares it with the page for every offered
  sort, status and search.
- Sorting TV by Episode Air Date read each caught-up show's unstarted season
  with its own query (193 queries cold on beta's 267 shows); they are loaded
  in one query now.
- The Library page read the user's tag names twice (filter menu and bulk
  menu); once now. Library pages issue one query fewer.

Measured on beta (551 movies, 267 shows, rolled back): a movie page renders in
about 320 ms warm, TV in 0.6 to 1.1 s; the Episode Air Date sort was 2.3 s
cold. The query-count pins in `app.tests.test_query_counts` had drifted above
their budgets before this work (the suite runs on pull requests only and this
branch is pushed directly); see the board item.

### P4-C: Detail pages

Today's title page (`app/media_details.html`, view
`app.media_details_views.media_details`, about 1,870 lines) renders in two
phases. The shell reads only caches, so first paint never waits on a provider.
`?fragment=secondary` then fetches what is missing and renders the sections
below the hero. There is no season page: `season_details` redirects to the show
with `?season=N`, and the season's episodes are the show page's secondary
fragment.

C1 is the movie and show page in the CineTrack v2 layout (`ct/detail_hero.html`
and `ct/detail_secondary.html`). Other types (anime, games, books, music,
podcasts, comics) redirect 307 to their Django page, as the Library does.

- [x] Back control, backdrop (cache only; the poster until the secondary
      phase finds one), poster, title.
- [x] Meta line: type, two genres, year; runtime and certification for
      movies; "N Seasons" and "X% watched" for shows.
- [x] Score chips (the values; the ratings graphs come later).
- [x] The main action: an untracked or planned movie gets Mark as watched;
      a watched movie shows Watched; a show gets "Mark S2 E5 as watched" for
      its next episode. Until the track dialog (P4-D), a Track link opens the
      Django page, which keeps every other action reachable.
- [x] Overview, and Watch on for the user's region.
- [x] Shows: season pills (`?season=N`, else the next episode's season), the
      season's "X of Y episodes watched", episode rows with a watched check.
- [x] Movies: Your Plays.
- [x] Cast, the franchise collection and related lists, More Like This,
      Information.
- [x] Sections follow the user's detail layout: a hidden section is left out.
      The v2 sections are a block, so the layout's order does not move them
      on the page either.
- [x] Inside `/next`, Home and Library cards for movies and shows open this
      page (preloaded on tap, never on hover: the load can read the provider).
      Season, episode and other links keep their Django page.
- [ ] Later in P4-C: trailers, characters and crew tabs, notes, the physical
      collection section, history editing, ratings graphs, the link and tag
      popovers, the metadata provider switch, fanart logos, the season info
      dialog, the W shortcut, the episode, person and studio pages.

API (C1): `GET /api/v1/details/{media_type}/{source}/{media_id}/?part=shell`
or `part=secondary` returns the page's own data. `build_media_details_context`
is split from the view, and the phase is a parameter rather than
`?fragment=secondary`. The GET can write (metadata it resolves, queued
refreshes), so the endpoint takes the session or the account token only. The
web load awaits the shell and streams the secondary, which can take 0.5 to
1.9 s on a title's first TVDB read. Built as three reads:
`GET /api/v1/details/{type}/{source}/{id}/` (the hero), `.../sections/` and
`GET /api/v1/details/tv/{source}/{id}/season/?season=N` (a pill or Show more).

How C1 acts:
- A show's check and the hero's "Mark S1 E3" use the episode ensure route
  with a click's own event id, as Home does; the hero then re-reads the hero
  and the season. With no named next episode the hero takes the first
  unwatched aired episode of the season on screen, as ctShell.js does.
- An untracked or planned movie's Mark as watched posts the Django form
  (`media_save`, `save_as_new_entry`, the local wall time as `ctWatchNow`
  sends it), so a plan is replaced exactly as on the page. The button waits
  for hydration: an earlier click would post the form without its CSRF token
  and time.
- A watched movie's green Watched and the Track pill open the Django page,
  which keeps every other action (status, rating, dates, lists, rewatches).
- Shown as the Django Cast tab (person, then role); the Characters tab with
  TVDB pictures and the Crew tab come later in P4-C.

Measured locally: the detail page with the shell is 108.4 kB gzip (budget
110 kB).
