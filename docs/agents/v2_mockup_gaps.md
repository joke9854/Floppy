# v2 (Apple layout) mockup gaps

Features the live CineTrack app has that the Penpot "Apple layout (v2)"
boards do not show. From Phase 5 on, each phase hides these (CineTrack only,
nothing deleted) and lists them here. Once the six phases are done, review
each entry: keep, improve, or remove.

Phase 4 predates the rule: its entries are still visible.

| Phase | Page (board) | Feature | State | Where |
| --- | --- | --- | --- | --- |
| 4 | Library (A3/A16) | View settings gear menu (bulk select, share view, entry grouping, table/grid) | Visible | `filter_toolbar.html` (`ct-settings-menu`) |
| 4 | Library (A3/A16) | Shows / Seasons segment beside the title | Visible | `ct/library_header.html` |
| 4 | Library (A3) | "No Status" status tab | Visible | `ct/library_status.html` |
| 4 | Library (A3/A16) | Filter label shows the active filters instead of "Filter" | Visible | `filter_menu.html` |
| 4 | Library (A16) | Filter button on phones (the board shows only status and sort) | Visible | `filter_toolbar.html` |
| 4 | Library (A16) | Type switch lists every enabled type (the board shows Shows, Movies, Anime, More) | Visible | `ct/library_header.html` |
| 4 | Library (A3/A16) | Next-episode quick link on cards (user preference) | Visible, moved top-left | `media_card.html` (`media-next-ep-link`) |
| 4 | Lists (A13) | Search field, type filter and sort menu | Visible | `lists/custom_lists.html` |
| 4 | Lists (A13) | Public Profile button | Visible | `lists/custom_lists.html` |
| 4 | Lists (A13) | New List split menu (smart list, Trakt/MDBList/CSV import) | Visible | `lists/custom_lists.html` |
| 4 | Lists (A13) | "% completed" in the card meta line | Visible | `lists/components/ct_list_card.html` |
| 5 | Discover (A8/A19) | Refresh recommendations button | Hidden | `ct/discover_header.html` |
| 5 | Discover (A8/A19) | "Hidden" view (items hidden from Discover, to unhide them) | Hidden | `ct/discover_header.html` |
| 5 | Discover (A8/A19) | Hero prev/next arrows, poster thumbnail and row-name eyebrow | Hidden | `ct/discover_hero.html` |
| 5 | Discover (A8/A19) | Row "why" line, match signal and "Refreshing…" note | Hidden | `discover_row.html` |
| 5 | Discover (A8/A19) | Card match % ("Taste match" etc.) and provenance line | Hidden | `discover_row.html` |
| 5 | Discover (A8/A19) | Alternate-title ⓘ button on cards | Hidden | `input.css` (`.ct-rail-row.ct-library-grid`) |
| 5 | Discover (A8/A19) | Card hover actions (Add to Planning, Hide from Discover, Add to list) | Visible (hover only; the only way to hide an item) | `media_card.html` |
| 5 | Discover/Search (A8/A9/A19) | Top bar search field, its suggestions dropdown and book barcode scan | Hidden on these two pages | `input.css` (`.ct-topbar`) |
| 5 | Search (A9) | Grid / list layout toggle (always list rows) | Hidden | `ct/search_header.html` |
| 5 | Search (A9) | Result counts ("N results · Showing first N") | Hidden | `search.html` |
| 5 | Search (A9) | Lists, history and info buttons of the classic list card | Hidden | `ct/search_row.html` |
| 5 | Search (A9) | "Matched: …" alternate-title line | Hidden | `ct/search_row.html` |
| 5 | Search (A9) | Pagination | Visible (needed to reach page 2+) | `search.html` |
| 5 | Search (A9) | Music search (artists/albums grids) | Visible, unchanged | `search.html` |
| 5 | Discover (A8/A19) | "Refreshing recommendations in background…" banner and the refresh/undo toasts | Visible (transient states) | `discover.html` |
| 6 | Settings (A5/A22) | RSS and About rows in the settings nav (URLs still work) | Hidden | `users/components/ct_settings_nav.html` |
| 6 | Settings (A5/A22) | Preferences row in the settings nav | Visible (core tracking options live there) | `users/components/ct_settings_nav.html` |
| 6 | Settings (A5/A22) | "Configure your account and preferences" line under the title | Hidden | `input.css` (`.ct-settings > .mb-8 > p`) |
| 6 | Integrations (A5) | "Jump to integration" filter bar | Hidden (the card grid replaces it) | `users/integrations.html` |
| 6 | Integrations (A5) | Setup panels for each integration | Visible only after Manage/Connect/Set up on its card (or `?open=`) | `users/integrations.html` |
| 6 | Integrations (A5) | Legacy API key, App tokens, Connected apps, Watched-state sync, Nuvio | Visible behind a "API key, app tokens…" link under the grid (`?open=api`); needed for webhooks and apps | `users/components/ct_integrations_grid.html` |
| 6 | Integrations (A5) | Matching review and saved match decisions | Visible (only when there are entries; the only place to fix matches) | `users/integrations.html` |
| 6 | Integrations (A5) | Guided-setup banner | Visible (transient, onboarding only) | `users/integrations.html` |
| 6 | Appearance (A22) | Detail pages layout section | Hidden (its state still posts unchanged) | `users/appearance.html` |
| 6 | Appearance (A22) | Section icons and subtitles | Hidden | `input.css` (`.ct-appearance`) |
| 6 | Appearance (A22) | Every theme preset beyond the board's five, and the custom palette | Visible (choosing a theme is core) | `users/appearance.html` |
| 6 | Appearance (A22) | Save bar | Visible (settings apply only after saving) | `users/appearance.html` |
| 6 | Login (A15) | Register / "No account exists yet" links | Visible when registration is on (the only way to sign up) | `account/login.html` |
| 6 | Login (A15) | "Sign-ups are disabled · Host your own" line | Hidden | `account/login.html` |
| 6 | Login (A15) | Social provider buttons are labelled with the provider name, not "Continue with SSO" | Visible (several providers can be configured) | `socialaccount/snippets/provider_list.html` |

## Mockup parts not built

The reverse gap: things the boards show that the live app cannot back yet,
because they need data or endpoints that do not exist. Each one waits for a
decision: build the backend, adapt the design, or drop it.

| Phase | Page (board) | Mockup part | Missing | Where it would go |
| --- | --- | --- | --- | --- |
| 5 | Discover (A8/A19) | "See All" link on each row | No per-row Discover page to link to | `discover_row.html` (`ct-row-head`) |
| 5 | Discover (A8) | Hero overview text | Discover candidates carry no overview | `ct/discover_hero.html` |
| 5 | Discover (A8) | Hero runtime ("2h 46m") | Candidates carry only a runtime bucket | `ct/discover_hero.html` |
| 5 | Discover (A8/A19) | Hero rank ("#1 trending this week") | No rank on the candidate | `ct/discover_hero.html` |
| 5 | Discover (A8/A19) | Status badges on cards for tracked items | Candidates have no tracking state | `discover_row.html` |
| 5 | Discover (A8/A19) | A row titled "Because You Watched …" | Exists only as a per-card provenance line (hidden above), not as a row | Discover row registry |
| 5 | Search (A9) | "All" tab and per-type result counts | Search runs one media type per request | `ct/search_header.html` |
| 5 | Search (A9) | "People" tab | No person search | `ct/search_header.html` |
| 5 | Search (A9) | Network / author in the row meta ("FX", "Katherine Arden") | Not in search results | `ct/search_row.html` |
| 6 | Integrations (A5) | Connected / Not connected for Emby, Kodi and Stremio | No stored connection state (no last-received time); cards show the method and "Set up" | `users/components/ct_integration_card.html` |
| 6 | Integrations (A5) | Stremio "Every 2 hours · Synced 14:02" | No last-sync time on the page; the Stremio import runs from the Import page | `users/components/ct_integrations_grid.html` |
| 6 | Integrations (A5) | Trakt "Sign-in expired 1 Nov · Fix" | Trakt stores client credentials only, no sign-in or expiry; the card says Configured / Not connected | `users/components/ct_integrations_grid.html` |
| 6 | Appearance (A22) | "Changes apply immediately" | Appearance saves on submit; the subtitle says "Changes apply after saving." | `users/appearance.html` |
| 6 | Login (A15) | "+ 4 more" after the brand chips | No fixed count; says "and more" | `allauth/layouts/entrance_v2.html` |
