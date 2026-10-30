from allauth.account.signals import user_signed_up
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.db import connection
from django.db.models.signals import post_migrate
from django.db.utils import OperationalError, ProgrammingError
from django.dispatch import receiver

from app.models import MediaTypes
from users.demo import ensure_demo_user
from users.models import ThemeChoices

# Media types a new account starts with; the rest are one switch away in Settings.
NEW_ACCOUNT_MEDIA_TYPES = frozenset(
    (
        MediaTypes.TV.value,
        MediaTypes.SEASON.value,
        MediaTypes.MOVIE.value,
        MediaTypes.ANIME.value,
    ),
)


def _demo_user_schema_ready():
    """Only provision the demo user once the current user schema exists."""
    user_model = get_user_model()
    table_name = user_model._meta.db_table

    try:
        if table_name not in connection.introspection.table_names():
            return False

        with connection.cursor() as cursor:
            columns = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor,
                    table_name,
                )
            }
    except (OperationalError, ProgrammingError):
        return False

    required_columns = {
        field.column for field in user_model._meta.local_concrete_fields
    }
    return required_columns.issubset(columns)


@receiver(user_logged_in)
def apply_session_duration(sender, request, user, **kwargs):
    """Set session expiry to match the user's session_duration preference."""
    duration = getattr(user, "session_duration", None)
    if duration is not None:
        request.session.set_expiry(duration)


@receiver(user_signed_up)
def apply_new_account_defaults(sender, request, user, **kwargs):
    """Start a newly signed-up account on CineTrack with TV, Movies and Anime."""
    user.theme = ThemeChoices.CINETRACK
    update_fields = ["theme"]
    for media_type in MediaTypes.values:
        field_name = f"{media_type}_enabled"
        if hasattr(user, field_name):
            setattr(user, field_name, media_type in NEW_ACCOUNT_MEDIA_TYPES)
            update_fields.append(field_name)
    user.save(update_fields=update_fields)


@receiver(post_migrate)
def ensure_demo_user_after_migrate(sender, **kwargs):
    """Provision the configured demo account after migrations."""
    if getattr(settings, "TESTING", False):
        return

    if not getattr(settings, "DEMO_ACCOUNT_ENABLED", True):
        return

    if getattr(sender, "label", None) != "users":
        return

    if not _demo_user_schema_ready():
        return

    ensure_demo_user()
