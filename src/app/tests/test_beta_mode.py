"""FLOPPY_BETA_MODE: a beta copy must never contact connected services."""

import json
import sqlite3
import sys
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from django_celery_beat.models import IntervalSchedule, PeriodicTask

from app import beta_mode
from app.middleware import BetaModeMiddleware
from config.celery import app as celery_app

NOTIFICATION_TASKS = {
    "Send release notifications",
    "Send daily digest",
    "Send premiere digest",
}
DELIVER = "Deliver watched state to a provider"


def _registry():
    """Return the Celery registry with every task module imported."""
    import events.tasks
    import integrations.tasks
    import lists.tasks

    celery_app.loader.import_default_modules()
    celery_app.finalize()
    return celery_app.tasks


def _url_names(patterns):
    names = set()
    for pattern in patterns:
        if isinstance(pattern, URLResolver):
            names |= _url_names(pattern.url_patterns)
        elif isinstance(pattern, URLPattern) and pattern.name:
            names.add(pattern.name)
    return names


class TaskCoverageTests(SimpleTestCase):
    """Every integration task has been classified as blocked or safe."""

    def test_sets_do_not_overlap(self):
        self.assertFalse(beta_mode.BLOCKED_TASK_NAMES & beta_mode.BETA_SAFE_TASK_NAMES)

    def test_every_listed_name_is_registered(self):
        registry = _registry()
        for name in beta_mode.BLOCKED_TASK_NAMES | beta_mode.BETA_SAFE_TASK_NAMES:
            self.assertIn(name, registry, name)

    def test_every_integration_task_is_classified(self):
        registry = _registry()
        for name, task in registry.items():
            module = task.__module__
            in_scope = (
                module.startswith("integrations.")
                or module == "lists.tasks"
                or name in NOTIFICATION_TASKS
            )
            if not in_scope:
                continue
            in_blocked = name in beta_mode.BLOCKED_TASK_NAMES
            in_safe = name in beta_mode.BETA_SAFE_TASK_NAMES
            self.assertTrue(
                in_blocked != in_safe,
                f"{name} must be in exactly one of the beta task sets",
            )


class TaskGuardTests(SimpleTestCase):
    """The base task skips blocked tasks only in beta mode."""

    def test_tasks_use_the_guard_base(self):
        self.assertIsInstance(_registry()[DELIVER], beta_mode.BetaGuardTask)

    @override_settings(FLOPPY_BETA_MODE=True)
    def test_blocked_task_does_not_run(self):
        task = _registry()[DELIVER]
        with patch("integrations.state.outbound.run_delivery") as run_delivery:
            direct = task(1)
            eager = task.apply(args=(1,)).get()
        run_delivery.assert_not_called()
        self.assertEqual(direct, beta_mode.BETA_SKIP_MESSAGE)
        self.assertEqual(eager, beta_mode.BETA_SKIP_MESSAGE)

    @override_settings(FLOPPY_BETA_MODE=False)
    def test_blocked_task_runs_when_flag_off(self):
        task = _registry()[DELIVER]
        with patch(
            "integrations.state.outbound.run_delivery",
            return_value="ran",
        ) as run_delivery:
            result = task.apply(args=(1,)).get()
        run_delivery.assert_called_once_with(1)
        self.assertEqual(result, "ran")

    @override_settings(FLOPPY_BETA_MODE=True)
    def test_unblocked_task_runs_in_beta_mode(self):
        task = _registry()["Sync Smart Lists For Items"]
        with patch("lists.tasks.User.objects.get") as get_user:
            get_user.side_effect = lists_user_missing()
            task.apply(args=(1, []))
        get_user.assert_called_once()

    @override_settings(FLOPPY_BETA_MODE=True)
    def test_skip_log_has_task_name_but_not_kwargs(self):
        task = _registry()[DELIVER]
        with self.assertLogs("app.beta_mode", level="INFO") as logs:
            task.apply(kwargs={"delivery_id": "secret-token"})
        output = "\n".join(logs.output)
        self.assertIn(DELIVER, output)
        self.assertNotIn("secret-token", output)


def lists_user_missing():
    from lists.tasks import User

    return User.DoesNotExist()


class BlockedUrlTests(SimpleTestCase):
    """Every blocked URL name exists in the URLconf."""

    def test_every_blocked_url_name_is_routed(self):
        routed = _url_names(get_resolver().url_patterns)
        missing = beta_mode.BLOCKED_URL_NAMES - routed
        self.assertFalse(missing, f"unrouted URL names: {sorted(missing)}")


class BetaModeMiddlewareTests(TestCase):
    """The middleware refuses service-contacting views only in beta mode."""

    def _run(self, path):
        get_response = MagicMock(return_value=MagicMock(status_code=200))
        response = BetaModeMiddleware(get_response)(RequestFactory().get(path))
        return response, get_response

    @override_settings(FLOPPY_BETA_MODE=True)
    def test_blocked_url_gets_403_and_view_is_not_called(self):
        response, get_response = self._run(reverse("plex_connect"))
        self.assertEqual(response.status_code, 403)
        self.assertIn(b"Beta server", response.content)
        get_response.assert_not_called()

    @override_settings(FLOPPY_BETA_MODE=True)
    def test_blocked_api_url_gets_json(self):
        response, get_response = self._run(reverse("api_user_notification_test"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(json.loads(response.content)["code"], "beta_server")
        get_response.assert_not_called()

    @override_settings(FLOPPY_BETA_MODE=True)
    def test_normal_page_is_unaffected(self):
        response, get_response = self._run("/")
        get_response.assert_called_once()
        self.assertEqual(response.status_code, 200)

    @override_settings(FLOPPY_BETA_MODE=False)
    def test_blocked_url_unaffected_when_flag_off(self):
        _response, get_response = self._run(reverse("plex_connect"))
        get_response.assert_called_once()

    @override_settings(FLOPPY_BETA_MODE=True)
    def test_full_stack_blocked_before_view(self):
        with patch("integrations.views.plex_connect") as view:
            response = self.client.get(reverse("plex_connect"))
        self.assertEqual(response.status_code, 403)
        view.assert_not_called()


class NotificationTests(SimpleTestCase):
    """Notifications are never sent from a beta copy."""

    @override_settings(FLOPPY_BETA_MODE=True)
    def test_send_user_notification_skips_apprise(self):
        from events import notifications

        with patch("apprise.Apprise") as apprise_class:
            result = notifications.send_user_notification(
                user=MagicMock(),
                urls=["json://localhost"],
                title="t",
                body="b",
            )
        apprise_class.assert_not_called()
        self.assertIsNone(result)


class BannerTests(TestCase):
    """The banner shows in beta mode and nowhere else."""

    BANNER = "connected services are paused"

    def _render(self):
        request = RequestFactory().get("/")
        request.user = MagicMock(is_authenticated=False)
        return render_to_string("base_public.html", request=request)

    @override_settings(FLOPPY_BETA_MODE=True)
    def test_banner_present_in_beta_mode(self):
        self.assertIn(self.BANNER, self._render())

    @override_settings(FLOPPY_BETA_MODE=False)
    def test_banner_absent_otherwise(self):
        self.assertNotIn(self.BANNER, self._render())


class PrepareBetaCopyTests(TestCase):
    """prepare_beta_copy disables per-user schedules and nothing else."""

    def setUp(self):
        schedule = IntervalSchedule.objects.create(
            every=1,
            period=IntervalSchedule.HOURS,
        )
        builtin_name = next(iter(settings.CELERY_BEAT_SCHEDULE))
        self.builtin = PeriodicTask.objects.create(
            name=builtin_name,
            task="Reload calendar",
            interval=schedule,
        )
        self.per_user = PeriodicTask.objects.create(
            name="Import from Trakt for someone",
            task="Import from Trakt",
            interval=schedule,
            kwargs='{"user_id": 1}',
        )

    @override_settings(FLOPPY_BETA_MODE=False)
    def test_refuses_when_flag_off(self):
        with self.assertRaises(CommandError):
            call_command("prepare_beta_copy", stdout=StringIO())
        self.per_user.refresh_from_db()
        self.assertTrue(self.per_user.enabled)

    @override_settings(FLOPPY_BETA_MODE=True)
    def test_disables_only_per_user_tasks_and_is_idempotent(self):
        out = StringIO()
        call_command("prepare_beta_copy", stdout=out)
        self.assertIn("Disabled 1", out.getvalue())
        self.per_user.refresh_from_db()
        self.builtin.refresh_from_db()
        self.assertFalse(self.per_user.enabled)
        self.assertTrue(self.builtin.enabled)

        again = StringIO()
        call_command("prepare_beta_copy", stdout=again)
        self.assertIn("Disabled 0", again.getvalue())
        self.assertEqual(PeriodicTask.objects.count(), 2)


class WriteDatabaseSnapshotTests(SimpleTestCase):
    """write_database_snapshot copies a SQLite database read-only."""

    def test_snapshot_is_a_readable_copy(self):
        if not sys.platform.startswith("linux"):
            self.skipTest("live snapshots use /proc/self/fd and need Linux")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.sqlite3"
            connection = sqlite3.connect(source)
            connection.execute("CREATE TABLE t (id INTEGER)")
            connection.execute("INSERT INTO t VALUES (7)")
            connection.commit()
            connection.close()
            dest = Path(tmp) / "snap"
            out = StringIO()
            with override_settings(
                FLOPPY_DB_PATH=source,
                USING_SQLITE_DATABASE=True,
            ):
                call_command("write_database_snapshot", dest=str(dest), stdout=out)
            written = Path(out.getvalue().strip())
            self.assertTrue(written.is_file())
            copy = sqlite3.connect(written)
            self.assertEqual(copy.execute("SELECT id FROM t").fetchone(), (7,))
            copy.close()

    def test_none_result_is_an_error(self):
        with (
            override_settings(USING_SQLITE_DATABASE=True),
            patch(
                "app.management.commands.write_database_snapshot."
                "create_live_database_snapshot",
                return_value=None,
            ),
            self.assertRaises(CommandError),
        ):
            call_command("write_database_snapshot", dest="x", stdout=StringIO())

    def test_postgres_failure_is_an_error(self):
        with (
            override_settings(USING_SQLITE_DATABASE=False),
            patch(
                "config.postgres_snapshot.create_postgres_snapshot", return_value=None
            ),
            self.assertRaisesMessage(CommandError, "pg_dump"),
        ):
            call_command("write_database_snapshot", dest="x", stdout=StringIO())
