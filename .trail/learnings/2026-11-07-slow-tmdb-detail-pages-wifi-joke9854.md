---
title: "Slow or never-loading v2 detail pages: season enrichment on the request, and the server's Wi-Fi"
author: Joke9854
date: 2026-11-07
branch: CineTrack-API
touches:
  - src/app/detail_related.py
  - src/app/providers/services.py
  - src/app/tasks.py
---

## Decided
- A show page's secondary fragment no longer fetches uncached TMDB seasons while the user waits. `detail_related._cached_tmdb_season_numbers` enriches the season cards from cached seasons only and queues `app.tasks.fetch_tmdb_seasons` for the rest. The queue runs on commit, deduplicated by a lock keyed on show + language + season list, and the task releases the lock. The enrichment only fills card titles, counts, dates and posters, which the show payload mostly carries already. TVDB shows still fetch inline.
- `api_request` uses `REQUEST_TIMEOUT_INTERACTIVE = (5, 20)` inside `interactive_request_scope()`. The read timeout bounds silence between bytes, not total time. Background calls keep `REQUEST_TIMEOUT` (120 s).

## Tried and ruled out
- TMDB and the code are not slow. With an empty cache, Game of Thrones' two season requests take 3.3 s from a desktop on the same LAN, and the container's own HTTP stack fetched the same response in 0.5 s.
- MTU / Docker networking: the container MTU is 1500 and the container was fast in the same minute that the host stalled.

## Watch out
- Prod (`floppyserver`) reaches the internet only over Wi-Fi (`wlp2s0`, netplan + systemd-networkd + wpa_supplicant, not NetworkManager); the wired NIC is down. Large responses sometimes stall for minutes: a 164 KB TMDB response once took 200 s, then 2 s on the next try. A secondary fragment then ran for 45–80 s, the browser gave up (`499`), and a reload rendered it again in parallel.
- The FRITZ!Box 5 GHz SSID ("... 5ghz") was on channel 116, a DFS channel that goes quiet on radar detection: the likely cause of the nightly 5 GHz outages.
- To profile a prod request, run it through `docker compose exec -T floppy sh -c 'cd /floppy && python manage.py shell'` with a Django test `Client` and `force_login`, and patch `urllib3.connectionpool.HTTPConnectionPool.urlopen` to time outbound calls. `urlopen` returns after the headers, so body download time shows up only in `resilient_request`.
