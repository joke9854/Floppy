"""App pull connections, episode coordinates in the feed, and sync activities.

An app (CineTrack, Nuvio) has no provider adapter, so before app connections
existed the change log was never switched on for API-only users and the feed was
always empty. These tests pin the registration contract and the properties that
make it safe: pull-only, idempotent, owner-scoped, and never a delivery target.
"""

import datetime
from http import HTTPStatus as HTTP  # noqa: N814

from django.test import override_settings
from django.utils import timezone

from app.models import (
    TV,
    Episode,
    Item,
    MediaTypes,
    Movie,
    Season,
    Sources,
    Status,
    SyncActivity,
    WatchState,
    WatchStateSequence,
)
from app.services.watch_state import effective_state
from integrations.models import (
    CAPABILITY_WATCHED_PUSH_PLAYED,
    IntegrationToken,
    OutboundStateDelivery,
    SyncBinding,
    SyncBindingStatus,
    SyncClientKind,
    SyncDirection,
)

from .base import FloppyApiTestCase

CONNECTIONS = "/api/v1/sync/connections/"
CHANGES = "/api/v1/sync/changes/"
ACTIVITIES = "/api/v1/sync/activities/"


def _register(client, headers, **overrides):
    body = {"client": "cinetrack", "instance_key": "install-1"}
    body.update(overrides)
    return client.post(CONNECTIONS, body, format="json", **headers)


def _watch_episode(user, *, season_number=2, episode_number=5):
    """Record one watched episode through the ordinary ORM write path."""
    tv_item = Item.objects.create(
        media_id="1399",
        source=Sources.TMDB.value,
        media_type=MediaTypes.TV.value,
        title="Show",
    )
    season_item = Item.objects.create(
        media_id="1399",
        source=Sources.TMDB.value,
        media_type=MediaTypes.SEASON.value,
        title="Show",
        season_number=season_number,
    )
    episode_item = Item.objects.create(
        media_id="1399",
        source=Sources.TMDB.value,
        media_type=MediaTypes.EPISODE.value,
        title="Show",
        season_number=season_number,
        episode_number=episode_number,
    )
    tv = TV.objects.create(item=tv_item, user=user, status=Status.IN_PROGRESS.value)
    season = Season.objects.create(
        item=season_item,
        user=user,
        related_tv=tv,
        status=Status.IN_PROGRESS.value,
    )
    return Episode.objects.create(
        related_season=season,
        item=episode_item,
        end_date=datetime.datetime(2026, 7, 1, 20, tzinfo=datetime.UTC),
    )


class AppConnectionTests(FloppyApiTestCase):
    def test_registering_is_idempotent_and_turns_emitting_on(self):
        """The same client and install id resolve to one active connection."""
        first = _register(self.client, self.auth_headers, label="Pixel")
        self.assertEqual(first.status_code, HTTP.CREATED)
        self.assertTrue(
            WatchStateSequence.objects.get(user=self.user1).emit_changes,
        )

        second = _register(self.client, self.auth_headers)
        self.assertEqual(second.status_code, HTTP.OK)
        self.assertEqual(second.data["connection"], first.data["connection"])
        self.assertEqual(second.data["client"], "cinetrack")
        self.assertEqual(second.data["instance_key"], "install-1")
        self.assertEqual(
            SyncBinding.objects.filter(
                user=self.user1,
                client_kind=SyncClientKind.APP.value,
            ).count(),
            1,
        )
        self.assertEqual(first.data["newest_sequence"], 0)

    def test_binding_is_pull_only(self):
        """Approved for Floppy-to-client with no capability, nothing to push."""
        _register(self.client, self.auth_headers)
        binding = SyncBinding.objects.get(user=self.user1)
        self.assertEqual(binding.status, SyncBindingStatus.ACTIVE.value)
        self.assertEqual(
            binding.approved_directions,
            [SyncDirection.OUTBOUND.value],
        )
        self.assertEqual(binding.approved_capabilities, [])

    def test_different_install_is_a_different_connection(self):
        first = _register(self.client, self.auth_headers)
        second = _register(self.client, self.auth_headers, instance_key="install-2")
        self.assertEqual(second.status_code, HTTP.CREATED)
        self.assertNotEqual(first.data["connection"], second.data["connection"])

    def test_invalid_body_is_rejected(self):
        for body in (
            {"client": "Bad Slug!", "instance_key": "x"},
            {"client": "cinetrack", "instance_key": ""},
            {"client": "cinetrack"},
            {"client": "x" * 33, "instance_key": "x"},
        ):
            response = self.client.post(
                CONNECTIONS,
                body,
                format="json",
                **self.auth_headers,
            )
            self.assertEqual(response.status_code, HTTP.BAD_REQUEST, body)

    def test_registered_connection_sees_episode_with_coordinates(self):
        """A watched episode reaches the feed with its season and episode."""
        registered = _register(self.client, self.auth_headers)
        _watch_episode(self.user1, season_number=2, episode_number=5)

        response = self.client.get(
            CHANGES,
            {"cursor": registered.data["newest_sequence"]},
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.OK)
        results = response.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["media_type"], MediaTypes.EPISODE.value)
        self.assertEqual(results[0]["season_number"], 2)
        self.assertEqual(results[0]["episode_number"], 5)
        self.assertTrue(results[0]["watched"])

    def test_movie_change_has_null_coordinates(self):
        _register(self.client, self.auth_headers)
        item = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Film",
        )
        Movie.objects.create(
            item=item,
            user=self.user1,
            status=Status.COMPLETED.value,
            end_date=timezone.now(),
        )
        results = self.client.get(CHANGES, **self.auth_headers).data["results"]
        self.assertEqual(len(results), 1)
        self.assertIsNone(results[0]["season_number"])
        self.assertIsNone(results[0]["episode_number"])

    def test_newest_sequence_is_where_a_fresh_snapshot_resumes(self):
        _register(self.client, self.auth_headers)
        _watch_episode(self.user1)
        again = _register(self.client, self.auth_headers)
        self.assertGreater(again.data["newest_sequence"], 0)
        feed = self.client.get(
            CHANGES,
            {"cursor": again.data["newest_sequence"]},
            **self.auth_headers,
        )
        self.assertEqual(feed.data["results"], [])

    def test_delete_deactivates_and_turns_emitting_off(self):
        registered = _register(self.client, self.auth_headers)
        url = f"{CONNECTIONS}{registered.data['connection']}/"

        response = self.client.delete(url, **self.auth_headers)
        self.assertEqual(response.status_code, HTTP.NO_CONTENT)

        binding = SyncBinding.objects.get(user=self.user1)
        self.assertEqual(binding.status, SyncBindingStatus.DISABLED.value)
        self.assertFalse(
            WatchStateSequence.objects.get(user=self.user1).emit_changes,
        )

    def test_delete_keeps_emitting_while_another_connection_is_operational(self):
        first = _register(self.client, self.auth_headers)
        _register(self.client, self.auth_headers, instance_key="install-2")
        self.client.delete(
            f"{CONNECTIONS}{first.data['connection']}/",
            **self.auth_headers,
        )
        self.assertTrue(
            WatchStateSequence.objects.get(user=self.user1).emit_changes,
        )

    def test_reregistering_after_delete_reactivates(self):
        first = _register(self.client, self.auth_headers)
        self.client.delete(
            f"{CONNECTIONS}{first.data['connection']}/",
            **self.auth_headers,
        )
        again = _register(self.client, self.auth_headers)
        self.assertEqual(again.status_code, HTTP.CREATED)
        self.assertEqual(again.data["connection"], first.data["connection"])
        self.assertTrue(
            WatchStateSequence.objects.get(user=self.user1).emit_changes,
        )

    def test_another_users_connection_is_not_found(self):
        registered = _register(self.client, self.auth_headers)
        response = self.client.delete(
            f"{CONNECTIONS}{registered.data['connection']}/",
            **self.auth_headers2,
        )
        self.assertEqual(response.status_code, HTTP.NOT_FOUND)
        self.assertEqual(
            SyncBinding.objects.get(user=self.user1).status,
            SyncBindingStatus.ACTIVE.value,
        )

    def test_unknown_connection_is_not_found(self):
        response = self.client.delete(f"{CONNECTIONS}nope/", **self.auth_headers)
        self.assertEqual(response.status_code, HTTP.NOT_FOUND)

    def test_provider_binding_cannot_be_deleted_here(self):
        binding = SyncBinding.objects.create(
            user=self.user1,
            client_kind=SyncClientKind.JELLYFIN.value,
            origin_key="jellyfin_abc",
            status=SyncBindingStatus.ACTIVE.value,
        )
        response = self.client.delete(
            f"{CONNECTIONS}{binding.origin_key}/",
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.NOT_FOUND)

    def test_listing_includes_app_connections(self):
        registered = _register(self.client, self.auth_headers, label="Pixel")
        response = self.client.get(CONNECTIONS, **self.auth_headers)
        self.assertEqual(response.status_code, HTTP.OK)
        rows = [
            row
            for row in response.data["results"]
            if row["client_kind"] == SyncClientKind.APP.value
        ]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["origin_key"], registered.data["connection"])
        self.assertEqual(rows[0]["label"], "Pixel")
        self.assertEqual(rows[0]["pending_deliveries"], 0)

    def test_no_outbound_delivery_is_queued_for_an_app_binding(self):
        """An app is pulled from, never pushed to."""
        _register(self.client, self.auth_headers)
        _watch_episode(self.user1)
        self.assertTrue(WatchState.objects.filter(user=self.user1).exists())
        self.assertEqual(OutboundStateDelivery.objects.count(), 0)

    def test_no_delivery_even_if_push_were_approved(self):
        """The missing adapter, not the approval, is what keeps it pull-only."""
        _register(self.client, self.auth_headers)
        binding = SyncBinding.objects.get(user=self.user1)
        binding.approved_capabilities = [CAPABILITY_WATCHED_PUSH_PLAYED]
        binding.save(update_fields=["approved_capabilities"])

        _watch_episode(self.user1)
        self.assertEqual(OutboundStateDelivery.objects.count(), 0)

    def test_state_is_projected_for_registered_user(self):
        _register(self.client, self.auth_headers)
        episode = _watch_episode(self.user1)
        self.assertTrue(effective_state(self.user1, episode.item).watched)


class AppConnectionScopeTests(FloppyApiTestCase):
    def _headers(self, *scopes):
        _token, raw = IntegrationToken.generate(
            user=self.user1,
            name="scoped",
            scopes=list(scopes),
        )
        return {"HTTP_X_API_KEY": raw}

    def test_token_without_sync_read_cannot_register_a_connection(self):
        response = _register(self.client, self._headers("watchlist:read"))
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)
        self.assertFalse(SyncBinding.objects.exists())

    def test_sync_read_token_can_register_and_delete(self):
        # The tracking preset (sync:read) must be enough for an app to pull the
        # feed; sync:write stays reserved for resolving conflicts.
        headers = self._headers("sync:read")
        registered = _register(self.client, headers)
        self.assertEqual(registered.status_code, HTTP.CREATED)
        response = self.client.delete(
            f"{CONNECTIONS}{registered.data['connection']}/",
            **headers,
        )
        self.assertEqual(response.status_code, HTTP.NO_CONTENT)

    def test_token_without_sync_read_cannot_delete_a_connection(self):
        registered = _register(self.client, self.auth_headers)
        response = self.client.delete(
            f"{CONNECTIONS}{registered.data['connection']}/",
            **self._headers("watchlist:read"),
        )
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)

    def test_activities_need_sync_read(self):
        denied = self.client.get(ACTIVITIES, **self._headers("watchlist:read"))
        self.assertEqual(denied.status_code, HTTP.FORBIDDEN)
        allowed = self.client.get(ACTIVITIES, **self._headers("sync:read"))
        self.assertEqual(allowed.status_code, HTTP.OK)


class SyncActivitiesEndpointTests(FloppyApiTestCase):
    def setUp(self):
        """Drop the stamps the shared fixtures wrote, so tests start clean."""
        super().setUp()
        SyncActivity.objects.all().delete()

    def test_empty_account_reports_nulls(self):
        response = self.client.get(ACTIVITIES, **self.auth_headers)
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(
            set(response.data),
            {
                "all",
                "watched",
                "playback",
                "library",
                "lists",
                "collection",
                "removed",
            },
        )
        self.assertTrue(all(value is None for value in response.data.values()))

    def test_values_are_utc_iso_strings_and_all_is_the_max(self):
        earlier = datetime.datetime(2026, 7, 1, 10, tzinfo=datetime.UTC)
        later = datetime.datetime(2026, 7, 2, 11, 30, tzinfo=datetime.UTC)
        SyncActivity.objects.create(
            user=self.user1,
            category="library",
            changed_at=earlier,
        )
        SyncActivity.objects.create(
            user=self.user1,
            category="lists",
            changed_at=later,
        )
        SyncActivity.objects.create(
            user=self.user2,
            category="removed",
            changed_at=later + datetime.timedelta(days=5),
        )

        data = self.client.get(ACTIVITIES, **self.auth_headers).data
        self.assertEqual(data["library"], "2026-07-01T10:00:00Z")
        self.assertEqual(data["lists"], "2026-07-02T11:30:00Z")
        self.assertEqual(data["all"], data["lists"])
        self.assertIsNone(data["removed"])

    @override_settings(TIME_ZONE="Europe/Rome")
    def test_values_stay_utc_whatever_the_server_zone(self):
        SyncActivity.objects.create(
            user=self.user1,
            category="watched",
            changed_at=datetime.datetime(2026, 7, 1, 10, tzinfo=datetime.UTC),
        )
        data = self.client.get(ACTIVITIES, **self.auth_headers).data
        self.assertEqual(data["watched"], "2026-07-01T10:00:00Z")


class InfoExtensionsTests(FloppyApiTestCase):
    def test_info_lists_the_new_flags(self):
        response = self.client.get("/api/v1/info/")
        self.assertEqual(response.status_code, HTTP.OK)
        extensions = response.data["api_extensions"]
        for flag in (
            "sync_app_connections_v1",
            "sync_changes_coordinates_v1",
            "sync_activities_v1",
        ):
            self.assertIs(extensions[flag], True)
        self.assertIs(extensions["cinetrack_episode_events_v1"], True)
