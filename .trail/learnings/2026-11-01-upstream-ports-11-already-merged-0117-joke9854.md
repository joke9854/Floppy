---
title: UPSTREAM_PORTS 11 already merged; 0117 repair window misses Floppy
author: Joke9854
date: 2026-11-01
branch: CineTrack-API
cost: { minutes: 6, tokens: 93961 }
touches:
  - README.md
  - UPSTREAM_PORTS.md
---

## Decided
- UPSTREAM_PORTS #11 (Yamtrack 82a1f301) needed no new code. Merge 84b5ee71 (2026-05-27) already brought in the runtime fix in events/calendar/tv.py (reopen a completed show only for future season events), and 228f8181 also excludes unknown-unreleased sentinels. Ledger row: "Ported / Discarded (D4)".
- app/migrations/0117_fix_reopened_completed_tv_seasons.py came in with that same merge and is already in the shipped graph. Leave it there; never delete a shipped migration.
## Tried and ruled out
- Writing a new Floppy repair migration. dannyvfilms/Floppy#650 requires a read-only audit first.
## Watch out
- 0117 only repairs seasons created between 2026-04-06 and 2026-04-14 (Yamtrack's release window). Floppy shipped the unfixed 0109 from 2026-04-09 (merge 94747c46) to 2026-05-27, so anyone who upgraded after Apr 14 can still have bogus Planning seasons under In-progress shows.
- Before marking a ledger row Pending, check `git log -- <upstream file paths>` for an earlier merge from upstream.
