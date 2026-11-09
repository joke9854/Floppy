from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from app.detail_related import enrich_detail_related_cards


class EnrichDetailRelatedCardsTests(SimpleTestCase):
    def test_skipped_sections_keep_provider_items_and_skip_the_lookup(self):
        season = {"media_id": "1", "source": "tmdb", "season_number": 1}
        recommendation = {"media_id": "2", "source": "tmdb", "media_type": "tv"}
        metadata = {
            "related": {"seasons": [season], "recommendations": [recommendation]}
        }
        enriched = [{"item": recommendation, "media": None}]

        with patch(
            "app.detail_related.helpers.enrich_items_with_user_data",
            return_value=enriched,
        ) as enrich:
            enrich_detail_related_cards(
                RequestFactory().get("/"),
                metadata,
                media_type="tv",
                tracking_user=None,
                skip_sections={"seasons"},
            )

        self.assertEqual(enrich.call_count, 1)
        self.assertEqual(enrich.call_args.kwargs["section_name"], "recommendations")
        self.assertEqual(metadata["related"]["seasons"], [season])
        self.assertEqual(metadata["related"]["recommendations"], enriched)
