"""Webhook filters shared by the web settings and the API: Seerr."""

from app.models import Status

SEERR_STATUSES = frozenset(
    {"UNKNOWN", "PENDING", "PROCESSING", "PARTIALLY_AVAILABLE", "AVAILABLE"},
)
SEERR_DEFAULT_STATUSES = (Status.PLANNING.value, Status.IN_PROGRESS.value)


class WebhookSettingsError(ValueError):
    """The settings cannot be saved; the message says why."""


def save_seerr_settings(
    user,
    *,
    enabled,
    trigger_statuses,
    allowed_usernames,
    default_added_status,
):
    """Validate and save the Seerr webhook settings.

    `trigger_statuses` and `allowed_usernames` are lists; empty trigger
    statuses mean the default behaviour (UNKNOWN is skipped). An unknown
    default status falls back to Planning.
    """
    tokens = [str(t).strip().upper() for t in trigger_statuses if str(t).strip()]
    unknown = [t for t in tokens if t not in SEERR_STATUSES]
    if unknown:
        msg = (
            "Seerr trigger statuses contain invalid values: "
            + ", ".join(unknown)
            + ". Valid: "
            + ", ".join(sorted(SEERR_STATUSES))
        )
        raise WebhookSettingsError(msg)
    if default_added_status not in SEERR_DEFAULT_STATUSES:
        default_added_status = Status.PLANNING.value

    # kept: reads/writes the unrenamed jellyseerr_* model fields
    user.jellyseerr_enabled = bool(enabled)
    user.jellyseerr_trigger_statuses = ",".join(tokens)
    user.jellyseerr_allowed_usernames = ",".join(
        str(name).strip() for name in allowed_usernames if str(name).strip()
    )
    user.jellyseerr_default_added_status = default_added_status
    user.save(
        update_fields=[
            "jellyseerr_enabled",
            "jellyseerr_trigger_statuses",
            "jellyseerr_allowed_usernames",
            "jellyseerr_default_added_status",
        ],
    )
