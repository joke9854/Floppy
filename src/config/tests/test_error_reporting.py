from unittest.mock import patch

from django.test import SimpleTestCase

from config.error_reporting import init_error_reporting, scrub_breadcrumb, scrub_event


class ScrubEventTests(SimpleTestCase):
    def test_request_keeps_only_method_and_a_url_without_query(self):
        event = scrub_event({
            "request": {
                "method": "POST",
                "url": "https://user:pw@floppy.example/api/v1/scrobble/?token=abc",
                "headers": {"Authorization": "Bearer flp_secret", "X-Api-Key": "flp_secret"},
                "cookies": {"sessionid": "abc"},
                "data": {"password": "hunter2"},
                "query_string": "token=abc",
                "env": {"REMOTE_ADDR": "10.0.0.1"},
            },
        })

        self.assertEqual(
            event["request"],
            {"method": "POST", "url": "https://floppy.example/api/v1/scrobble/"},
        )

    def test_messages_and_exception_values_are_redacted(self):
        event = scrub_event({
            "message": "failed with api_key=flp_secret",
            "logentry": {"message": "%s", "formatted": "Authorization: Bearer flp_secret"},
            "exception": {"values": [{
                "value": "token=flp_secret rejected",
                "stacktrace": {"frames": [{"function": "f", "vars": {"token": "flp_secret"}}]},
            }]},
            "extra": {"payload": "flp_secret"},
        })

        self.assertNotIn("flp_secret", repr(event))
        self.assertEqual(event["exception"]["values"][0]["stacktrace"]["frames"], [{"function": "f"}])

    def test_breadcrumbs_keep_only_safe_fields(self):
        crumb = scrub_breadcrumb({
            "message": "password=hunter2",
            "data": {
                "url": "https://api.example/x?api_key=flp_secret",
                "method": "GET",
                "status_code": 200,
                "http.query": "api_key=flp_secret",
            },
        })

        self.assertNotIn("hunter2", crumb["message"])
        self.assertEqual(
            crumb["data"],
            {"url": "https://api.example/x", "method": "GET", "status_code": 200},
        )

    def test_event_breadcrumbs_are_scrubbed_too(self):
        event = scrub_event({"breadcrumbs": {"values": [{"message": "secret=flp_secret"}]}})

        self.assertNotIn("flp_secret", repr(event))


class InitErrorReportingTests(SimpleTestCase):
    def test_init_disables_pii_bodies_and_local_variables(self):
        with patch("config.error_reporting.sentry_sdk.init") as init:
            init_error_reporting("https://key@glitchtip.example/1", release="v1", environment="test")

        options = init.call_args.kwargs
        self.assertFalse(options["send_default_pii"])
        self.assertFalse(options["include_local_variables"])
        self.assertFalse(options["include_source_context"])
        self.assertEqual(options["max_request_body_size"], "never")
        self.assertIs(options["before_send"], scrub_event)
        self.assertIs(options["before_breadcrumb"], scrub_breadcrumb)
