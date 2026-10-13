"""Let sync write entries name an item by external ids.

Every sync write endpoint takes ``source`` + ``media_id``. An entry may instead
carry ``ids`` (``tmdb``, ``imdb``, ``tvdb``), as Trakt and Simkl clients do.
Those entries are resolved to a TMDB item before the endpoint parses the
request. An entry whose ids match nothing still gets its own result, in its
own position, so a batch never fails because of one unknown id.
"""

import logging

from app.models import Sources

from .fork_views_playback import resolve_show_tmdb_id

logger = logging.getLogger(__name__)

_ID_KEYS = ("tmdb", "imdb", "tvdb")

# Result ``type`` per request section.
_SECTION_TYPES = {"movies": "movie", "shows": "show", "episodes": "episode"}


def _wants_ids(raw):
    """Return whether ``raw`` names its item by ``ids`` only."""
    if not isinstance(raw, dict) or raw.get("source") or raw.get("media_id"):
        return False
    ids = raw.get("ids")
    return isinstance(ids, dict) and any(
        isinstance(ids.get(key), (str, int))
        and not isinstance(ids.get(key), bool)
        and str(ids.get(key)).strip()
        for key in _ID_KEYS
    )


def _clean_ids(ids):
    return {
        key: str(ids[key]).strip()
        for key in _ID_KEYS
        if isinstance(ids.get(key), (str, int))
        and not isinstance(ids.get(key), bool)
        and str(ids[key]).strip()
    }


def _lookup(section, ids):
    """Return ``(tmdb_id, None)`` or ``(None, reason)`` for one entry's ids."""
    # Movies resolve to a movie; shows and episodes to their show (an episode's
    # own IMDb id resolves to its show too).
    media_type = "movie" if section == "movies" else "episode"
    try:
        tmdb_id = resolve_show_tmdb_id(media_type, ids)
    except Exception:
        logger.warning("Sync ids lookup failed for a %s entry", section, exc_info=True)
        return None, "provider_unavailable"
    if not tmdb_id:
        return None, "unknown_ids"
    return str(tmdb_id), None


def resolve_entry_ids(data, sections, limit):
    """Rewrite id-only entries to TMDB references.

    Returns ``(data, plan)``. ``plan`` lists, per section, one slot per input
    entry: ``None`` for an entry passed on to the endpoint, or the unresolved
    entry with its reason. ``plan`` is None when nothing needs resolving, or
    when the request is malformed or over ``limit`` (the endpoint's own
    validation then answers).
    """
    if not isinstance(data, dict):
        return data, None
    lists = {section: data.get(section) for section in sections}
    if not any(
        isinstance(entries, list) and any(_wants_ids(raw) for raw in entries)
        for entries in lists.values()
    ):
        return data, None
    total = sum(len(e) for e in lists.values() if isinstance(e, list))
    if total > limit:
        return data, None

    rewritten = dict(data)
    plan = []
    for section in sections:
        entries = lists[section]
        if not isinstance(entries, list):
            continue
        kept = []
        slots = []
        for raw in entries:
            if _wants_ids(raw):
                ids = _clean_ids(raw["ids"])
                tmdb_id, reason = _lookup(section, ids)
                if tmdb_id is None:
                    slots.append({"raw": raw, "ids": ids, "reason": reason})
                    continue
                raw = {**raw, "source": Sources.TMDB.value, "media_id": tmdb_id}  # noqa: PLW2901
            kept.append(raw)
            slots.append(None)
        rewritten[section] = kept
        plan.append((section, slots))
    return rewritten, plan


def has_resolved_entries(data, plan):
    """Return whether any entry is left for the endpoint to handle."""
    return any(slot is None for _, slots in plan for slot in slots)


def _unresolved_result(section, slot, style):
    raw = slot["raw"]
    outcome = (
        "metadata_unavailable"
        if slot["reason"] == "provider_unavailable"
        else "not_found"
    )
    result = {"type": _SECTION_TYPES[section]}
    if style == "history":
        result["client_event_id"] = str(raw.get("client_event_id") or "")
    else:
        result.update(source="", media_id="")
    for key in ("season_number", "episode_number"):
        if isinstance(raw.get(key), int) and not isinstance(raw.get(key), bool):
            result[key] = raw[key]
    result.update(outcome=outcome, reason=slot["reason"], ids=slot["ids"])
    return result


def splice_unresolved(results, plan, style):
    """Put a result for each unresolved entry back at its input position.

    ``results`` are the endpoint's results for the entries it received, in
    section order. ``style`` is ``"history"`` (results keyed by
    ``client_event_id``) or ``"items"`` (keyed by source/media_id).
    """
    remaining = iter(results)
    merged = []
    for section, slots in plan:
        for slot in slots:
            if slot is None:
                merged.append(next(remaining))
            else:
                merged.append(_unresolved_result(section, slot, style))
    merged.extend(remaining)
    return merged
