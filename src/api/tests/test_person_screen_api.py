"""The web person page API (v2 P4-C3) against the Django person page."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

import events.tasks
from app.models import (
    CreditRoleType,
    Item,
    ItemPersonCredit,
    MediaTypes,
    Movie,
    Person,
    PersonGender,
    Sources,
    Status,
)
from users.models import ThemeChoices

PERSON = {
    "person_id": "123",
    "source": Sources.TMDB.value,
    "name": "Jane Star",
    "image": "http://example.com/jane.jpg",
    "biography": "Test <b>bio</b>.",
    "known_for_department": "Acting",
    "gender": "female",
    "birth_date": "1990-01-01",
    "death_date": None,
    "place_of_birth": "Los Angeles",
    "filmography": [
        {
            "media_id": "501",
            "source": Sources.TMDB.value,
            "media_type": MediaTypes.MOVIE.value,
            "title": "Tracked Movie",
            "image": "http://example.com/tracked.jpg",
            "year": 2024,
            "credit_type": "cast",
            "role": "Lead",
            "department": "Acting",
        },
        {
            "media_id": "777",
            "source": Sources.TMDB.value,
            "media_type": MediaTypes.TV.value,
            "title": "Other Show",
            "image": "http://example.com/show.jpg",
            "year": 2021,
            "credit_type": "cast",
            "role": "Guest",
            "department": "Acting",
        },
    ],
}


@patch("app.providers.tmdb.person", return_value=PERSON)
class PersonScreenApiTests(TestCase):
    """GET /api/v1/details/person/{source}/{id}/ says what the page renders."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="person", password="x")
        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])
        self.client.force_login(self.user)
        person = Person.objects.create(
            source=Sources.TMDB.value,
            source_person_id="123",
            name="Jane Star",
            gender=PersonGender.FEMALE.value,
        )
        item = Item.objects.create(
            media_id="501",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Tracked Movie",
            image="http://example.com/tracked.jpg",
        )
        ItemPersonCredit.objects.create(
            item=item, person=person, role_type=CreditRoleType.CAST.value, role="Lead"
        )
        with patch("app.providers.services.get_media_metadata", return_value={"max_progress": 1}):
            Movie.objects.create(
                item=item,
                user=self.user,
                status=Status.COMPLETED.value,
                end_date=timezone.now(),
            )

    def test_person_page(self, _person):
        page = self.client.get(
            reverse(
                "person_detail",
                kwargs={"source": "tmdb", "person_id": "123", "name": "jane-star"},
            )
        ).content.decode()
        response = self.client.get(reverse("api_person_screen", args=["tmdb", "123"]))

        self.assertEqual(response.status_code, 200, response.content[:300])
        body = response.json()
        self.assertEqual(body["name"], "Jane Star")
        self.assertEqual(body["department"], "Acting")
        self.assertTrue(body["born"].startswith("Born "))
        self.assertEqual(body["place_of_birth"], "Los Angeles")
        self.assertEqual(body["biography"], "Test bio.")
        self.assertEqual(body["stats"]["titles"], 1)
        self.assertEqual(body["stats"]["movies"], 1)
        self.assertEqual([card["title"] for card in body["watched"]], ["Tracked Movie"])
        self.assertEqual(
            [credit["title"] for credit in body["filmography"]], ["Tracked Movie", "Other Show"]
        )
        self.assertTrue(body["filmography"][0]["watched"])
        self.assertFalse(body["filmography"][1]["watched"])
        self.assertEqual(body["history_url"], "/history?person_source=tmdb&person_id=123")
        for credit in body["filmography"]:
            self.assertIn(credit["title"], page)

    def test_sources_without_person_pages(self, _person):
        response = self.client.get(reverse("api_person_screen", args=["igdb", "1"]))

        self.assertEqual(response.status_code, 400)

    def test_integration_tokens_cannot_call_it(self, _person):
        from integrations.models import IntegrationToken

        _, raw = IntegrationToken.generate(user=self.user, name="person", scopes=["catalog:read"])
        response = Client().get(
            reverse("api_person_screen", args=["tmdb", "123"]), HTTP_X_API_KEY=raw
        )

        self.assertEqual(response.status_code, 403)
