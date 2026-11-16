"""Per-user live events over Redis pub/sub (v2 P2-B).

Workers publish small JSON events on ``floppy:events:user:<id>``; the
``/api/v1/events/`` stream (``api.fork_views_events``) relays them to the
user's open connections as server-sent events. Redis is already required
(cache and broker), so this works on SQLite installs too.

Events carry ids and states only, never titles, credentials or response
bodies. Publishing never raises: a missed event costs a client one poll.
"""

import json
import logging
from functools import cache

from django.conf import settings

logger = logging.getLogger(__name__)

CHANNEL_PREFIX = "floppy:events:user:"

# Event types a client can rely on. Extend here and in the API docs together.
TASK_FINISHED = "task.finished"


def channel_for(user_id):
    """Return the pub/sub channel for one user's events."""
    return f"{CHANNEL_PREFIX}{int(user_id)}"


@cache
def _publisher():
    import redis

    return redis.Redis.from_url(
        settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2
    )


def publish(user_id, event_type, data):
    """Send one event to the user's open streams; never raises."""
    try:
        payload = json.dumps({"type": event_type, "data": data}, default=str)
        _publisher().publish(channel_for(user_id), payload)
    except Exception:  # a lost event must never fail the caller
        logger.debug("live event %s for user %s not published", event_type, user_id)


async def subscribe(user_id, *, poll_seconds):
    """Yield the user's events as dicts, or None after `poll_seconds` idle.

    The None lets the stream send a heartbeat and check for shutdown.
    """
    import redis.asyncio as aioredis

    client = aioredis.Redis.from_url(settings.REDIS_URL)
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    try:
        await pubsub.subscribe(channel_for(user_id))
        while True:
            message = await pubsub.get_message(timeout=poll_seconds)
            if message is None:
                yield None
                continue
            try:
                yield json.loads(message["data"])
            except (TypeError, ValueError):
                continue
    finally:
        await pubsub.aclose()
        await client.aclose()


def publish_task_finished(task_id, kwargs, state):
    """Celery task_postrun hook: tell the task's owner it finished."""
    user_id = (kwargs or {}).get("user_id")
    if not isinstance(user_id, int) or not task_id:
        return
    publish(user_id, TASK_FINISHED, {"task_id": task_id, "state": state})
