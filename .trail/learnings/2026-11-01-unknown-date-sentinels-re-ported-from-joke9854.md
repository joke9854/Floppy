---
title: "Unknown-date sentinels re-ported from orphaned PR #683"
author: Joke9854
date: 2026-11-01
branch: CineTrack-API
cost: { minutes: 19, tokens: 97704 }
touches:
  - UPSTREAM_PORTS.md
  - src/app/media_list_filters.py
  - src/app/models/manager.py
  - src/app/templatetags/app_tags.py
  - src/events/admin.py
  - src/events/calendar/anime.py
  - src/events/calendar/other.py
  - src/events/calendar/selectors.py
  - src/events/calendar/tv.py
  - src/events/models.py
---

## Decided
- dannyvfilms PR #683 was merged into PR #673's branch after #673 had merged, so it never reached latest; it was re-ported here, scoped.
- Two explicit sentinels in events.models: UNKNOWN_RELEASED_DATETIME (0001-01-02 11:59:59.999999 UTC) and UNKNOWN_UNRELEASED_DATETIME (9999-12-30 same time); both survive any UTC offset. Legacy datetime.min means unreleased for SEASON events and released for everything else.
- Readers exclude UNKNOWN_UNRELEASED_QUERY (exact values, no year lookup) instead of `datetime__year__lt=1900`, so released-but-undated content (MangaUpdates chapters, AniList) counts.
- TV: undated gaps inherit the nearest later aired date on the event only; inferred and sentinel dates never become Item.release_datetime.

## Tried and ruled out
- Porting #683's season max_progress denominator rework: a separate behaviour change, left out.
- A data migration for legacy rows: use the read-only `audit_calendar_sentinels` command first.

## Watch out
- Home-screen code passes SimpleNamespace events into manager._annotate_next_event; read event properties with getattr there.
- `datetime__year=1` lookups convert bounds through the DB timezone and can overflow at negative offsets; match exact sentinel values.
