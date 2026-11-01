import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.providers import services
from events.models import UNKNOWN_RELEASED_DATETIME, Event

from .other import process_other

logger = logging.getLogger(__name__)


def process_anime_bulk(items, events_bulk):
    """Process multiple anime items and add events to the event list.

    Returns the items that were successfully checked. Items that AniList did not
    cover fall through to process_other, and are only reported as checked when
    that call succeeds, so a provider failure there is retried rather than being
    suppressed by the staleness window.
    """
    if not items:
        return []

    checked = []
    anime_data = get_anime_schedule_bulk([item.media_id for item in items])

    for item in items:
        episodes = anime_data.get(item.media_id)

        if episodes is not None:
            for episode in episodes:
                if episode["airingAt"] is None:
                    episode_datetime = UNKNOWN_RELEASED_DATETIME
                else:
                    episode_datetime = datetime.fromtimestamp(
                        episode["airingAt"],
                        tz=ZoneInfo("UTC"),
                    )
                events_bulk.append(
                    Event(
                        item=item,
                        content_number=episode["episode"],
                        datetime=episode_datetime,
                    ),
                )
            checked.append(item)
        else:
            logger.info(
                "Anime: %s (%s), not proccesed by AniList",
                item.title,
                item.media_id,
            )
            if process_other(item, events_bulk):
                checked.append(item)

    return checked


def _collect_airing_schedule_pages(query, url, media_ids, page):
    """Collect every nested airing-schedule page for one outer media page."""
    media_by_id = {}
    airing_page = 1

    while True:
        variables = {
            "ids": media_ids,
            "page": page,
            "airingPage": airing_page,
        }
        response = services.api_request(
            "ANILIST",
            "POST",
            url,
            params={"query": query, "variables": variables},
        )

        page_data = response["data"]["Page"]
        has_next_airing_page = False

        for media in page_data["media"]:
            mal_id = str(media["idMal"])
            schedule_by_episode = media_by_id.setdefault(mal_id, {})
            schedule = media["airingSchedule"]

            for node in schedule.get("nodes", []):
                episode_number = node.get("episode")
                if episode_number is None:
                    continue

                existing = schedule_by_episode.get(episode_number)
                if existing is None or (
                    existing.get("airingAt") is None
                    and node.get("airingAt") is not None
                ):
                    schedule_by_episode[episode_number] = {
                        "episode": episode_number,
                        "airingAt": node.get("airingAt"),
                    }

            has_next_airing_page = has_next_airing_page or schedule.get(
                "pageInfo",
                {},
            ).get("hasNextPage", False)

        if not has_next_airing_page:
            return media_by_id, page_data["pageInfo"]["hasNextPage"]

        airing_page += 1


def get_anime_schedule_bulk(media_ids):
    """Get the airing schedule for multiple anime items from AniList API."""
    all_data = {}
    page = 1
    url = "https://graphql.anilist.co"
    query = """
    query ($ids: [Int], $page: Int, $airingPage: Int) {
      Page(page: $page) {
        pageInfo {
          hasNextPage
        }
        media(idMal_in: $ids, type: ANIME) {
          idMal
          airingSchedule(page: $airingPage) {
            pageInfo {
              hasNextPage
            }
            nodes {
              episode
              airingAt
            }
          }
        }
      }
    }
    """

    while True:
        media_by_id, has_next_page = _collect_airing_schedule_pages(
            query,
            url,
            media_ids,
            page,
        )

        for mal_id, schedule_by_episode in media_by_id.items():
            all_data[mal_id] = sorted(
                schedule_by_episode.values(),
                key=lambda episode: episode["episode"],
            )

        if not has_next_page:
            break
        page += 1

    return all_data
