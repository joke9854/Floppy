---
title: "TV completion skips unaired episodes (UPSTREAM_PORTS #1)"
author: Joke9854
date: 2026-10-31
branch: CineTrack-API
cost: { minutes: 28, tokens: 103412 }
touches:
  - UPSTREAM_PORTS.md
  - src/app/models/tv.py
  - src/app/tests/models/test_season.py
  - src/app/tests/models/test_tv.py
  - src/integrations/tests/imports/test_mal.py
  - README.md
  - scripts/install/docker.sh
  - scripts/install/finish.sh
  - scripts/install/source_common.sh
  - src/app/context_processors.py
---

## Decided
- `app.models.tv.released_episode_numbers` is the one rule for "aired": dated episodes once the date passes; undated ones count as aired inside an aired run or when the whole season is undated (manual/TVDB), and the undated tail after the last aired episode is unaired. Year < 1900 and year 9999 are unknown dates.
- Completing a show/season never records watches for unaired episodes; the season stays IN_PROGRESS (PLANNING if nothing aired, from TV completion) and the show IN_PROGRESS.

## Tried and ruled out
- Upstream's "no air_date means unreleased": would leave manual and undated TVDB seasons uncompletable.
- An early `return` in Season.save's completion branch: skips fetch_releases and the time-left/media-list cache clears at the end of save.

## Watch out
- get_remaining_eps keeps Floppy's rewatch-pass filter (pass_started_on); upstream's version has none.
- dannyvfilms PR #683 (the adapted #51/#67 unknown-date work) is not in this branch's history even though later dannyvfilms PRs are.
- On Windows, `create_import_schedule` fails (naive 1900 datetime .astimezone); test fixtures opened without encoding fail on cp1252.
