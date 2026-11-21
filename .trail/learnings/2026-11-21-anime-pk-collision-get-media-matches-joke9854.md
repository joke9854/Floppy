---
title: "Anime pk collision: get_media matches an anime pk to its title"
author: Joke9854
date: 2026-11-21
branch: CineTrack-API
touches:
  - src/api/library_screen.py
  - src/api/tests/test_track_screen_api.py
  - src/app/models/manager.py
  - src/app/save_views.py
  - src/app/track_modal_views.py
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
---

## Decided
- BasicMedia.objects.get_media(user, "anime", pk) looked the pk up in the Anime table, then as a TV row filed as anime. Anime and TV pks overlap, so a TMDB show filed as anime (route type `anime`, posted media_type `anime` with identity_media_type tv) could open, SAVE TO or DELETE a MAL anime with the same pk. get_media now takes media_id and source (keyword-only) and matches the pk to that title in the anime branch; media_save, media_delete and build_standard_track_context pass them.
- The track builder catches ObjectDoesNotExist: the anime branch can raise TV.DoesNotExist, which model.DoesNotExist (Anime) did not catch (500).
## Tried and ruled out
- Falling back to the title's entry when an instance_id misses: a stale play id would then open a different play for editing. A miss still opens the empty Add form, as before.
## Watch out
- Also passed: update_media_score (the detail score chip adds ?media_id=&source= to its post, since its URL type is the route type and the response slot id uses it) and both history_modal views. media_status is safe (its form posts current_instance.item.media_type). The history-record delete paths use the record's own model type. Any new caller that can get an `anime` pk must pass media_id and source.
