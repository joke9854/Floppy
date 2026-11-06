from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from app.discover.schemas import CandidateItem, RowResult
from app.models import Item, MediaTypes, Movie, Sources, Status
from app.templatetags.app_tags import (
    ct_discover_hero,
    ct_library_in_progress,
    ct_library_subtitle,
    ct_library_types,
)
from users.models import ThemeChoices

BACKDROP = "https://image.tmdb.org/t/p/w1280/back.jpg"


def _candidate(media_id, media_type="movie", image="https://image.tmdb.org/t/p/w500/p.jpg"):
    return CandidateItem(
        media_type=media_type,
        source=Sources.TMDB.value,
        media_id=media_id,
        title=f"Title {media_id}",
        image=image,
        release_date="2024-05-01",
    )


def _row(key, *items):
    return RowResult(key=key, title=key.title(), mission="", why="Why.", source="local", items=list(items))


class _CineTrackUserMixin:
    def setUp(self):
        cache.clear()
        self.credentials = {"username": "library", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    def _use_cinetrack(self):
        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])


class CineTrackLibraryTypesTests(TestCase):
    """W4/E1: TV Seasons folds into TV Shows while both are enabled."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="types", password="12345")

    def test_seasons_fold_into_tv(self):
        library = ct_library_types(self.user)

        types = [entry["media_type"] for entry in library["types"]]
        self.assertTrue(library["tv_seasons"])
        self.assertIn(MediaTypes.TV.value, types)
        self.assertNotIn(MediaTypes.SEASON.value, types)

    def test_seasons_keep_their_entry_without_tv(self):
        self.user.tv_enabled = False
        self.user.save(update_fields=["tv_enabled"])

        library = ct_library_types(self.user)

        self.assertFalse(library["tv_seasons"])
        self.assertIn(MediaTypes.SEASON.value, [entry["media_type"] for entry in library["types"]])


class CineTrackLibraryCardTests(TestCase):
    """v2 A3: the card subtitle names the next episode, else the status."""

    def _media(self, media_type, status, **attrs):
        item = SimpleNamespace(media_type=media_type)
        return SimpleNamespace(item=item, status=status, aggregated_status=None, **attrs)

    def test_in_progress_show_names_the_next_episode(self):
        season = SimpleNamespace(item=SimpleNamespace(season_number=2))
        media = self._media(
            MediaTypes.TV.value,
            Status.IN_PROGRESS.value,
            next_episode_target=lambda: (season, 5),
        )

        self.assertEqual(ct_library_subtitle(media), "S2 E5 next")

    def test_in_progress_season_names_the_next_episode(self):
        media = self._media(
            MediaTypes.SEASON.value,
            Status.IN_PROGRESS.value,
            next_episode_number=lambda: 7,
        )

        self.assertEqual(ct_library_subtitle(media), "E7 next")

    def test_caught_up_and_other_statuses_show_the_status(self):
        caught_up = self._media(
            MediaTypes.TV.value,
            Status.IN_PROGRESS.value,
            next_episode_target=lambda: None,
        )
        planned = self._media(MediaTypes.MOVIE.value, Status.PLANNING.value)

        self.assertEqual(ct_library_subtitle(caught_up), "In Progress")
        self.assertEqual(ct_library_subtitle(planned), "Planning")
        self.assertEqual(ct_library_subtitle(self._media(MediaTypes.MOVIE.value, "")), "")

    def test_in_progress_count_is_per_type_and_user(self):
        user = get_user_model().objects.create_user(username="counts", password="12345")
        other = get_user_model().objects.create_user(username="other", password="12345")
        for index, (owner, status) in enumerate(
            [(user, Status.IN_PROGRESS), (user, Status.COMPLETED), (other, Status.IN_PROGRESS)],
        ):
            item = Item.objects.create(
                media_id=str(index),
                source=Sources.TMDB.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"Movie {index}",
                image="https://image.tmdb.org/t/p/w500/p.jpg",
            )
            Movie.objects.create(item=item, user=owner, status=status.value)

        self.assertEqual(ct_library_in_progress(user, MediaTypes.MOVIE.value), 1)
        self.assertEqual(ct_library_in_progress(user, "nope"), 0)


class CineTrackDiscoverHeroTests(TestCase):
    """W4: one hero slide per row, skipping placeholders and repeats."""

    def setUp(self):
        cache.clear()

    def test_one_slide_per_row_with_cached_backdrop(self):
        cache.set("tmdb_backdrop_movie_1", BACKDROP)
        rows = [
            _row("trending", _candidate("1"), _candidate("2")),
            _row("picks", _candidate("1"), _candidate("3", image=None), _candidate("4")),
        ]

        with patch(
            "app.backdrops.resolve_backdrop",
            side_effect=lambda candidate: cache.get(f"tmdb_backdrop_movie_{candidate.media_id}"),
        ):
            slides = ct_discover_hero(rows)

        self.assertEqual([slide["candidate"].media_id for slide in slides], ["1", "4"])
        self.assertEqual([slide["backdrop"] for slide in slides], [BACKDROP, None])
        self.assertEqual(slides[1]["row_title"], "Picks")

    def test_limit_caps_the_slides(self):
        rows = [_row(f"r{i}", _candidate(str(i))) for i in range(8)]

        with patch("app.backdrops.resolve_backdrop", return_value=None):
            self.assertEqual(len(ct_discover_hero(rows, limit=5)), 5)


@override_settings(IMAGE_CACHE_ENABLED=False)
class CineTrackMediaListTests(_CineTrackUserMixin, TestCase):
    """W4: the Library header replaces the title row for the CineTrack theme only."""

    def test_cinetrack_renders_type_switch_and_status_tabs(self):
        self._use_cinetrack()

        response = self.client.get(reverse("medialist", args=[MediaTypes.SEASON.value]))

        self.assertContains(response, 'class="ct-library-head"')
        self.assertContains(response, 'class="ct-type-switch"')
        # Seasons is TV's second view: TV is the current type, Seasons the current view.
        content = response.content.decode()
        tv_url, season_url = reverse("medialist", args=["tv"]), reverse("medialist", args=["season"])
        self.assertRegex(content, rf'href="{tv_url}"\s+class="ct-type-pill"\s+aria-current="page"')
        self.assertNotRegex(content, rf'href="{season_url}"\s+class="ct-type-pill"')
        self.assertContains(response, 'class="ct-segment"')
        self.assertContains(response, 'data-status="completed"')
        self.assertContains(response, 'hx-include="#filter-form"')
        self.assertContains(response, 'hx-swap="innerHTML transition:true"')
        self.assertContains(response, "<span data-result-count>", count=1)
        self.assertContains(response, 'id="filter-form"', count=1)
        self.assertContains(response, 'id="loading-indicator"', count=1)

    def test_classic_theme_keeps_the_title_row(self):
        response = self.client.get(reverse("medialist", args=[MediaTypes.TV.value]))

        self.assertNotContains(response, "ct-library-head")
        self.assertNotContains(response, "ct-status-tab")
        self.assertContains(response, '<h1 class="text-3xl font-bold">')
        self.assertNotContains(response, "ct-toolbar")
        self.assertNotContains(response, "ct-library-grid")
        self.assertContains(response, "media-settings-menu-desktop")

    def test_cinetrack_v2_toolbar_and_grid(self):
        """A3: status segment and toolbar share a row; the grid is restyled."""
        self._use_cinetrack()
        item = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie",
            image="https://image.tmdb.org/t/p/w500/p.jpg",
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)

        response = self.client.get(reverse("medialist", args=[MediaTypes.MOVIE.value]))

        self.assertContains(response, 'class="ct-library-bar"')
        self.assertContains(response, "ct-toolbar")
        self.assertContains(response, 'data-ct-filter="status"')
        self.assertContains(response, "layoutHref('table')")
        self.assertContains(response, "ct-settings-menu")
        self.assertContains(response, "media-grid ct-library-grid")
        self.assertContains(response, 'data-status="completed"', count=2)
        self.assertContains(response, '<p class="ct-library-sub">Completed</p>', html=True)

    def test_cinetrack_status_tabs_request_their_own_status(self):
        """Each tab sends its status in hx-vals, not the form's stale one.

        htmx reads #filter-form in the same click, before Alpine re-renders
        its hidden status inputs, so the form alone carries the previous tab.
        """
        self._use_cinetrack()

        response = self.client.get(reverse("medialist", args=[MediaTypes.MOVIE.value]))

        self.assertContains(response, """hx-vals='{"status": "all"}'""", count=1)
        for status in (Status.IN_PROGRESS.value, Status.COMPLETED.value):
            self.assertContains(response, f"""hx-vals='{{"status": "{status}"}}'""", count=1)


@override_settings(IMAGE_CACHE_ENABLED=False)
@patch("app.middleware.discover_tab_cache.maybe_schedule_user_warmup", return_value=0)
@patch("app.views.discover_tab_cache.get_tab_status", return_value={"is_refreshing": False})
@patch("app.views.discover_tab_cache.warm_sibling_tabs")
@patch("app.views.discover_tab_cache.get_tab_rows")
class CineTrackDiscoverTests(_CineTrackUserMixin, TestCase):
    """W4/E4/E5: hero and rails, no subtitle line, rows load on scroll."""

    def setUp(self):
        super().setUp()
        cache.set("tmdb_backdrop_movie_1", BACKDROP)
        self.rows = [_row("trending_right_now", _candidate("1"), _candidate("2"))]

    def test_cinetrack_page_has_hero_rails_and_scroll_loading(self, get_tab_rows, *_):
        get_tab_rows.return_value = self.rows
        self._use_cinetrack()

        response = self.client.get(reverse("discover"))

        self.assertContains(response, 'class="ct-discover-head"')
        self.assertContains(response, 'x-data="ctHero(1)"')
        self.assertContains(response, "https://image.tmdb.org/t/p/w1280/back.jpg 1280w")
        self.assertContains(response, "ct-rail-row")
        self.assertContains(response, 'data-horizontal-drag="true"')
        self.assertContains(response, "data-discover-load-more")
        self.assertContains(response, 'id="discover-rows"', count=1)
        self.assertContains(response, 'id="discover-row-trending_right_now"', count=1)
        self.assertNotContains(response, "UNDER CONSTRUCTION")
        self.assertNotContains(response, "Show More Rows")

    def test_cinetrack_v2_follows_the_mockup(self, get_tab_rows, *_):
        """v2 A8/A19: hero actions, card meta line; features the board lacks are hidden."""
        get_tab_rows.return_value = self.rows
        self._use_cinetrack()

        response = self.client.get(reverse("discover"))

        self.assertContains(response, "Add to Planned")
        self.assertContains(response, '"action":"planning"')
        self.assertContains(response, 'class="ct-discover-hero__secondary">Details<')
        self.assertContains(response, "ct-palette-open")
        self.assertContains(response, 'class="ct-library-sub">Movie · 2024</p>', count=2)
        self.assertContains(response, 'class="ct-row-title">Trending_Right_Now<')
        self.assertNotContains(response, "Refresh recommendations")
        self.assertNotContains(response, "switchMedia('hidden')")
        self.assertNotContains(response, "Why.")
        self.assertNotContains(response, "ct-discover-hero__poster")

    def test_classic_page_is_unchanged(self, get_tab_rows, *_):
        get_tab_rows.return_value = self.rows

        response = self.client.get(reverse("discover"))

        self.assertContains(response, "UNDER CONSTRUCTION")
        self.assertContains(response, "Show More Rows")
        self.assertNotContains(response, "ct-discover")
        self.assertNotContains(response, "ctHero(")
        self.assertNotContains(response, "data-horizontal-drag")


@override_settings(IMAGE_CACHE_ENABLED=False)
@patch("app.providers.services.search")
class CineTrackSearchTests(_CineTrackUserMixin, TestCase):
    """W4: the restyled Search header keeps the source and layout links."""

    def _get(self, mock_search):
        mock_search.return_value = {"page": 1, "total_results": 0, "total_pages": 1, "results": []}
        return self.client.get(reverse("search") + "?media_type=movie&q=test")

    def test_cinetrack_header(self, mock_search):
        """v2 A9: the page's own field and the type segment; no layout toggle."""
        self._use_cinetrack()

        response = self._get(mock_search)

        self.assertContains(response, 'class="ct-search-head"')
        self.assertContains(response, 'class="ct-search-field"')
        self.assertRegex(response.content.decode(), r'name="q"\s+value="test"')
        self.assertRegex(
            response.content.decode(),
            r'media_type=movie"\s+aria-current="page">Movies<',
        )
        self.assertNotContains(response, "Results for")
        self.assertNotContains(response, "layout=list")

    def test_cinetrack_result_rows(self, mock_search):
        """Tracked results show their status; the others an Add button."""
        self._use_cinetrack()
        item = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Tracked Movie",
            image="http://example.com/a.jpg",
        )
        Movie.objects.create(item=item, user=self.user, status=Status.PLANNING.value)
        mock_search.return_value = {
            "page": 1,
            "total_results": 2,
            "total_pages": 1,
            "results": [
                {
                    "media_id": media_id,
                    "title": title,
                    "media_type": MediaTypes.MOVIE.value,
                    "source": Sources.TMDB.value,
                    "image": "http://example.com/a.jpg",
                }
                for media_id, title in (("1", "Tracked Movie"), ("2", "New Movie"))
            ],
        }

        response = self.client.get(reverse("search") + "?media_type=movie&q=movie")

        self.assertContains(response, 'class="ct-search-row"', count=3)
        self.assertContains(response, "In Your Library")
        self.assertContains(response, "More Results")
        self.assertContains(response, 'data-status="planning"', count=2)
        self.assertContains(response, 'class="ct-search-row__add"', count=1)
        self.assertNotContains(response, "Online Results")

    def test_classic_header(self, mock_search):
        response = self._get(mock_search)

        self.assertNotContains(response, "ct-search-head")
        self.assertContains(response, "Search Results")
