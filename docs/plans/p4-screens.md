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

## Browser flows to cover again

The Django browser tests below drove the retired classic theme and are
skipped (`CLASSIC_UI_SKIP`, 2026-11-20). Each slice that rebuilds the screen
adds a web test for its flow:

- Search, then track a show manually, as completed, a season as completed,
  a season's progress (`test_tv_manual`, `test_tv_completed`,
  `test_season_completed`, `test_season_progress_edit`): P4-D and search.
- The movie track window's close button and release date, a game's progress
  updating its start date (`test_movie_split_track_modal_...`,
  `test_game_progress_live_updates_start_date`): P4-D.
- Session history calendar and the shared date picker
  (`test_session_history_calendar_...`): P4-D / P4-E.
- Touch card actions (`test_touch_media_card_reveals_...`): P4-B5.
- Discover's match signal wrapping (`test_discover_match_signal_...`): P4-G.
- Lists: the blank list modal and the add/remove flow (`test_blank_modal`,
  `test_flow`): P4-I.

## Slices

| Slice | Screen | Status |
|---|---|---|
| P4-A | Home | Built: API `3a04e8483`, screen `cdefe0815`; follow-up (Now Playing pill, poster widths, TRACK_TIME) approved from screenshots |
| P4-B | Library (every media list) | B1 to B6 built (2026-11-20): grid, filters, table, bulk select, card actions, music, podcasts and comics, Share View |
| P4-C | Detail pages (title, episode, person, studio; there is no season page) | C1, C2, C3 built and pushed (2026-11-20); the studio page, anime episodes and ratings graphs later |
| P4-D | Track dialog | D1 and D2a on beta (2026-11-21): the General tab for movies, shows, seasons and episodes, then anime, manga, games, books, comics, comic issues, board games. D2b on beta: music artists and albums, podcast shows. D3: the Episode Plays tab. D4: the Discover tab. D5: the Collection tab (single episodes). D6a: the Metadata tab's plain forms. D6b: its searches (remap, library move, Hardcover edition, MusicBrainz release). D6c: Convert to Grouped Series. D7: the episode rows' Activity History. D8: the custom-field editor. Songs and podcast episodes come with their detail pages |
| P4-E | History | E1 (2026-11-22): the month view, filtered pages, type pills, rows with Edit tracking, Add to list and the title's history, Load more, the Filter History sheet. E2 next: the Library card menu's link, a web test for the sessions dialog |
| P4-F | Calendar | F1 (2026-11-22): the month as a grid (phones: Agenda or Month) or a list, the type and status filter, Fetch New Releases, Download Calendar, the iCal export link |
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
- [x] B2: the filter menu (rating, collection, progress, genre, implied
      genre, the Date pane's release year and completed date as a year, a
      range or "within the last N", release, source, availability,
      language, country, platform, origin, format, author, streaming
      service, tags with OR/AND/NOT). The API sends the page's `current_*`
      values as `filters` and its `filter_data` as `filter_options`; panes
      show as filter_menu.html shows them. The menu loads on first use, to
      keep the Library inside its bundle budget (104.2 kB of 110).
- [x] B3 (2026-11-20): the table layout. The grid / table switch saves the
      type's layout as the page does (`layout=`); the table shows the user's
      columns in their order, a small poster, the title with its repeat
      count, and each cell with its note (Latest, Total, Earliest,
      Remaining); genres filter the list. The Columns menu (loaded on first
      use) shows, hides and moves columns and resets to defaults through
      `PUT /api/v1/user/table-columns/`. The API sends each cell from the
      page's own cell template (a parity test compares every cell with the
      Django table) and reads the tags column in one query.
- [x] B4 (2026-11-20): bulk select. View settings > Select Items turns a tap
      into a selection (grid and table); the bar posts the page's own
      endpoints: Update Status (`/bulk/status`), Add to List
      (`/list/bulk-add`), Add to Collection (`/bulk/collection`), Apply Tag
      Add / Remove (`/tag_bulk_toggle`). The API sends the menus as `bulk`
      (null where the page has none: artists, albums).
- [x] B5 (2026-11-20): the card's menu, as the page's hover buttons: Edit
      tracking (the Django page until the track dialog, P4-D), Add to List,
      View your activity history; and the Next ep pill with the user's quick
      update preference on (`next_episode_url`). The Django Library card has
      no progress +1 (that is Home's card), so neither has the web one. The
      Next ep link costs one query per show without a tracked next episode,
      as media_card.html does (pinned at one per card).
- [x] B6 (2026-11-20): music (Artists, Albums, Tracks), podcasts and comics
      (Comics, Issues) on the web Library: the views switch with
      `subview=`, music and podcasts draw square art, artist and album rows
      use their own table columns. Every Library type now opens the web.
- [x] Share View and "Show matching entries separately" in View settings
      (`/list/share-view`, `/medialist/<type>/entry-grouping/`). The API now
      runs the list inside the user's entry grouping, as the page's view
      does; before, a user who shows each play saw them grouped on the web.
- Bundle: the table, the Columns, card and View settings menus, the bulk
  bar and the write helpers load on first use. Library 109.8 kB of 110.
- Dev: Vite proxies `/bulk`, `/list/`, `/tag_bulk_toggle` and `/medialist`
  to Django, as nginx does in the container.

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
- [x] C2 (2026-11-20): Characters / Cast / Crew tabs (Characters lead
      with the role and show TVDB's character picture where there is one),
      the Trailers row and player (`GET /api/v1/details/.../trailers/`,
      loaded on its own as the page's ?fragment=trailers), the hero's Trailer
      button, fanart.tv's poster and title logo, the Links sheet, the season
      info dialog (each cover's ⓘ; the season read's `info`), the W shortcut.
      Everything below the hero loads with the sections, so the page's first
      load is the hero alone (106.2 kB of 110).
- [ ] With the track dialog (P4-D): notes, the physical collection section,
      history editing, the metadata provider switch, the tag popover.
- [x] C3 (2026-11-20): the person page (ct/person_page.html: hero, your
      numbers, View in History, the source page, the biography, You've
      Watched, Known For, the filmography with All / Movies / Shows, newest or
      oldest first, the first 20 until "All N credits") and the TV episode
      page (crumbs, the still blurred until watched when spoilers are hidden,
      scores, one-click Mark as watched, previous / next, the overview's
      spoiler cover, the season strip, Guest Stars, the crew grid). Both
      read their page's builder (`build_person_context`,
      `build_episode_context`): `GET /api/v1/details/person/...` and
      `/api/v1/details/episode/...`. Person and episode links across the web
      open them; Watched and Track on an episode open the Django page.
- [ ] Later: the ratings graphs; the studio page (classic design, mostly
      games, which have no web detail page yet); anime episodes.

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

### P4-D: Track dialog

Today's dialog (`app/components/fill_track.html`, `app.track_modal_views`,
one form per type in `app/forms.py`) has five tabs: General, Metadata,
Collection, Episode Plays and Discover. The scripts that drive the General
tab are `static/js/mediaStatusDateHandler.js` and `dateTimePicker.js`.

D1 (2026-11-21): the General tab for movies, shows, seasons and episodes.

- [x] The fields in the page's order with the page's values, choices and
      limits (score on the user's rating scale, "No Status"), the hidden
      fields posted back unchanged, notes, the KOReader document ID.
- [x] Dates: Start Now, Just Finished, Release Date (the runtime sets the
      start), Now, Copy from the other date, Clear (the start-cleared flag).
      A new Completed or In progress entry is dated now; a status change
      clears the dates the dialog filled, but not an end date the entry was
      saved without. Ported as pure functions with tests (`lib/track/rules.ts`).
- [x] Delete, Rewatch (with Since) / End rewatch, Save as another play
      (movies) / Save as new entry (episodes), Update / Add.
- [x] Opens from Track and Watched on the title and episode pages and from
      the Library card's Edit tracking (movies, shows, seasons); other types
      keep their Django page.
- [x] D2a (2026-11-21): anime, manga, games, books, comics, comic issues
      and board games, opened from the Library card's Edit tracking with the
      target the page's own card button opens (the card's `track`: an anime
      filed from TMDB opens as `anime`, with the entry as `instance_id`).
      Games: time played in the page's format ("3h 35min"), and typing it or
      changing the end backfills the start as end minus time played until
      the user sets the start (never on opening an edit). Book, comic and
      manga progress in pages or the user's percentage mode, as the page; an
      unchanged percentage keeps the stored count (it showed to 0.1%, so a
      book over 1000 pages moved a page on every untouched Update, 2026-11-21).
      Tested: page-field parity and an untouched Update keeping dates and
      progress for every type.
- [x] D2b (2026-11-21): music artists and albums and podcast shows, the
      page's shared tracker dialog (`build_music_tracker_context`,
      `build_podcast_show_track_context`, split from their renders). API
      targets `artist|album/music/{id}` and `podcast/{source}/{podcast_uuid}`
      on the same track route; the save and delete views answer JSON. The
      tracker forms have no `instance_id`, so the web dialog reads `tracked`
      to tell an edit from an add: Django's script counts every tracker as
      new and filled an empty end date with now on opening; fixed in Django
      too (`data-existing-entry` on the dialog form, read when there is no
      `instance_id` field).
- [ ] Songs and podcast episodes: the page's play-history dialog
      (`fill_track_song.html`), inline on the album and podcast detail pages,
      which are not on the web yet: build it with those pages.
- [ ] The web detail pages serve movies and shows only; the other types'
      Track buttons come with their detail pages.
- [x] D3 (2026-11-21): the Episode Plays tab for shows, seasons, grouped
      anime, podcast shows (`episode_bulk_save`), artists and albums
      (`music_bulk_save`): the page's form as the track screen's `plays`
      (range by watch order, summary and warnings ported from
      episodeBulkTrackForm.js), posted as JSON; the page's job writes the
      plays. Fixed with it: the job cut the start and end to dates, so the
      plays fell on midnight and same-day episodes shared one timestamp; it
      now keeps the picked times (Django tab too).
- [x] D4 (2026-11-21): the Discover tab (Visible or Hidden in Discover,
      Save off until it changes) as the track screen's `discover`, posted to
      `discover_toggle_hidden`, which answers JSON.
- [x] D5 (2026-11-22): the Collection tab, which the page has for single
      episodes only: the owned copies (summary lines as
      collection_entry_summary.html, each removable), the Add Copy form in
      the page's field order (first field across both columns) and the
      user's custom-field values, as the track screen's `collection`.
      `collection_add` and `collection_remove` answer JSON without flash
      messages. Fields gained the `checkbox` kind (posted only when ticked).
      Editing the custom-field schema stays on the page.
- [x] D6a (2026-11-22): the Metadata tab's plain forms as the track
      screen's `metadata`: display provider, metadata language, image URL
      (also posted with the General form, as on the page, so an untracked
      title saves it on Add) and custom metadata (prefixed `metadata-`
      names; date fields as dates). The four endpoints answer JSON.
- [x] D6b (2026-11-22): the Metadata tab's searches: remap the display
      provider's match, move the title to another library (lands on the new
      title's page), pick a Hardcover edition or a MusicBrainz release (the
      album dialog's Metadata tab). The search views answer
      `{results}` for `Accept: application/json`; the select views answer
      through `helpers.answers_json`, which turns the messages they queue
      into the JSON answer.
- [x] D6c (2026-11-22): Convert to Grouped Series for a flat MAL anime
      shown from TMDB or TVDB: the page's preview (lines and seasons, the
      conversion target marked) as `metadata.grouped`; `migrate_grouped_anime`
      answers JSON through `answers_json` and the web lands on the grouped
      show's page. Not opened in the browser (no such anime on the local
      account); covered by tests.
- [x] D7 (2026-11-22): the episode rows' history button (watched
      episodes) opens the Activity History dialog, as the page's
      fill_history.html: each entry's date and changes, Edit (the track
      dialog for that play, `instance_id`), Delete (DELETE
      `delete_history_record`). `GET /api/v1/activity/...` reads the page's
      `build_history_context`. Fixed with it: D6b's picker imported the
      shell's search icon, which split it into one more file and put the
      Library 0.1 kB over budget.
- [x] D8 (2026-11-22): the Collection tab's custom-field editor (the
      page's Manage custom fields): groups and fields (name, type, media
      types, a select's options) added, removed and reordered (up and down
      for the page's drag handles), saved as the whole schema to
      `collection_fields_save` (JSON already); the tab's custom fields
      re-render from the saved schema. The track screen's `collection`
      carries `schema` and `item_media_type`.

API (D1): `GET /api/v1/track/{type}/{source}/{id}/` reads
`build_standard_track_context`, split from `_render_standard_track_modal`.
The web posts the form to the page's own views with `Accept: application/json`
(`media_save`, `episode_save`, `media_delete`, `media_rewatch` answer
`{saved, message, instance_id, warnings}` or the form's errors), so saving
keeps one implementation; plain and HTMX posts answer as before.

Exact instants: the Django dialog dropped a play's microseconds on every
untouched Update (Django zeroes them in a DateTimeInput's initial value), so
`ExactPlayDatesMixin` keeps the stored value; the round trip is tested for
movies and episodes. The dialog, its host and strings load on the first
Track tap; the Library stays at 109.9 kB of 110.

### P4-E: History

Today's page (`app/history.html`, `history_views.history`, rows in
`components/ct/history_row.html`, days in `ct/history_day.html`): the month
view from the history cache, or 30 days per page for filtered views.

Parity checklist:

- [x] Type pills (All plus the user's types), as `media_type`; other
      filters stay.
- [x] Month view: this month, the newer month (not in the future), the older
      month, a year back; the month's name.
- [x] Filtered views (a title, date range, release dates, on this day, genre,
      person, logging style) paginate 30 days per page, numbered pages at the
      top and bottom.
- [x] Day: weekday, date, "N items · runtime" (or "N releases").
- [x] Row: the local time ("Released" in release mode, music's time range,
      a game's date range), poster (square for music and podcasts), title
      (the show for an episode), the episode code and title or the type,
      runtime and score; the title's page.
- [x] Row actions (not in release mode): Edit tracking (the web track
      dialog for that play), Add to custom lists, View your activity history
      (History for that title; games and board games as sessions).
- [x] Load more on a day over 30 plays (`history_day_fragment` answers JSON).
- [x] Filter History: From/To, media types, Activity or Release dates, genre,
      implied genre (all types or music); Clear filters, Apply.
- [x] The refresh banner while the cache rebuilds; the empty state.
- [x] The shell's History link and the detail page's History link open the
      web screen (`detailHref` maps `/history`).
- [x] The Library card menu's View history opens the web screen (with F1,
      once the detail-only strings left #lib/strings.ts).
- [ ] The activity sessions dialog (`history/sessions`) belongs to the detail
      pages: build it with them.

E1 (2026-11-22): `GET /api/v1/history/screen/` reads the page's own context
(`build_history_context`, split from `history_views.history`), each row as
the page writes it. Watch out: Tailwind utilities a new screen adds go into
the shared stylesheet every page loads (the Library went 0.1 kB over), so
the screen's layout lives in `lib/history/history.css`.

### P4-F: Calendar

Today's page (`events/calendar.html`, `events.views.calendar`, the CineTrack
agenda in `components/ct/calendar_agenda.html`): one month of releases.

Parity checklist:

- [x] Header and subtitle; previous and next month, Go to Today (the day and
      month tile).
- [x] Grid or List (`view`, saved as the user's calendar layout).
- [x] Grid: weekday headers in the user's week start, a cell per day with
      each release as title and code plus time, today marked, past days
      dimmed. Phones: Agenda (today onward in the current month) or Month (a
      day picker with up to three dots, then that day's releases); the choice
      kept in the browser (`ct-calendar-mode`).
- [x] List: days with releases, "Weekday, Month day", Today.
- [x] Release rows: poster, title, code, type, "at" time; the title's page.
- [x] The type and status filter in the browser under the page's own key
      (`yamtrack.calendar.filters.<user id>`), so it holds on both pages:
      Show all / Hide all, a status submenu per type, types and statuses
      without releases this month dimmed, the button's label (All Types, No
      Types, one type, N Types, " ·" for a status filter).
- [x] Calendar Actions: Fetch New Releases (queued; `reload_calendar` answers
      JSON through `answers_json`), Download Calendar.
- [x] Export link: media types (the user's enabled ones on) and statuses,
      the iCal URL with repeated `media_types` and `status`.
- [ ] The list view uses the agenda rows (poster, code, time); the page's
      older list rows show a square image. Same data.

F1 (2026-11-22): `GET /api/v1/calendar/screen/` reads the page's own context
(`build_calendar_context`, split from `events.views.calendar`). With it, 60
strings only the detail and person pages use moved from #lib/strings.ts to
`lib/details/strings.ts`: every page loads less (the Library 110.0 to
109.4 kB).
