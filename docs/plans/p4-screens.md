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
- Discover's match signal wrapping (`test_discover_match_signal_...`): the
  signal shows only in the Django page's debug panel, which stays on Django
  (`?discover_debug=1`); nothing for the web screen.
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
| P4-G | Discover | G1 (2026-11-22): type tabs with More, the ⋮ menu (Refresh recommendations, Hidden from Discover), the hero, rows with Add to Planning and Hide (toast with Undo), the rest of the rows at the page's end, the rebuild wait, the Hidden view with Unhide. G2: a card's Add to custom lists dialog |
| P4-H | Statistics | H1 (2026-11-23): range, media-type and compare controls, Refresh with the cache wait, Monthly recap link, hero, highlights, summary cards, Activity History or Played Hours by Media Type, Statistics Preferences. H2 (2026-11-23): the filtered charts. H3 (2026-11-23): per-type overviews, talent section, nav |
| P4-I | Lists | I1 (2026-11-23): the index (My Lists / Shared with Me, search, type, sort, covers, more on scroll), create/edit/delete, CSV, MDBList and Trakt imports; the nav opens it. I2 (2026-11-23): a manual list's page. I3 (2026-11-23): smart lists with the rule builder, Recommendations and Activity History dialogs |
| P4-J | Settings and integrations | J1 (2026-11-27): the settings route and nav, Account, Appearance, Notifications, Media types, About. J2 (2026-11-27): Preferences, Metadata, Connected apps, Export, Advanced. J3 (2026-11-27): Integrations and RSS. Import stays P4-K |
| P4-K | Imports | K1 (2026-11-27): the Import page (settings, source tiles with the media-type filter, activity panel with cancel, undo, schedule and by-source delete) and the file and username imports (Floppy, Yamtrack, CLZ, HowLongToBeat, Grouvee, IMDB, Goodreads, Hardcover, StoryGraph, TV Time, MyAnimeList, Kitsu, Simkl, MDBList). K2 (2026-11-27): Trakt, AniList, Last.fm, Koito, Steam, Xbox, PlayStation, Pocket Casts, GPodder. K3 (2026-11-28): Plex, Radarr, Sonarr, Stremio, Audiobookshelf, Storyteller, KOReader. Every Import source is drawn by the web |
| P4-L | Detail pages for the other types | L1 built (2026-11-28): manga, games, books, comics, board games. L2 built (2026-11-28): music artist and album pages and podcast shows, with the song and podcast-episode play dialog. L3: anime (its page and episodes), the activity sessions dialog, the ratings graphs, the studio page |
| P4-M | Search and Add New Item | Planned (2026-11-28). M1: the search page (with the parent-show search). M2: the shell's search palette. M3: Add New Item (manual create) and Add Recommendation; the search-then-track web test |
| P4-N | Floating sidebar | Planned (2026-11-28). The shell honours Appearance's sidebar style: Floating (the detached bar) with Expand on hover, Always expanded or Icons only; Attached stays the default |
| P4-O | Leftover pages | Planned (2026-11-28). Tags, Collection, the Monthly recap, lists the user can only view, the collaborator search |

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

### P4-G: Discover

Today's page (`app/discover.html`, `app.discover_views.discover_page`, the
CineTrack header `components/ct/discover_header.html`, the hero
`ct/discover_hero.html`, rows `discover_rows.html` and `discover_row.html`,
cards `media_card.html` with `hover_action_mode='discover'`).

Parity checklist:

- [x] Title; on phones and tablets a search button (the web opens `/search`).
- [x] Type tabs: All and the primary types, the rest under More (its label
      becomes the picked type); the choice is saved as the user's last
      Discover type.
- [x] ⋮ menu: Refresh recommendations (queues the rebuild, then waits on the
      page's cache status for fresh rows and reloads, "Recommendations
      refreshed."; the wait ends when the page shows another type), Hidden
      from Discover with its count.
- [x] Hero: one pick per row with a backdrop (or logo), "Type · Genre ·
      Year", Add to Planning, Details; dots; advances every 7 s unless
      hovered, focused or reduced motion.
- [x] Rows: title, cards (poster, title, "Type · Year"; square for music and
      podcasts), the empty-row message (the continue rows have their own).
- [x] Card quick actions: Add to Planning, Hide from Discover (on hover or
      focus; always on touch screens). A toast with the message and Undo
      for 8 s.
- [x] The rest of the rows load when the page reaches its end (`show_more`);
      as on the page, the rows on screen stay while the longer tab builds.
- [x] Building Discover rows (rebuilding, polled until ready), No Discover
      rows available, the "Refreshing recommendations in background..."
      banner.
- [x] Hidden from Discover: back link, count sentence, rows (poster, title,
      "Type · Year · Hidden 22 Nov"), Unhide; the empty message.
- [x] Add to custom lists from a card (G2): the user's manual lists with
      Add or Remove, the tag filter, "On N lists" (`lists_modal` and
      `list_item_toggle` answer JSON). The full Lists screens stay P4-I.
- [ ] The hero's poster accent tint (the page samples the poster's colour);
      the web uses the accent colour.
- [ ] The debug panel (`?discover_debug=1`) stays on the Django page.

G1 (2026-11-22): `GET /api/v1/discover/screen/` reads the page's own context
(`build_discover_context`, split from `discover_page`); each card carries the
exact fields the page posts to `discover_action`, with the stored image (a
Hide seeds a new Item from it). `discover_action` answers JSON for
`Accept: application/json` (`{action, message, undo_token}`; 400s as
`{error}`), after the tab cache is patched, so the web re-reads the screen.
The row styles (`.ct-row`) moved from the Home stylesheet to
`lib/styles/cards.css`: Home and Discover share `lib/home/Row.svelte`.
All repeats row keys (each type's Trending Right Now is `trending_right_now`;
the Django page's ids repeat too), so the web keys rows by position.

G2 (2026-11-23): each card carries `lists_url` (the page's `lists_modal`
URL); with `Accept: application/json` it answers the item, its manual lists
with `has_item`, the tags and `on_list_count`, and `list_item_toggle` answers
`{list_id, has_item}` (403 for a smart list, 500 with `{error}`). The dialog
is `lib/discover/ListsDialog.svelte` on `lib/ui/Dialog.svelte` (a sheet on
phones). `lists_modal` no longer runs the episode-title backfill for other
items: with `force=True` it fetched a "season" and the title itself for every
movie or show that opened its lists.

### P4-H: Statistics

Today's page (`app/statistics.html`, `app.statistics_views.statistics`,
`static/js/date-range.js` and `statistics-charts.js` on Chart.js). Three
slices; the nav keeps the Django page until H3.

Parity checklist:

- [x] H1: the range dropdown (Predefined Ranges with their dates, "All
      activity"; Custom Range with Start/End Date, Cancel, Apply Range), saved
      as the user's default range for presets, as on the page.
- [x] H1: the media-type dropdown (All media, the enabled types), switched
      in the browser and kept in `media-type`.
- [x] H1: Compare to (Previous period, Last year, No comparison, each with
      the compared dates) for finite ranges; posts the user's compare mode.
- [x] H1: Refresh statistics (presets: queue, wait on the cache status,
      "Statistics refreshed."; custom ranges reload), the "Refreshing
      statistics in background..." banner on load, Monthly recap (Django).
- [x] H1: hero ("You've spent N hours with N {titles}. That's N days of
      {flavour}."), highlight cards (First Play, Last Play, Today in
      (your) history; phones swipe with dots).
- [x] H1: summary cards (Completed Items, Average Rating, Most Active Day,
      Current Streak with Longest, Activity against the compared period).
- [x] H1: Activity History (heatmap, every type) or Played Hours by Media
      Type (stacked, days bucketed into weeks, months or years as the page,
      filtered by type), per the user's Activity History View.
- [x] H1: Statistics Preferences (view, duration format, week start, rating
      scale, anime split with TVDB and no Anime type).
- [x] H1: a database error is an error state, not zeros.
- [x] H2: Activity Rhythm (quantile tiers), Hours by Media Type (Top
      Genres for TV, movies, anime, music and games, with the overlap note),
      Hours by Month, Day of Week and Time of Day, consumption tiles (Per
      Year/Month/Day, Average Playtime/Length), Status Composition, Rating
      Distribution, Status Breakdown, Average Rating; all follow the media
      type as on the page.
- [x] H3: per-type Activity Overviews (TV, anime, manga, movies, games,
      books, comics, music, podcasts: their year, month and daily charts and
      ranked lists with the templates' captions), board games Most Played,
      the Top Played empty state.
- [x] H3: the talent section for All, TV, movies, anime and games (Featured
      Repeat Player with Known For and View Profile, their titles, Role
      Leaders with Plays/Time/Titles and a click to feature a person, Studio
      Footprint and Taste Signals with their sorts).
- [x] H3: the nav's Stats and `/statistics` links open the web page; the
      Monthly recap stays the Django page.
- [ ] Monthly recap stays the Django page.

H1 (2026-11-23): `GET /api/v1/statistics/screen/` reads the page's own
context (`build_statistics_context`, split from `statistics`; it keeps the
database-error fallback) for the page's `start-date`, `end-date`, `compare`;
`media-type` never reaches the API. Charts are plain SVG (Chart.js does not
fit the 110 kB budget). The bar chart and the preferences sheet load on first
use: with them static the page put the Library and Discover over budget
(shared chunks re-split), not only itself.

H2 (2026-11-23): the screen's `charts` (rhythm, hours by type, top genres,
combined hours, consumption, status, ratings) drawn as plain SVG
(`ChartsTop`, `ChartsRest`, `Donut`, `Rhythm`) and loaded after the page with
their own CSS and strings (`charts.css`, `chart-strings.ts`), so the page
stays under its budget.

H3 (2026-11-23): the screen's `overviews` (`api/statistics_overviews.py`
maps the nine overview templates to charts and ranked lists), `board_games`
and `no_top_played`; `GET /api/v1/statistics/talent/`
(`api/statistics_talent_screen.py`) reads the talent fragment's own context
(`build_talent_fragment_context`, split from statistics_talent_fragment) and,
like update_top_talent_sort and select_featured_person, re-aggregates for
`media_type` and features `person_source` + `person_id`. The sorts post to
the page's own views (they already answer JSON). Both sections load after
the page.

### P4-I: Lists

Today's pages: the index (`lists/custom_lists.html`,
`lists.views_list_browse.lists`), a list (`list_detail.html`,
`smart_list_detail.html`), the form (`components/list_form.html`), the
recommendations and activity pages. Three slices. Public views, the public
profile, RSS/JSON and CSV export stay Django (they work signed out).

Parity checklist:

- [x] I1: "Lists", "N lists · N shared with you"; New List with its menu (New
      list, New smart list, Import from Trakt, Import from MDBList, Import CSV,
      Public profile).
- [x] I1: My Lists / Shared with Me; the toolbar from six lists or while
      filtering: search (300 ms), type, sort (picking the active sort flips
      it; saved as the user's list sort).
- [x] I1: cards with the first four posters (batched), name, "N items ·
      Shared/Public/Private · N% completed", the last-watched line under that
      sort, Edit for editors; 20 a page, more on scroll; the empty state.
- [x] I1: create and edit (name, description, tags, collaborators by exact
      username, smart, public, recommendations, notes, custom URL with its
      preview and errors), Activity History link, delete with a confirm step.
      A new smart list opens its rules on the list's page.
- [x] I1: CSV import (queued), MDBList (connect with API key and sync
      frequency, import by URL or ID, Sync Now, Disconnect, connection
      problem), Trakt (setup with the redirect URI, client ID and secret,
      Login with Trakt by device code).
- [x] I1: the nav's Lists link and `/lists` links open the web index.
- [x] I2: a manual list's page: header (items, completion, Public · Links,
      collaborators, media type breakdown, description), search, type and
      status filters, sort, grid and table with the Library's columns, custom
      order (Edit Item Order moves), bulk select, Edit List, more on scroll.
      Add New Item, Add Recommendation, Activity History, Recommendations and
      Export open the Django pages; lists the user can only view open the
      Django page too.
- [x] I3: smart lists: the Smart List chip, the rules summary, Edit Smart
      Rules with the builder (search, types with season and episode kept out
      of "all", statuses, the Library's filter menu, rating range, release
      and date added ranges and windows, linked lists, sort), saving as it
      goes ("Saving…", "Save failed").
- [x] I3: Recommendations (Approve and add, Deny) and Activity History as
      dialogs on the list page, for manual and smart lists.
- [ ] Add Recommendation stays the Django search page, like Add New Item.
- [ ] Lists the user can only view (shared read-only, others' public lists)
      still open the Django page.
- [ ] The collaborator field takes exact usernames: the page's select2 user
      search has no endpoint the web can use.

I1 (2026-11-23): `GET /api/v1/lists/screen/` reads the page's own context
(`build_lists_context`, split from `lists`). The form views answer JSON for
`Accept: application/json`: `list_edit_form` returns every field, and the
web posts every field back (the form saves them all: a field left out would
be cleared, smart rules included); `list_create` and `list_edit` return
`{saved, list, location}` or `{saved: false, errors}` (the page drops an
invalid edit silently) and take `collaborator_usernames`; `list_delete`
returns `{deleted}`. Imports use the list imports API. Trakt always uses the
device code flow on the web, so its setup shows the out-of-band redirect URI.

I2 (2026-11-23): `GET /api/v1/lists/page/<reference>/` reads the page's own
context (`build_list_detail_context`, split from `list_detail`) and draws the
items with the Library's card and table builders (the grid's items go
through the same table adapter). It answers `handled: false` with the Django
URL for smart lists, read-only lists and missing lists, and the web route
redirects there. Moves use `list_reorder_item`, which renumbers the whole
list, so paging stays right. Fixed in passing: the Django list page's
`bulk_action_data` was a one-element tuple (a trailing comma), so its bulk
menus read a JSON array and showed no options. The grid's card loads with
the grid to keep the page within its budget.

I3 (2026-11-23): the same endpoint reads a smart list's page context
(`build_smart_list_detail_context`, split from `_smart_list_detail_response`)
and adds `smart`: every saved rule, the summary chips, and the builder's
options (the Library's filter options from `smart_filter_data`, the types,
statuses and linked lists). `list_smart_rules_update` rebuilds the whole
rule set from what it is sent, so the builder posts every rule back (a test
posts the screen's rules unchanged and checks nothing moves). Saves run one
at a time and only the latest pending is sent, so a slow save never lands
after a newer one; the edit state is the page's, not the URL's.
`list_recommendations`, `list_activity`, `approve_recommendation` and
`deny_recommendation` answer JSON for `Accept: application/json`. Fixed in
passing: `can_recommend` is a model method, so every list offered Add
Recommendation. The builder's and dialogs' styles load with them
(`list-extras.css`).

Page budgets went from 110 to 115 kB with I1 (the user's call, 2026-11-23):
each new route grows the shared route table and re-splits shared code, and
an empty Lists route alone tipped Discover over.

### P4-J: Settings and integrations

One web route, `/next/settings/<slug>` (the Django path's last segment), with
each page loaded on its own; the empty route cost about 0.1 kB on the other
pages. `GET /api/v1/settings/screen/<slug>/` returns the settings nav (each
item says whether the web draws it) and the page's data, read the way the
Django view reads it; any other page answers `handled: false` and the web
opens its Django page. The web saves through the Django views' own forms,
which answer JSON for `Accept: application/json`: the P1 settings endpoints
differ from the pages in places (no media-type order, missing preference
fields, the notifications PATCH that turned the premiere digest off), so
they are used only where they match (notification exclusions and the test
send). Every form page has a round-trip test: the screen's values posted
back change nothing.

- [x] J1: the settings nav (sections You, Library, Data; a select on phones);
      the shell's Settings, Appearance and Notifications links open the web.
- [x] J1: Account: username and password (the session stays signed in).
      Setting up or replacing the authenticator and regenerating recovery
      codes stay on the Django page (it shows the secret and codes once).
- [x] J1: Appearance: sidebar style and floating behaviour; the hidden
      detail-layout editor's layouts post back unchanged. The web shell does
      not follow these settings yet; they shape the Django pages.
- [x] J1: Notifications: Apprise URLs, the three switches, Test
      Notifications, exclusions with search, the RSS link (Django).
- [x] J1: Media types: the touch overlay switch, which types show and their
      order (arrows instead of drag handles); saving refreshes the shell.
- [x] J1: About: description, install, resources, API documents (open or
      download, no inline preview), attributions, license, version.
- [x] J2: Preferences: every field posts back (the view resets the
      auto-pause rules, region and language when they are missing); labels
      and options come from the screen, a stored value the list lacks
      (UNSET) shows as Not set; auto-pause rules add, edit, remove.
- [x] J2: Metadata: the provider per library (only configured sources),
      anime library mode, the anime conversion prompt (from the POST answer,
      not the session); provider keys with the masked preview only; instance
      keys for superusers, personal keys for anyone; Save is off until a key
      is typed and Remove is its own button (a blank field deletes).
- [x] J2: Export: the CSV form answers with the file (blob download);
      errors answer JSON; schedules (delete), the last 7 days of runs,
      backup and snapshot folders, Letterboxd.
- [x] J2: Advanced: logs (superusers), image caching (superusers), each
      cache clear and Clear All behind the Django page's confirm text,
      delete one media type behind a typed DELETE, TMDB proxy (never read
      back; Save off when blank, Remove separate).
- [x] J2: Connected apps: signed-in installs (Sign out), sync connections,
      crash reports (newest 50, Export JSON).
- [x] J3: Integrations: the card grid (?open= per panel, Back), matching
      review, onboarding banner, watched-state sync, legacy key (regenerate
      behind a confirm), app tokens (the new secret comes back once in the
      create answer, never the session), connected apps, Jellyfin (official,
      unofficial with webhook events, Floppy → Jellyfin: connect, settings,
      push, pull, TSV upload), Plex (usernames, libraries, shares, status),
      Emby, Kodi, Stremio (install credentials, catalog status), Seerr, Nuvio.
      Forms that clear a missing field always post every field.
- [x] J3: RSS: media type, row, skip options, the feed URL, a JSON preview.
      Reached from Notifications, not the nav.
- [ ] Import stays P4-K.

Fixed in J1: the notifications API (`PATCH /api/v1/user/notifications/`)
left the premiere digest out of the form, so every PATCH turned it off; it
now reads and writes all four fields.

Fixed in J2:
- `helpers.answers_json` answered a bare 403/404 as `{"saved": true}` and
  turned a JSON GET into an answer; refusals now fail with their status and
  GET renders the page.
- Preferences reset the provider region and metadata language to their
  defaults whenever TMDB's lists failed to load; it now keeps them.
- The settings route could hand a page the next page's screen for one
  update while moving between pages (a crash in the old page); the page
  component and its screen are now set together.

Decided in J3: the screen returns the account's legacy key and the webhook
URLs built on it, as the Django page renders them. The settings screen is
`NEVER`-scoped, so only the signed-in browser session reads it; a test
checks an API token is refused.

Fixed in J3: after a save the Integrations page fell back to the card grid
(a refresh resets SvelteKit's shallow-routing state); the open panel now
lives in the component and follows ?open= links and Back/Forward.

Not verifiable locally (J3): a filled RSS preview (the Django preview is
empty here too); connecting a real Jellyfin; Plex libraries and shares
(need a connected Plex).

Not verifiable locally: clearing caches and deleting a media type need
Redis (`delete_pattern`); the local server has none, so both answered 500
there (the Django page fails the same way). Server tests cover them.
Report only: the search-cache clear is instance-wide and has no superuser
check (as on the Django page).

### P4-K: Imports

- [x] K1: the page: Import Settings (each change posts all three), the
      tiles with the media-type filter and the template download, ?open=
      deep links, the guided-setup banner; the activity panel polls
      `import_data_activity` as JSON every 5 s while visible.
- [x] K1: the dialogs for Floppy, Yamtrack, CLZ, HowLongToBeat, Grouvee,
      IMDB, Goodreads, Hardcover (key and/or CSV), StoryGraph, TV Time (two
      files), MyAnimeList, Kitsu, MDBList, and Simkl (a real form submit to
      Simkl's sign-in, `next` back to the web page). Every form posts the
      page's frequency, time and mode (several views fail without them).
- [x] K2: Trakt (public username, OAuth as a real form submit with `next`,
      data export with several files), AniList (public or OAuth), Steam,
      and the accounts: Last.fm, Koito, Xbox, PlayStation, Pocket Casts,
      GPodder (connect, Sync now, full history, Disconnect). The screen
      carries each account's state, never a key, token or password.
- [x] K3: Plex (sign-in as a real form submit with `next` and
      `auto_import=0`, live status and libraries, content kinds, usernames,
      watchlist sync), Radarr and Sonarr (instances), Stremio,
      Audiobookshelf, Storyteller (device login: code, approval link,
      polling, cancel), KOReader (connect, settings, sync).

Decided in K1: the screen carries the first activity snapshot, but a
Celery result-store outage leaves it null instead of failing the page (the
panel keeps polling). Locally, with no Redis, reading a queued task's status
fails, so the activity answers 500 there once an import is queued; the
Django panel fails the same way.

Decided in K2: after any account action the page reloads its data whether
the answer saved or failed (Xbox and PSN connects can save the account and
then fail to schedule). The connect views call the provider before
answering, so the dialog says it is checking. None of the K2 controls is
mode- or demo-gated, as in Django; the Trakt export is gated only on a
one-time import.

Decided in K3: Plex's sign-in from the web passes `auto_import=0`, so the
callback does not queue the setup wizard's default import (the wizard,
without the flag, keeps it). The Plex library list no longer carries each
server's URI and access token to the browser, on the Django page too.

### P4-L to P4-O: what still opens Django (planned 2026-11-28)

After P4-K every screen in the original list is on the web. These are the
pages and pieces that still open Django, collected from the follow-ups
above, so P5 can cut over. Order not decided yet; each on the board.

P4-L, detail pages for the other types (C follow-ups):
- [x] L1 (2026-11-28): the detail page for manga, games, books, comics and
      board games (`details/<source>/<media_type>/...`): the hero's progress
      line (the page's activity subtitle) and a book's series line, no
      filled action (Track opens the web Track dialog), the Information
      grid with `format` and linked Authors, Genres (chips to the web
      Library's genre filter), Studios, a game's Time to Beat (or the
      page's not-available note), a comic volume's Issues (Read mark, Track
      as `comicissue`, the issue page on Django, "Show ..." pages by
      `episode_page`). The user's layout family picks the sections.
      Not in L1: the activity sessions dialog behind the progress line
      (L3), IGDB trailers and screenshots (the page's carousel), the
      Hardcover `?edition_id=` preview (the Track dialog's Metadata tab
      picks the edition), Notes and Collection sections (not on the movie
      page either).
- [x] L2 (2026-11-28): music artist and album pages (`details/music/artist/...`, album
      releases) and podcast shows, with the song and podcast-episode
      play-history dialog (`fill_track_song.html`).
      Scope (decided 2026-11-28): three read endpoints, one phase each
      (`details/music/artist/<id>/`, `.../album/<id>/`,
      `details/podcast/<source>/<uuid>/` with `episode_page`); the web
      pages on their own routes (own bundles). The actions reuse their
      JSON twins unchanged: the tracker dialog (`track/artist|album|podcast`,
      the album's release picker in its Metadata tab), add a play
      (`music/songs/plays`, `podcasts/episodes/plays`), delete a play
      (`history/<type>/<id>`), Sync (`music/artists/<id>/sync-discography`,
      `music/albums/<id>/resync`). The Django renderers are split into
      context builders the page and the API share. The podcast feed
      refresh runs on the page's first read only, never on an episode page.
      A canonical album or merged artist answers 400, so the web falls back
      to the Django page, which redirects.
      Not in L2: Collection and Notes sections (as L1), the album's tags,
      a track's own score, the podcast in-progress entry's delete, delete
      all plays (its artist filter misses credited albums), mark all played
      (no page offers it), the cover and photo polling (the page shows what
      is stored; a reload picks up the rest).
- [ ] L3: anime: its page (grouped TMDB/TVDB anime on the show machinery,
      flat MAL anime with the mapped episode preview) and its episode pages;
      the activity sessions dialog (`history/sessions`), the ratings graphs,
      the studio page. Moved out of L1 (2026-11-28): anime's next-episode
      mark posts episode events, so it needs its own contract check.
      Scope (decided 2026-11-28), two parts:
      L3a, anime: grouped TMDB/TVDB anime on the show machinery with anime
      season and episode URLs; every check and mark-next on an anime page
      sends `library_media_type: "anime"` from the page type (an unwatched
      row has no Item to read it from); the season read gains an anime
      route and the episode read an optional `?parent=anime`, tv answers
      unchanged. Checks only where the ensure route takes the source
      (`check_source_type("tv", ...)`: tmdb, tvdb, manual, as
      `api/fork_helpers.py` widens `VALID_SOURCES` at import). Flat MAL anime is read-only: the
      mapped episode preview links to the provider's anime episode pages,
      no checks (a mark there files a grouped show beside the MAL entry and
      does not move its progress).
      L3b: the activity sessions dialog behind the progress line, the
      ratings graphs (their own endpoint, fetched on open), the studio page.

P4-M, Search and Add New Item:
- [ ] M1: the search page (`search`, `search/parent_tv`).
- [ ] M2: the shell's search palette (`search/palette`).
- [ ] M3: Add New Item (`create`) and Add Recommendation (both now the
      Django search page); the web test for search, then track (the skipped
      `test_tv_manual`, `test_tv_completed`, `test_season_*`).

P4-N, the floating (detached) sidebar:
- [ ] The web shell always draws the attached sidebar from lg and the icon
      rail from md. Appearance's `sidebar_style` = Floating and its
      `floating_sidebar` (Expand on hover, Always expanded, Icons only) are
      saved by the web Settings (J1) but only the Django shell draws them.
      Draw the floating bar in `web/src/lib/shell/Shell.svelte` from the
      user's setting; Attached stays the default; phones keep the bottom bar.

P4-O, leftover pages:
- [ ] Tags (`tags`) and Collection (`collection/`).
- [ ] The Monthly recap (`statistics/recap`).
- [ ] Lists the user can only view (shared read-only, others' public lists)
      and the collaborator search (needs a user-search endpoint).

Staying on Django on purpose: Discover's debug panel (`?discover_debug=1`).

