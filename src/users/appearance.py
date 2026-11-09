import json

from django.core.exceptions import ValidationError


def _zone(label, *sections):
    return {
        "label": label,
        "sections": [{"key": key, "label": title} for key, title in sections],
    }


DETAIL_LAYOUT_FAMILIES = {
    "media": {
        "label": "Films, books and manga",
        "zones": {
            "sidebar": _zone(
                "Information column",
                ("history", "Your history"),
                ("details", "Details"),
                ("genres", "Genres"),
                ("studios", "Studios"),
                ("collection", "Collection"),
            ),
            "content": _zone(
                "Main content",
                ("notes", "Notes"),
                ("related", "Related titles"),
                ("cast", "Cast"),
                ("crew", "Crew"),
                ("recommendations", "Recommendations"),
            ),
        },
    },
    "series": {
        "label": "Series and seasons",
        "zones": {
            "sidebar": _zone(
                "Information column",
                ("history", "Your history"),
                ("details", "Details"),
                ("genres", "Genres"),
                ("studios", "Studios"),
                ("collection", "Collection"),
            ),
            "content": _zone(
                "Main content",
                ("notes", "Notes"),
                ("seasons", "Seasons"),
                ("episodes", "Episodes"),
                ("cast", "Cast"),
                ("crew", "Crew"),
                ("recommendations", "Recommendations"),
            ),
        },
    },
    "game": {
        "label": "Games",
        "zones": {
            "sidebar": _zone(
                "Information column",
                ("history", "Your history"),
                ("details", "Details"),
                ("genres", "Genres"),
                ("studios", "Studios"),
                ("collection", "Collection"),
            ),
            "content": _zone(
                "Main content",
                ("notes", "Notes"),
                ("game_lengths", "Play times"),
                ("cast", "Cast"),
                ("crew", "Crew"),
                ("recommendations", "Recommendations"),
            ),
        },
    },
    "episode": {
        "label": "Episodes",
        "zones": {
            "content": _zone(
                "Content",
                ("notes", "Notes"),
                ("cast", "Cast"),
                ("crew", "Crew"),
            )
        },
    },
    "comic": {
        "label": "Comic volumes",
        "zones": {
            "sidebar": _zone(
                "Information column",
                ("history", "Your history"),
                ("details", "Details"),
                ("genres", "Genres"),
                ("studios", "Studios"),
                ("collection", "Collection"),
            ),
            "content": _zone(
                "Main content",
                ("notes", "Notes"),
                ("episodes", "Issues"),
                ("recommendations", "Recommendations"),
            ),
        },
    },
    "comic_issue": {
        "label": "Comic issues",
        "zones": {
            "sidebar": _zone(
                "Information column",
                ("details", "Details"),
                ("authors", "Authors"),
                ("collection", "Collection"),
            ),
        },
    },
    "music_album": {
        "label": "Music albums",
        "zones": {
            "sidebar": _zone(
                "Information column",
                ("details", "Details"),
                ("collection", "Collection"),
            ),
            "content": _zone(
                "Main content", ("notes", "Notes"), ("tracks", "Tracks")
            ),
        },
    },
    "music_artist": {
        "label": "Music artists",
        "zones": {
            "sidebar": _zone(
                "Information column",
                ("details", "Details"),
                ("collection", "Collection"),
            ),
            "content": _zone(
                "Main content",
                ("notes", "Notes"),
                ("relations", "Related artists"),
                ("discography", "Discography"),
            ),
        },
    },
    "podcast": {
        "label": "Podcasts",
        "zones": {
            "sidebar": _zone(
                "Information column",
                ("details", "Details"),
                ("genres", "Genres"),
            ),
            "content": _zone(
                "Main content", ("notes", "Notes"), ("episodes", "Episodes")
            ),
        },
    },
    "person": {
        "label": "People",
        "zones": {
            "hero": _zone("Profile", ("biography", "Biography and facts")),
            "content": _zone("Content", ("filmography", "Filmography")),
        },
    },
    "studio": {
        "label": "Studios",
        "zones": {
            "hero": _zone("Profile", ("overview", "Overview and facts")),
            "content": _zone("Content", ("works", "Works")),
        },
    },
}

_INVALID_LAYOUT = "Invalid detail layout configuration."
_INVALID_FAMILY = "Unsupported detail page family."
_INVALID_ZONE = "Unsupported detail page zone."
_INVALID_SECTION = "Unsupported detail page section."


def default_detail_layouts():
    """Return the complete default order for every detail page zone."""
    return {
        family_key: {
            zone_key: [section["key"] for section in zone["sections"]]
            for zone_key, zone in family["zones"].items()
        }
        for family_key, family in DETAIL_LAYOUT_FAMILIES.items()
    }


def resolved_detail_layouts(saved_layouts):
    """Overlay valid saved choices on the current default registry."""
    resolved = default_detail_layouts()
    if not isinstance(saved_layouts, dict):
        return resolved
    for family_key, family_layout in saved_layouts.items():
        if family_key not in resolved or not isinstance(family_layout, dict):
            continue
        for zone_key, section_keys in family_layout.items():
            if zone_key in resolved[family_key] and isinstance(section_keys, list):
                resolved[family_key][zone_key] = section_keys
    return resolved


def parse_detail_layouts(raw_payload):
    """Parse and validate ordered visible sections submitted by settings."""
    try:
        payload = json.loads(raw_payload or "{}")
    except json.JSONDecodeError as exc:
        raise ValidationError(_INVALID_LAYOUT) from exc
    if not isinstance(payload, dict):
        raise ValidationError(_INVALID_LAYOUT)

    cleaned = {}
    for family_key, family_layout in payload.items():
        family = DETAIL_LAYOUT_FAMILIES.get(family_key)
        if family is None or not isinstance(family_layout, dict):
            raise ValidationError(_INVALID_FAMILY)
        cleaned_family = {}
        for zone_key, section_keys in family_layout.items():
            zone = family["zones"].get(zone_key)
            if zone is None or not isinstance(section_keys, list):
                raise ValidationError(_INVALID_ZONE)
            allowed = {section["key"] for section in zone["sections"]}
            if len(section_keys) != len(set(section_keys)) or any(
                not isinstance(key, str) or key not in allowed for key in section_keys
            ):
                raise ValidationError(_INVALID_SECTION)
            cleaned_family[zone_key] = section_keys
        cleaned[family_key] = cleaned_family
    return cleaned
