"""Sync activity stamps and the bulk-write projection that feeds the change log.

The stamps are advisory ("did anything in this area move?"), so the properties
worth pinning are the ones a client relies on to skip work: the right write
bumps the right area, a deletion also bumps ``removed``, and a recompute that
changed nothing bumps nothing.
"""

import datetime
import logging
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from app.models import (
    TV,
    CollectionEntry,
    Episode,
    Item,
    MediaTypes,
    Movie,
    PlaybackProgress,
    Season,
    Sources,
    Status,
    SyncActivity,
    WatchState,
    WatchStateChange,
    WatchStateSequence,
)
from app.services.sync_activity import (
    activity_snapshot,
    batched_activity,
    touch_activity,
)
from app.services.watch_state import project_watch_state, suspend_projection
from lists.models import CustomList, CustomListItem

METADATA_PATH = "app.providers.services.get_media_metadata"


def setUpModule():
    """Silence log noise for this module only."""
    logging.disable(logging.DEBUG)


def tearDownModule():
    """Restore logging so other modules' assertLogs still see records."""
    logging.disable(logging.NOTSET)


def _stamps(user):
    return dict(
        SyncActivity.objects.filter(user=user).values_list("category", "changed_at"),
    )


class ActivityTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="owner")
        self.other = get_user_model().objects.create_user(username="other")
        self.movie_item = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Film",
        )

    def reset(self):
        SyncActivity.objects.all().delete()


class TouchActivityTests(ActivityTestCase):
    def test_first_use_inserts_and_later_use_updates_in_place(self):
        touch_activity(self.user, "library")
        first = _stamps(self.user)["library"]
        touch_activity(self.user, "library")

        self.assertEqual(SyncActivity.objects.filter(user=self.user).count(), 1)
        self.assertGreaterEqual(_stamps(self.user)["library"], first)

    def test_costs_one_update_per_category_once_the_row_exists(self):
        touch_activity(self.user, "library", "removed")
        with self.assertNumQueries(2):
            touch_activity(self.user, "library", "removed")

    def test_batch_writes_each_category_once_on_the_way_out(self):
        touch_activity(self.user, "library")
        with batched_activity():
            with self.assertNumQueries(0):
                for _ in range(5):
                    touch_activity(self.user, "library", "removed")
            with batched_activity():  # nested batches defer to the outer one
                touch_activity(self.user, "lists")
            with self.assertNumQueries(0):
                pass
            self.assertEqual(
                set(_stamps(self.user)),
                {"library"},
            )
        self.assertEqual(
            set(_stamps(self.user)),
            {"library", "removed", "lists"},
        )

    def test_is_scoped_to_the_user(self):
        touch_activity(self.user, "lists")
        self.assertEqual(_stamps(self.other), {})

    def test_unknown_category_is_refused(self):
        with self.assertRaises(ValueError):
            touch_activity(self.user, "nonsense")

    def test_snapshot_all_is_the_latest_stamp(self):
        early = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
        late = datetime.datetime(2026, 2, 1, tzinfo=datetime.UTC)
        SyncActivity.objects.create(user=self.user, category="lists", changed_at=late)
        SyncActivity.objects.create(
            user=self.user,
            category="library",
            changed_at=early,
        )
        snapshot = activity_snapshot(self.user)
        self.assertEqual(snapshot["all"], late)
        self.assertIsNone(snapshot["watched"])


class WatchedActivityTests(ActivityTestCase):
    def test_new_state_bumps_watched_without_emitting(self):
        Movie.objects.create(
            item=self.movie_item,
            user=self.user,
            status=Status.COMPLETED.value,
            end_date=timezone.now(),
        )
        self.assertIn("watched", _stamps(self.user))
        self.assertFalse(WatchStateChange.objects.exists())

    def test_new_state_bumps_watched_when_emitting(self):
        WatchStateSequence.objects.create(user=self.user, emit_changes=True)
        Movie.objects.create(
            item=self.movie_item,
            user=self.user,
            status=Status.COMPLETED.value,
            end_date=timezone.now(),
        )
        self.assertIn("watched", _stamps(self.user))
        self.assertTrue(WatchStateChange.objects.exists())

    def test_noop_projection_does_not_bump_watched(self):
        for emit in (False, True):
            with self.subTest(emit=emit):
                WatchStateSequence.objects.update_or_create(
                    user=self.user,
                    defaults={"emit_changes": emit},
                )
                Movie.objects.filter(user=self.user).delete()
                movie = Movie.objects.create(
                    item=self.movie_item,
                    user=self.user,
                    status=Status.COMPLETED.value,
                    end_date=timezone.now(),
                )
                self.assertIn("watched", _stamps(self.user))
                self.reset()

                project_watch_state(self.user, movie.item)

                self.assertNotIn("watched", _stamps(self.user))

    def test_changed_state_bumps_watched_again(self):
        movie = Movie.objects.create(
            item=self.movie_item,
            user=self.user,
            status=Status.COMPLETED.value,
            end_date=timezone.now(),
        )
        self.reset()
        movie.end_date = movie.end_date + datetime.timedelta(days=1)
        movie.save()
        self.assertIn("watched", _stamps(self.user))


class LibraryActivityTests(ActivityTestCase):
    def test_media_save_bumps_library_only(self):
        Movie.objects.create(
            item=self.movie_item,
            user=self.user,
            status=Status.PLANNING.value,
        )
        stamps = _stamps(self.user)
        self.assertIn("library", stamps)
        self.assertNotIn("removed", stamps)
        self.assertNotIn("playback", stamps)

    def test_media_delete_bumps_library_and_removed(self):
        movie = Movie.objects.create(
            item=self.movie_item,
            user=self.user,
            status=Status.PLANNING.value,
        )
        self.reset()
        movie.delete()
        self.assertTrue({"library", "removed"} <= set(_stamps(self.user)))

    def test_tv_and_season_saves_bump_library(self):
        tv_item = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Show",
        )
        season_item = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Show",
            season_number=1,
        )
        tv = TV.objects.create(
            item=tv_item,
            user=self.user,
            status=Status.PLANNING.value,
        )
        self.reset()
        tv.notes = "changed"
        tv.save()
        self.assertIn("library", _stamps(self.user))

        self.reset()
        Season.objects.create(
            item=season_item,
            user=self.user,
            related_tv=tv,
            status=Status.PLANNING.value,
        )
        self.assertIn("library", _stamps(self.user))

    def test_deleting_the_user_does_not_leave_activity_behind(self):
        # Collection entries cascade with the user without being projected into
        # watch state, which keeps this about the activity stamps alone.
        CollectionEntry.objects.create(user=self.user, item=self.movie_item)
        CustomList.objects.create(name="Mine", owner=self.user)
        user_id = self.user.pk
        self.user.delete()
        self.assertFalse(SyncActivity.objects.filter(user_id=user_id).exists())


class PlaybackActivityTests(ActivityTestCase):
    def test_progress_create_update_delete_bump_playback(self):
        progress = PlaybackProgress.objects.create(
            user=self.user,
            item=self.movie_item,
            position_seconds=10,
        )
        self.assertIn("playback", _stamps(self.user))

        self.reset()
        progress.position_seconds = 99
        progress.save()
        self.assertIn("playback", _stamps(self.user))

        self.reset()
        progress.delete()
        self.assertIn("playback", _stamps(self.user))

    def test_progress_write_does_not_touch_library(self):
        PlaybackProgress.objects.create(
            user=self.user,
            item=self.movie_item,
            position_seconds=10,
        )
        self.assertNotIn("library", _stamps(self.user))


class CollectionActivityTests(ActivityTestCase):
    def test_collection_save_and_delete(self):
        entry = CollectionEntry.objects.create(user=self.user, item=self.movie_item)
        stamps = _stamps(self.user)
        self.assertIn("collection", stamps)
        self.assertNotIn("removed", stamps)

        self.reset()
        entry.delete()
        self.assertTrue({"collection", "removed"} <= set(_stamps(self.user)))


class ListsActivityTests(ActivityTestCase):
    def test_list_and_item_changes_bump_lists(self):
        custom_list = CustomList.objects.create(name="Mine", owner=self.user)
        self.assertIn("lists", _stamps(self.user))

        self.reset()
        entry = CustomListItem.objects.create(
            custom_list=custom_list,
            item=self.movie_item,
        )
        stamps = _stamps(self.user)
        self.assertIn("lists", stamps)
        self.assertNotIn("removed", stamps)

        self.reset()
        entry.delete()
        self.assertTrue({"lists", "removed"} <= set(_stamps(self.user)))

        self.reset()
        custom_list.delete()
        self.assertTrue({"lists", "removed"} <= set(_stamps(self.user)))


class BulkCompletionProjectionTests(ActivityTestCase):
    """Completing a show bulk-creates episodes, which fire no save signals."""

    def _metadata(self):
        episodes = [{"episode_number": number} for number in (1, 2, 3)]
        return {
            "max_progress": 6,
            "related": {
                "seasons": [
                    {"season_number": 1, "image": "i1.jpg"},
                    {"season_number": 2, "image": "i2.jpg"},
                ],
            },
            "season/1": {"season_number": 1, "image": "i1.jpg", "episodes": episodes},
            "season/2": {"season_number": 2, "image": "i2.jpg", "episodes": episodes},
        }

    def _complete_show(self):
        tv_item = Item.objects.create(
            media_id="777",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Show",
        )
        with patch(METADATA_PATH, return_value=self._metadata()):
            return TV.objects.create(
                item=tv_item,
                user=self.user,
                status=Status.COMPLETED.value,
            )

    def test_completing_a_show_projects_every_created_episode(self):
        tv = self._complete_show()

        episodes = Episode.objects.filter(related_season__related_tv=tv)
        self.assertEqual(episodes.count(), 6)
        states = WatchState.objects.filter(
            user=self.user,
            item__media_type=MediaTypes.EPISODE.value,
            watched=True,
        )
        self.assertEqual(states.count(), 6)
        self.assertIn("watched", _stamps(self.user))
        self.assertIn("library", _stamps(self.user))

    def test_completing_a_show_emits_a_change_per_episode(self):
        WatchStateSequence.objects.create(user=self.user, emit_changes=True)
        self._complete_show()

        changes = WatchStateChange.objects.filter(
            user=self.user,
            item__media_type=MediaTypes.EPISODE.value,
        )
        self.assertEqual(changes.count(), 6)
        coordinates = {
            (change.item.season_number, change.item.episode_number)
            for change in changes.select_related("item")
        }
        self.assertEqual(
            coordinates,
            {(season, episode) for season in (1, 2) for episode in (1, 2, 3)},
        )

    def test_projection_is_skipped_while_suspended(self):
        with suspend_projection():
            self._complete_show()
        self.assertFalse(
            WatchState.objects.filter(
                item__media_type=MediaTypes.EPISODE.value,
            ).exists(),
        )
