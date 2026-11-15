"""A user's schedule lookups must never reach another user's tasks."""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from integrations.models import AudiobookshelfAccount
from integrations.task_filters import user_kwargs_regex

TASK = "Import from Audiobookshelf (Recurring)"


class ScheduleOwnershipTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(username="one", password="x", id=1)
        self.other = user_model.objects.create_user(
            username="eleven", password="x", id=11
        )
        crontab = CrontabSchedule.objects.create(minute="0", hour="*/2")
        self.tasks = {
            user.id: PeriodicTask.objects.create(
                name=f"{TASK} for {user.username}",
                task=TASK,
                crontab=crontab,
                kwargs=json.dumps({"user_id": user.id}),
            )
            for user in (self.user, self.other)
        }

    def test_regex_matches_only_the_exact_user(self):
        for kwargs, expected in (
            ('{"user_id": 1}', True),
            ('{"user_id": 1, "mode": "new"}', True),
            ("{'user_id':1}", True),
            ('{"user_id": 11}', False),
            ('{"user_id": 10, "x": 1}', False),
        ):
            with self.subTest(kwargs=kwargs):
                PeriodicTask.objects.filter(id=self.tasks[1].id).update(kwargs=kwargs)
                found = PeriodicTask.objects.filter(
                    id=self.tasks[1].id, kwargs__regex=user_kwargs_regex(1)
                ).exists()
                self.assertEqual(found, expected)

    def test_disconnect_leaves_other_users_schedule(self):
        AudiobookshelfAccount.objects.create(
            user=self.user, base_url="http://abs.test", api_token="x"
        )
        self.client.force_login(self.user)

        self.client.post(reverse("audiobookshelf_disconnect"))

        self.assertFalse(PeriodicTask.objects.filter(id=self.tasks[1].id).exists())
        self.assertTrue(PeriodicTask.objects.filter(id=self.tasks[11].id).exists())
