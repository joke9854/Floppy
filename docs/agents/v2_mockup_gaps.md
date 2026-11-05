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
