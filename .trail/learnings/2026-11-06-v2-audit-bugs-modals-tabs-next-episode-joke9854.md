---
title: "v2 audit fixes: modal stacking, status tabs, show-level next episode, live counts, non-blocking backdrop"
author: Joke9854
date: 2026-11-06
branch: CineTrack-API
touches:
  - src/static/css/input.css
  - src/templates/base.html
  - src/templates/app/components/ct/library_status.html
  - src/templates/app/components/ct/detail_hero.html
  - src/templates/app/components/ct/episode_row.html
  - src/templates/app/components/ct/series_progress_card.html
  - src/templates/app/components/ct/episode_sections.html
  - src/templates/app/components/ct/home_grid.html
  - src/templates/app/components/ct/detail_backdrop.html
  - src/templates/app/components/ct/detail_secondary.html
  - src/templates/app/media_details.html
  - src/static/js/ctShell.js
  - src/app/providers/tmdb.py
  - src/app/templatetags/app_tags.py
---

## Decided
- Modals stay `z-50` everywhere. `.ct-rail` and `.ct-bottom-nav` dropped from 55 to 45 and the ct top bar from z-50 to z-40, so every modal and its backdrop cover the sidebar without touching ~57 modal templates.
- Library status tabs send their own status through `hx-vals`, which overrides `#filter-form` (htmx 2 replaces the key). htmx reads the form in the same click, before Alpine re-renders the `x-for` hidden inputs, so the form alone always carried the previous tab.
- The show hero's Mark button carries the show's next episode from `ct_detail_next_episode` (`TV.next_episode_target`, the same as Home) as data attributes. `ctShell.js` uses that target for the button and W and moves `.is-next` onto that row. Rows render both "Up next" and the air date, and CSS shows one. Without a server target (season pages, untracked shows) it falls back to the first unwatched row.
- Live counts: elements with `data-ct-live` and an id (`#ct-mark-next`, `#ct-series-progress`, `#ct-season-watched`) are swapped from a re-fetch of `location.href` after any successful POST on the page, including the toast's Undo. Home cards (`data-ct-card-key`) re-render from their row's `?load_row=<id>&offset=0` and keep `data-ct-watched-instance`, so Undo still finds them.
- The detail shell reads the backdrop from cache only. On a miss it adds `&ct_backdrop=1` to the secondary URL, and the secondary fetches it and OOB-swaps `#ct-detail-backdrop-pending`. `tmdb.process_tv` and `tmdb.movie` seed `tmdb_backdrop_<type>_<id>` from the details response, so a fresh metadata fetch needs no separate `/tv/{id}` call.

## Tried and ruled out
- The prod 13.7 s cold `?fragment=secondary` does not reproduce locally: about 0.5–0.9 s base and the same after the change, with a warm TMDB connection. With no SSH route to `floppyserver` from this box, the cause stays unknown. Suspects are contention on prod (TMDB 5 req/s web bucket, concurrent shell/carousel/secondary/season requests, warmups after login).
- Local numbers lie in three ways on Windows: (1) no Redis means a 4 s connect timeout per limiter call, so run `fakeredis.TcpFakeServer` on 127.0.0.1:6379; (2) `REDIS_URL=redis://localhost` tries IPv6 first and adds about 2 s per new pool, so use `127.0.0.1`; (3) the first request imports the URLconf (about 2 s), so warm `reverse("home")` before timing.

## Before / after (local, cache cleared, warm TMDB connection)
- Show shell cold: 320–350 ms → 177–186 ms, because it no longer waits on the backdrop fetch. With a cold TMDB connection it was 760–1020 ms → 310–410 ms.
- Hero Mark button: visible at about 0.9 s on a tracked show, no longer waiting on the episode list or secondary fragment.

## Watch out
- The preview DB had one bogus Event (S1 content_number 92) for The Bear, so `next_episode_target` said "S1 E92". On prod the calendar fills these, but the hero now shows whatever Home's check would mark.
- Season pages still take the hero target from their own episode list, which arrives with the secondary fragment.
- `test_crud.CreateMedia.*` "fail" under a targeted label because they are `@tag("network")`. Add `--exclude-tag network` to targeted runs.
