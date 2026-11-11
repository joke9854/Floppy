from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app import home_sections
from app.cache_utils import clear_home_row_cache_for_user
from app.models import (
    TV,
    Anime,
    Episode,
    Item,
    MediaTypes,
    Movie,
    PlaybackProgress,
    Season,
    Sources,
    Status,
)
from events.models import Event
from integrations.models import IntegrationToken
from users.models import ThemeChoices

POSTER = "https://image.tmdb.org/t/p/w500/abc.jpg"


class HomeSectionsTests(TestCase):
    """v2 Home: Airing This Week, Recently Watched and the catch-up count."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "sections", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        self.now = timezone.now()

        self.season_item = self._season_item(1)
        self.season = Season.objects.create(
            item=self.season_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        # Eight aired episodes, four watched: four to catch up on.
        for number in range(1, 9):
            Event.objects.create(
                item=self.season_item,
                content_number=number,
                datetime=self.now - timedelta(days=30 - number),
            )
        for number in range(1, 5):
            Episode.objects.create(
                item=self._episode_item(number),
                related_season=self.season,
                end_date=self.now - timedelta(days=10 - number),
            )

    def _season_item(self, season_number):
        return Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            season_number=season_number,
            title="Friends",
            image=POSTER,
        )

    def _episode_item(self, number):
        return Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            season_number=1,
            episode_number=number,
            title="Friends",
            image=POSTER,
        )

    def _airing(self, sections):
        return [entry for column in sections["airing"] for entry in column]

    def test_catch_up_counts_aired_unwatched_episodes(self):
        sections = home_sections.build_home_sections(self.user)

        self.assertEqual(sections["catch_up"], 4)
        self.assertEqual(sections["catch_up_shows"], 1)

    def test_catch_up_skips_paused_shows_like_the_in_progress_row(self):
        self.season.related_tv.status = Status.PAUSED.value
        self.season.related_tv.save(update_fields=["status"])
        cache.clear()

        sections = home_sections.build_home_sections(self.user)

        self.assertEqual(sections["catch_up"], 0)
        self.assertEqual(sections["catch_up_shows"], 0)

    def test_airing_this_week_tags_premiere_and_finale(self):
        Event.objects.create(
            item=self.season_item,
            content_number=9,
            datetime=self.now + timedelta(days=1),
        )
        Event.objects.create(
            item=self.season_item,
            content_number=10,
            datetime=self.now + timedelta(days=2),
        )
        next_season = self._season_item(2)
        Season.objects.create(
            item=next_season,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        Event.objects.create(
            item=next_season,
            content_number=1,
            datetime=self.now + timedelta(days=3),
        )
        Event.objects.create(
            item=next_season,
            content_number=2,
            datetime=self.now + timedelta(days=30),
        )

        sections = home_sections.build_home_sections(self.user)

        tags = {
            (entry.event.item.season_number, entry.event.content_number): entry.tag
            for entry in self._airing(sections)
        }
        self.assertEqual(tags, {(1, 9): None, (1, 10): "finale", (2, 1): "premiere"})
        self.assertEqual(sections["airing_count"], 3)

    def test_recently_watched_lists_each_title_once_newest_first(self):
        movie_item = Item.objects.create(
            media_id="550",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Fight Club",
            image=POSTER,
        )
        Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.COMPLETED.value,
            end_date=self.now - timedelta(days=1),
        )

        sections = home_sections.build_home_sections(self.user)

        titles = [entry.item.title for entry in sections["recent"]]
        self.assertEqual(titles, ["Fight Club", "Friends"])

    def test_recently_watched_skips_a_planned_movie_with_a_date(self):
        movie_item = Item.objects.create(
            media_id="9999",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Hope",
            image=POSTER,
        )
        Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.PLANNING.value,
            end_date=self.now - timedelta(days=1),
        )

        sections = home_sections.build_home_sections(self.user)

        titles = [entry.item.title for entry in sections["recent"]]
        self.assertEqual(titles, ["Friends"])

    def _season_with_events(self, media_id, title, days_by_episode):
        item = Item.objects.create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            season_number=1,
            title=title,
            image=POSTER,
        )
        Season.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        for number, days in days_by_episode:
            Event.objects.create(
                item=item,
                content_number=number,
                datetime=self.now + timedelta(days=days),
            )
        return item

    def test_coming_soon_has_one_entry_per_show_soonest_first(self):
        self._season_with_events("2222", "Other Show", [(1, 20), (2, 21)])
        self._season_with_events("3333", "Far Show", [(1, 120)])
        movie_item = Item.objects.create(
            media_id="7777",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Dune",
            image=POSTER,
        )
        Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.PLANNING.value,
        )
        Event.objects.create(item=movie_item, datetime=self.now + timedelta(days=40))

        sections = home_sections.build_home_sections(self.user)

        self.assertEqual(
            [entry.event.item.title for entry in sections["coming_soon"]],
            ["Other Show", "Dune"],
        )
        self.assertEqual(
            [entry.event.content_number for entry in sections["coming_soon"]],
            [1, None],
        )

    def test_coming_soon_leaves_out_titles_that_air_this_week(self):
        Event.objects.create(
            item=self.season_item,
            content_number=9,
            datetime=self.now + timedelta(days=1),
        )
        Event.objects.create(
            item=self.season_item,
            content_number=10,
            datetime=self.now + timedelta(days=30),
        )

        sections = home_sections.build_home_sections(self.user)

        self.assertEqual(sections["coming_soon"], [])
        self.assertEqual(
            [entry.event.content_number for entry in self._airing(sections)],
            [9],
        )

    def test_home_renders_the_four_sections_in_order(self):
        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])
        self._season_with_events("2222", "Other Show", [(1, 20)])
        Event.objects.create(
            item=self.season_item,
            content_number=9,
            datetime=self.now + timedelta(days=1),
        )

        html = self.client.get(reverse("home")).content.decode()

        positions = [
            html.index(title)
            for title in (
                "In Progress",
                "Airing This Week",
                "Recently Watched",
                "Coming Soon",
            )
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("Nothing to show yet", html)

    def test_home_hides_sections_with_nothing_to_show(self):
        empty_user = get_user_model().objects.create_user(
            username="empty",
            password="12345",
        )
        self.client.force_login(empty_user)

        response = self.client.get(reverse("home"))

        html = response.content.decode()
        for heading in (
            "In Progress",
            "Airing This Week",
            "Recently Watched",
            "Coming Soon",
        ):
            self.assertNotIn(heading, html)
        self.assertContains(response, "Nothing to show yet")

    def test_home_screen_settings_page_is_gone(self):
        self.assertEqual(self.client.get("/settings/home-screen").status_code, 404)

    def test_sections_are_cached_and_cleared_with_the_home_rows(self):
        home_sections.build_home_sections(self.user)
        with patch.object(home_sections, "_catch_up") as count:
            home_sections.build_home_sections(self.user)
            count.assert_not_called()

            clear_home_row_cache_for_user(self.user.id)
            count.return_value = (0, 0)
            home_sections.build_home_sections(self.user)
            count.assert_called_once()

    def test_cinetrack_home_renders_the_sections(self):
        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])
        Event.objects.create(
            item=self.season_item,
            content_number=9,
            datetime=self.now + timedelta(days=1),
        )

        home = self.client.get(reverse("home")).content.decode()

        self.assertIn("4 episodes to catch up on", home)
        self.assertIn(f'href="{reverse("medialist", args=["tv"])}?status=In%20progress"', home)
        self.assertIn("1 airing this week", home)
        # The row opens the airing episode, not its season.
        self.assertIn('href="/details/tmdb/tv/1668/friends/season/1/episode/9"', home)
        self.assertIn(f'href="{reverse("calendar")}"', home)
        self.assertIn(f'href="{reverse("history")}"', home)


class InProgressFixtures(TestCase):
    """Shows, movies and playback for the In Progress row (no tests of its own)."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "progress", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        self.now = timezone.now()

    def _show(
        self,
        media_id,
        status,
        *,
        released=0,
        watched=(),
        part_watched=None,
        part_position=600,
        part_duration=None,
        model=TV,
        media_type=MediaTypes.TV.value,
    ):
        """Track a show: season 1 with `released` aired episodes, some watched."""
        show_item = Item.objects.create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=media_type,
            title=f"Show {media_id}",
            image=POSTER,
        )
        model.objects.create(item=show_item, user=self.user, status=status)
        season_item = Item.objects.create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            season_number=1,
            title=f"Show {media_id}",
            image=POSTER,
        )
        season = Season.objects.create(
            item=season_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        for number in range(1, released + 1):
            Event.objects.create(
                item=season_item,
                content_number=number,
                datetime=self.now - timedelta(days=released + 1 - number),
            )
        for number in watched:
            Episode.objects.create(
                item=self._episode_item(media_id, number),
                related_season=season,
                end_date=self.now - timedelta(days=2),
            )
        if part_watched is not None:
            PlaybackProgress.objects.create(
                user=self.user,
                item=self._episode_item(media_id, part_watched),
                position_seconds=part_position,
                duration_seconds=part_duration,
                completed=False,
            )
        return show_item

    def _episode_item(self, media_id, number):
        item, _ = Item.objects.get_or_create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            season_number=1,
            episode_number=number,
            defaults={"title": f"Show {media_id}", "image": POSTER},
        )
        return item

    def _movie(self, media_id, status, *, position=None, duration=None):
        item = Item.objects.create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title=f"Movie {media_id}",
            image=POSTER,
        )
        Movie.objects.create(item=item, user=self.user, status=status)
        if position is not None:
            PlaybackProgress.objects.create(
                user=self.user,
                item=item,
                position_seconds=position,
                duration_seconds=duration,
                completed=False,
            )
        return item

    def _in_progress_titles(self):
        sections = home_sections.build_home_sections(self.user)
        return [entry.item.title for entry in sections["in_progress"]]

    def _dated_show(self, media_id, status, *, released, watched):
        """A show whose aired episodes carry release dates, with no season Events."""
        show_item = Item.objects.create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title=f"Show {media_id}",
            image=POSTER,
        )
        TV.objects.create(item=show_item, user=self.user, status=status)
        season_item = Item.objects.create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            season_number=1,
            title=f"Show {media_id}",
            image=POSTER,
        )
        season = Season.objects.create(
            item=season_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        for number in range(1, released + 1):
            Item.objects.create(
                media_id=media_id,
                source=Sources.TMDB.value,
                media_type=MediaTypes.EPISODE.value,
                season_number=1,
                episode_number=number,
                title=f"Show {media_id}",
                release_datetime=self.now - timedelta(days=released + 1 - number),
            )
        for number in watched:
            Episode.objects.create(
                item=self._episode_item(media_id, number),
                related_season=season,
                end_date=self.now - timedelta(days=2),
            )

    def _flat_anime(self, media_id, status, *, progress, released):
        """A flat anime tracked by count, with `released` aired episodes as Events."""
        item = Item.objects.create(
            media_id=media_id,
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title=f"Anime {media_id}",
            image=POSTER,
        )
        Anime.objects.create(item=item, user=self.user, status=status, progress=progress)
        for number in range(1, released + 1):
            Event.objects.create(
                item=item,
                content_number=number,
                datetime=self.now - timedelta(days=released + 1 - number),
            )
        return item


class InProgressRulesTests(InProgressFixtures):
    """The In Progress row shows only real progress, latest activity first."""

    def test_show_with_watched_and_unwatched_released_episodes_is_in(self):
        self._show("1", Status.IN_PROGRESS.value, released=3, watched=[1])

        self.assertEqual(self._in_progress_titles(), ["Show 1"])

    def test_show_with_nothing_watched_is_out(self):
        self._show("1", Status.IN_PROGRESS.value, released=3)

        self.assertEqual(self._in_progress_titles(), [])

    def test_show_fully_watched_is_out(self):
        self._show("1", Status.IN_PROGRESS.value, released=3, watched=[1, 2, 3])

        self.assertEqual(self._in_progress_titles(), [])

    def test_completed_show_with_a_newer_released_episode_is_in(self):
        self._show("1", Status.COMPLETED.value, released=4, watched=[1, 2, 3])

        self.assertEqual(self._in_progress_titles(), ["Show 1"])

    def test_completed_show_with_nothing_newer_is_out(self):
        self._show("1", Status.COMPLETED.value, released=3, watched=[1, 2, 3])

        self.assertEqual(self._in_progress_titles(), [])

    def test_planning_show_qualifies_only_through_a_part_watched_episode(self):
        self._show("1", Status.PLANNING.value, released=3, watched=[1], part_watched=2)
        self._show("2", Status.PLANNING.value, released=3, watched=[1])

        self.assertEqual(self._in_progress_titles(), ["Show 1"])

    def test_part_watched_episode_puts_an_in_progress_show_in(self):
        self._show("1", Status.IN_PROGRESS.value, released=1, part_watched=1)

        self.assertEqual(self._in_progress_titles(), ["Show 1"])

    def test_paused_and_dropped_shows_are_out(self):
        self._show("1", Status.PAUSED.value, released=3, watched=[1])
        self._show("2", Status.DROPPED.value, released=3, watched=[1])

        self.assertEqual(self._in_progress_titles(), [])

    def test_show_with_release_dated_episodes_and_no_events_qualifies(self):
        self._dated_show("3", Status.IN_PROGRESS.value, released=4, watched=[1])

        self.assertEqual(self._in_progress_titles(), ["Show 3"])

    def test_flat_anime_with_some_released_episodes_watched_is_in(self):
        self._flat_anime("7", Status.IN_PROGRESS.value, progress=5, released=12)

        self.assertEqual(self._in_progress_titles(), ["Anime 7"])

    def test_flat_anime_with_nothing_watched_is_out(self):
        self._flat_anime("7", Status.IN_PROGRESS.value, progress=0, released=12)

        self.assertEqual(self._in_progress_titles(), [])

    def test_flat_anime_fully_watched_is_out(self):
        self._flat_anime("7", Status.IN_PROGRESS.value, progress=12, released=12)

        self.assertEqual(self._in_progress_titles(), [])

    def test_paused_and_planning_flat_anime_are_out(self):
        self._flat_anime("7", Status.PAUSED.value, progress=5, released=12)
        self._flat_anime("8", Status.PLANNING.value, progress=5, released=12)

        self.assertEqual(self._in_progress_titles(), [])

    def test_movie_with_a_resume_position_is_in(self):
        self._movie("550", Status.IN_PROGRESS.value, position=1800, duration=7200)

        self.assertEqual(self._in_progress_titles(), ["Movie 550"])

    def test_movie_resume_entry_carries_the_position_percentage(self):
        self._movie("550", Status.IN_PROGRESS.value, position=1800, duration=7200)

        entry = home_sections.build_home_sections(self.user)["in_progress"][0]

        self.assertEqual(entry.resume_percent, 25)

    def test_movie_at_one_minute_is_out(self):
        self._movie("550", Status.IN_PROGRESS.value, position=60, duration=7200)

        self.assertEqual(self._in_progress_titles(), [])

    def test_movie_at_ninety_six_percent_is_out(self):
        self._movie("550", Status.IN_PROGRESS.value, position=6912, duration=7200)

        self.assertEqual(self._in_progress_titles(), [])

    def test_movie_without_a_runtime_is_in_from_two_minutes(self):
        self._movie("550", Status.IN_PROGRESS.value, position=120)

        self.assertEqual(self._in_progress_titles(), ["Movie 550"])

    def test_movie_in_progress_without_a_position_is_out(self):
        self._movie("550", Status.IN_PROGRESS.value)

        self.assertEqual(self._in_progress_titles(), [])

    def test_paused_and_dropped_movies_are_out(self):
        # A Completed movie with a resume position is a rewatch; see the builder tests.
        for media_id, status in (
            ("1", Status.PAUSED.value),
            ("2", Status.DROPPED.value),
        ):
            self._movie(media_id, status, position=1800, duration=7200)

        self.assertEqual(self._in_progress_titles(), [])

    def test_rows_are_ordered_by_latest_activity(self):
        movie = self._movie(
            "550", Status.IN_PROGRESS.value, position=1800, duration=7200
        )
        PlaybackProgress.objects.filter(item=movie).update(
            updated_at=self.now - timedelta(hours=1)
        )
        self._show("1", Status.IN_PROGRESS.value, released=3, watched=[1])

        self.assertEqual(self._in_progress_titles(), ["Movie 550", "Show 1"])

    def test_row_is_capped_at_twenty(self):
        for number in range(25):
            self._movie(
                str(number), Status.IN_PROGRESS.value, position=1800, duration=7200
            )

        self.assertEqual(len(self._in_progress_titles()), 20)

    def test_api_home_in_progress_group_matches_the_web_section(self):
        self._movie("550", Status.IN_PROGRESS.value, position=1800, duration=7200)
        self._show("1", Status.IN_PROGRESS.value, released=3, watched=[1])
        self._show("2", Status.IN_PROGRESS.value, released=3)

        _, raw_token = IntegrationToken.generate(
            user=self.user, name="home api test", scopes=["*"]
        )
        payload = self.client.get(
            reverse("api_home"), HTTP_X_API_KEY=raw_token
        ).json()
        group = next(
            group for group in payload["groups"] if group["media_type"] == "in_progress"
        )

        self.assertEqual(
            [item["item"]["title"] for item in group["rows"][0]["items"]],
            self._in_progress_titles(),
        )


class InProgressCardTests(InProgressFixtures):
    """The In Progress row: one card format, and the All/Movies/Shows pills."""

    def _home(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_movies_and_shows_share_the_progress_card(self):
        self._movie("550", Status.IN_PROGRESS.value, position=1800, duration=7200)
        self._show("1", Status.IN_PROGRESS.value, released=3, watched=[1])

        html = self._home()

        self.assertEqual(html.count('class="ct-progress-card"'), 2)
        self.assertIn('data-kind="movie"', html)
        self.assertIn('data-kind="show"', html)
        self.assertIn("--ct-progress: 25%", html)

    def test_pills_show_when_the_row_has_both_kinds(self):
        self._movie("550", Status.IN_PROGRESS.value, position=1800, duration=7200)
        self._show("1", Status.IN_PROGRESS.value, released=3, watched=[1])

        html = self._home()

        self.assertIn('aria-label="Filter In Progress by type"', html)
        self.assertEqual(html.count('class="ct-status-tab"'), 3)
        self.assertIn(":aria-pressed=\"kind === 'movie' ? 'true' : 'false'\"", html)

    def test_home_renders_the_row_as_a_refreshable_region(self):
        self._show("1", Status.IN_PROGRESS.value, released=3, watched=[1])

        html = self._home()

        self.assertIn(
            f'hx-get="{reverse("home_in_progress_fragment")}"',
            html,
        )
        self.assertIn('hx-trigger="refreshHomeInProgress from:body"', html)

    def test_fragment_renders_only_the_row(self):
        self._movie("550", Status.IN_PROGRESS.value, position=1800, duration=7200)

        response = self.client.get(reverse("home_in_progress_fragment"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("ct-progress-title", response.content.decode())
        self.assertNotContains(response, "<html")

    def test_fragment_is_empty_once_nothing_is_in_progress(self):
        response = self.client.get(reverse("home_in_progress_fragment"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("ct-progress-title", response.content.decode())

    def test_fragment_requires_sign_in(self):
        self.client.logout()

        response = self.client.get(reverse("home_in_progress_fragment"))

        self.assertEqual(response.status_code, 302)

    def test_pills_are_hidden_when_the_row_has_one_kind(self):
        self._show("1", Status.IN_PROGRESS.value, released=3, watched=[1])

        html = self._home()

        self.assertIn('data-kind="show"', html)
        self.assertNotIn('aria-label="Filter In Progress by type"', html)


    def test_cards_show_time_left_and_the_rewatch_badge(self):
        self._movie("620", Status.COMPLETED.value, position=1800, duration=7200)
        self._show(
            "7",
            Status.IN_PROGRESS.value,
            released=4,
            watched=[1],
            part_watched=2,
            part_position=1200,
            part_duration=2700,
        )

        html = self._home()

        self.assertIn("1h 30m left", html)  # the rewatch movie: 5400 s
        self.assertIn("25m left", html)  # the part-watched episode: 1500 s
        self.assertEqual(html.count(">Rewatch</span>"), 1)
        self.assertIn("S1 E2", html)

    def test_cards_without_a_known_runtime_show_no_time_left(self):
        self._movie("621", Status.IN_PROGRESS.value, position=1800)

        html = self._home()

        self.assertIn("Movie 621", html)
        self.assertNotIn(" left</span>", html)
        self.assertNotIn(">Rewatch</span>", html)


class RecentlyWatchedRelativeDayTests(TestCase):
    """Board A1: Recently Watched says Today, Yesterday or 2 Nov."""

    def test_relative_day_labels(self):
        from app.templatetags.app_tags import ct_relative_day

        today = timezone.localdate()
        self.assertEqual(ct_relative_day(today), "Today")
        self.assertEqual(ct_relative_day(today - timedelta(days=1)), "Yesterday")
        same_year = today.replace(month=1, day=2) if today.month > 1 else today.replace(day=1)
        if (today - same_year).days > 1:
            self.assertEqual(ct_relative_day(same_year), f"{same_year.day} {same_year:%b}")
        last_year = today.replace(year=today.year - 1, day=2)
        self.assertEqual(ct_relative_day(last_year), f"2 {last_year:%b} {last_year.year}")
        self.assertEqual(ct_relative_day("S1 E3"), "S1 E3")


class ContinueWatchingBuilderTests(InProgressFixtures):
    """The builder's targets, times and rewatch flags, on top of the row's rules."""

    def _entry(self, title):
        return next(
            entry
            for entry in home_sections.build_continue_watching(self.user)
            if entry.item.title == title
        )

    def test_part_watched_episode_is_the_target_with_time_left(self):
        self._show(
            "1",
            Status.IN_PROGRESS.value,
            released=4,
            watched=[1],
            part_watched=2,
            part_position=1200,
            part_duration=2700,
        )

        entry = self._entry("Show 1")

        self.assertEqual(entry.kind, "show")
        self.assertEqual(entry.target_season_number, 1)
        self.assertEqual(entry.target_episode_number, 2)
        self.assertEqual(entry.remaining_seconds, 1500)
        self.assertEqual(entry.resume_percent, 44)
        self.assertEqual((entry.watched_count, entry.released_count), (1, 4))
        self.assertFalse(entry.is_rewatch)

    def test_most_recently_updated_part_watched_episode_wins(self):
        self._show("1", Status.IN_PROGRESS.value, released=4, watched=[1], part_watched=2)
        third = self._episode_item("1", 3)
        PlaybackProgress.objects.create(
            user=self.user, item=third, position_seconds=300, completed=False
        )
        PlaybackProgress.objects.filter(item=third).update(
            updated_at=self.now + timedelta(hours=1)
        )

        self.assertEqual(self._entry("Show 1").target_episode_number, 3)

    def test_next_episode_target_has_no_time_left(self):
        self._show("2", Status.IN_PROGRESS.value, released=4, watched=[1])

        entry = self._entry("Show 2")

        self.assertEqual(entry.target_episode_number, 2)
        self.assertIsNone(entry.remaining_seconds)
        self.assertIsNone(entry.resume_percent)

    def test_part_watched_episode_without_a_duration_has_no_time_left(self):
        self._show("4", Status.IN_PROGRESS.value, released=4, watched=[1], part_watched=2)

        entry = self._entry("Show 4")

        self.assertEqual(entry.target_episode_number, 2)
        self.assertIsNone(entry.remaining_seconds)

    def test_target_title_comes_from_the_local_episode_item(self):
        self._show("5", Status.IN_PROGRESS.value, released=4, watched=[1])
        episode = self._episode_item("5", 2)
        episode.title = "The Second One"
        episode.save(update_fields=["title"])

        entry = self._entry("Show 5")

        self.assertEqual(entry.target_title, "The Second One")
        self.assertEqual(entry.target_item_id, episode.id)

    def test_open_rewatch_pass_is_a_rewatch_targeting_its_next_episode(self):
        self._show("3", Status.COMPLETED.value, released=3, watched=[1, 2, 3])
        season = Season.objects.get(user=self.user, item__media_id="3")
        season.start_rewatch(started_at=self.now, max_progress=3)

        entry = self._entry("Show 3")

        self.assertTrue(entry.is_rewatch)
        self.assertEqual(entry.target_episode_number, 1)

    def test_completed_show_without_a_rewatch_stays_out(self):
        self._show("6", Status.COMPLETED.value, released=3, watched=[1, 2, 3])

        self.assertNotIn("Show 6", self._in_progress_titles())

    def test_completed_movie_with_a_resume_position_is_a_rewatch(self):
        self._movie("600", Status.COMPLETED.value, position=2000, duration=7200)

        entry = self._entry("Movie 600")

        self.assertTrue(entry.is_rewatch)
        self.assertEqual(entry.remaining_seconds, 5200)
        self.assertEqual(entry.resume_percent, 28)

    def test_position_older_than_a_watch_of_that_episode_is_ignored(self):
        self._show(
            "7", Status.IN_PROGRESS.value, released=4, watched=[1, 2], part_watched=2
        )
        PlaybackProgress.objects.filter(item__media_id="7").update(
            updated_at=self.now - timedelta(days=3)
        )

        entry = self._entry("Show 7")

        self.assertEqual(entry.target_episode_number, 3)
        self.assertIsNone(entry.remaining_seconds)

    def test_position_older_than_the_last_finished_play_is_not_a_rewatch(self):
        item = self._movie("601", Status.COMPLETED.value, position=2000, duration=7200)
        Movie.objects.filter(item=item).update(end_date=self.now)
        PlaybackProgress.objects.filter(item=item).update(
            updated_at=self.now - timedelta(days=1)
        )

        self.assertNotIn("Movie 601", self._in_progress_titles())

    def test_card_links_to_the_episode_it_resumes(self):
        self._show(
            "8", Status.PLANNING.value, released=4, part_watched=3, part_duration=2700
        )

        response = self.client.get(reverse("home"))

        self.assertContains(
            response,
            reverse(
                "episode_details",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_id": "8",
                    "title": "show-8",
                    "season_number": 1,
                    "episode_number": 3,
                },
            ),
        )

    def test_completed_movie_without_a_resume_position_stays_out(self):
        self._movie("601", Status.COMPLETED.value)

        self.assertNotIn("Movie 601", self._in_progress_titles())

    def test_in_progress_movie_is_not_a_rewatch(self):
        self._movie("602", Status.IN_PROGRESS.value, position=1800, duration=7200)

        entry = self._entry("Movie 602")

        self.assertFalse(entry.is_rewatch)
        self.assertEqual(entry.remaining_seconds, 5400)

    def test_movie_time_left_is_unknown_without_a_runtime(self):
        self._movie("603", Status.IN_PROGRESS.value, position=1800)

        self.assertIsNone(self._entry("Movie 603").remaining_seconds)

    def test_check_target_names_the_episode_the_label_shows(self):
        self._show("1", Status.IN_PROGRESS.value, released=4, watched=[1], part_watched=2)

        check = self._entry("Show 1").check_target()

        self.assertEqual(check["media_id"], "1")
        self.assertEqual(check["season_number"], 1)
        self.assertEqual(check["episode_number"], 2)
        self.assertEqual(check["episode_title"], "Show 1")


class ContinueWatchingCacheTests(InProgressFixtures):
    """A resume write or delete clears the Home sections on the next render."""

    def test_playback_writes_clear_the_cached_home_sections(self):
        movie = self._movie("610", Status.IN_PROGRESS.value)
        self.assertNotIn("Movie 610", self._in_progress_titles())

        progress = PlaybackProgress.objects.create(
            user=self.user, item=movie, position_seconds=1800, duration_seconds=7200
        )
        self.assertIn("Movie 610", self._in_progress_titles())

        progress.delete()
        self.assertNotIn("Movie 610", self._in_progress_titles())
