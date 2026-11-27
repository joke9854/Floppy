"""Settings pages for the web (v2 P4-J).

`GET /api/v1/settings/screen/<page>/` returns the settings nav and one page's
data, read the way the Django page reads it. Pages the web draws are in
`WEB_PAGES`; any other page answers `handled: false` with its Django URL, and
the web opens that instead. The web saves through the Django views' own forms
(they answer JSON for `Accept: application/json`), so validation, messages and
side effects stay in one place.
"""

from __future__ import annotations

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from rest_framework import serializers

from api import settings_data_screen as data_screen
from api import settings_import_screen as import_screen
from api import settings_integrations_screen as integrations_screen
from api import settings_preferences_screen as preferences_screen
from app.templatetags import app_tags

# The Django settings nav (users/components/ct_settings_nav.html): section,
# then (web slug, Django URL name, label). The slug is the Django path's last
# segment, so /settings/<slug> on Django is /next/settings/<slug> on the web.
NAV = (
    (
        "You",
        (
            ("account", "account", "Account"),
            ("appearance", "appearance", "Appearance"),
            ("notifications", "notifications", "Notifications"),
        ),
    ),
    (
        "Library",
        (
            ("sidebar", "sidebar", "Media types"),
            ("integrations", "integrations", "Integrations"),
            ("metadata", "metadata_settings", "Metadata"),
            ("preferences", "preferences", "Preferences"),
        ),
    ),
    (
        "Data",
        (
            ("import", "import_data", "Import"),
            ("export", "export_data", "Export"),
            ("connected-apps", "connected_apps", "Connected apps"),
            ("advanced", "advanced", "Advanced"),
            ("about", "about", "About"),
        ),
    ),
)

# Pages the web draws (P4-J1); the rest open their Django page.
WEB_PAGES = frozenset(
    {
        "account",
        "appearance",
        "notifications",
        "sidebar",
        "preferences",
        "metadata",
        "export",
        "connected-apps",
        "advanced",
        "about",
        "integrations",
        "rss",
        "import",
    }
)

_FLOATING_HINTS = {
    "hover": "Hover opens the labels over the page; nothing shifts.",
    "expanded": "Labels stay visible; the page makes room for them.",
    "icons": "Icons only; labels show as tooltips.",
}
_STYLE_HINTS = {
    "attached": "Full-height sidebar with labels, always visible.",
    "floating": "Compact bar that floats over the page.",
}


def _pages() -> dict[str, tuple[str, str]]:
    pages = {slug: (url_name, label) for _section, items in NAV for slug, url_name, label in items}
    # RSS is reached from Notifications, not the nav (as on the Django pages).
    pages["rss"] = ("rss_settings", "RSS")
    return pages


def _nav() -> list[dict]:
    return [
        {
            "label": _(section),
            "items": [
                {"slug": slug, "label": _(label), "href": reverse(url_name), "web": slug in WEB_PAGES}
                for slug, url_name, label in items
            ],
        }
        for section, items in NAV
    ]


def _item(item) -> dict:
    return {
        "id": item.id,
        "title": str(item),
        "media_type": str(app_tags.media_type_readable(item.media_type)),
        "image": app_tags.image_url(item.image),
    }


def _account(request) -> dict:
    from allauth.socialaccount.adapter import get_adapter

    user = request.user
    try:
        has_social = bool(get_adapter().list_providers(request))
    except Exception:
        has_social = False
    return {
        "username": user.username,
        "is_demo": bool(user.is_demo),
        "authenticator_enabled": bool(user.has_authenticator_configured),
        "unused_recovery_codes": user.recovery_codes.filter(used_at__isnull=True).count(),
        "social_connections_url": reverse("socialaccount_connections") if has_social else "",
        "save_url": reverse("account"),
    }


def _notifications(request) -> dict:
    user = request.user
    return {
        "notification_urls": user.notification_urls or "",
        "daily_digest_enabled": bool(user.daily_digest_enabled),
        "release_notifications_enabled": bool(user.release_notifications_enabled),
        "premiere_notifications_enabled": bool(user.premiere_notifications_enabled),
        "excluded": [_item(item) for item in user.notification_excluded_items.all()],
        "urls": {
            "save": reverse("notifications"),
            "search": reverse("search_notification_items"),
            "exclusions": reverse("api_user_notification_exclusions"),
            "test": reverse("api_user_notification_test"),
            "rss": reverse("rss_settings"),
        },
    }


def _sidebar(request) -> dict:
    from users.views import SIDEBAR_MEDIA_TYPES

    user = request.user
    order = [value for value in user.sidebar_media_type_order or [] if value in SIDEBAR_MEDIA_TYPES]
    order += [value for value in SIDEBAR_MEDIA_TYPES if value not in order]
    return {
        "clickable_media_cards": bool(user.clickable_media_cards),
        "media_types": [
            {
                "value": value,
                "label": str(app_tags.media_type_readable_plural(value)),
                "enabled": bool(getattr(user, f"{value}_enabled", False)),
            }
            for value in order
        ],
        "save_url": reverse("sidebar"),
    }


def _appearance(request) -> dict:
    from users import appearance as appearance_config
    from users.models import FloatingSidebarChoices, SidebarStyleChoices

    user = request.user
    return {
        "sidebar_style": user.sidebar_style,
        "floating_sidebar": user.floating_sidebar,
        "sidebar_styles": [
            {"value": value, "label": str(label), "hint": _(_STYLE_HINTS.get(value, ""))}
            for value, label in SidebarStyleChoices.choices
        ],
        "floating_choices": [
            {"value": value, "label": str(label), "hint": _(_FLOATING_HINTS.get(value, ""))}
            for value, label in FloatingSidebarChoices.choices
        ],
        # The detail-page layouts (hidden on the page) post back unchanged; a
        # save without them would reset every layout.
        "detail_layouts": appearance_config.resolved_detail_layouts(user.detail_page_layouts),
        "is_demo": bool(user.is_demo),
        "save_url": reverse("appearance"),
    }


def _about(_request) -> dict:
    return {
        "version": str(settings.VERSION),
        "commit": str(settings.COMMIT_SHA_SHORT or ""),
        "urls": {
            "docs": reverse("swagger-ui"),
            "openapi": reverse("openapi-contract"),
            "jsonld": reverse("jsonld-context"),
            "schema": reverse("schema"),
            "asyncapi": reverse("asyncapi-contract"),
        },
    }


_BUILDERS = {
    "account": _account,
    "notifications": _notifications,
    "sidebar": _sidebar,
    "appearance": _appearance,
    "about": _about,
    "preferences": preferences_screen.build_preferences,
    "metadata": data_screen.build_metadata,
    "export": data_screen.build_export,
    "advanced": data_screen.build_advanced,
    "connected-apps": data_screen.build_connected_apps,
    "integrations": integrations_screen.build_integrations,
    "rss": integrations_screen.build_rss,
    "import": import_screen.build_import,
}


def build_settings_screen(request, page: str) -> dict:
    """Return one settings page for the web, or the Django page to open."""
    pages = _pages()
    if page not in pages:
        return {"handled": False, "django_url": reverse("account"), "page": page, "nav": _nav()}
    url_name, label = pages[page]
    screen = {
        "handled": page in WEB_PAGES,
        "django_url": reverse(url_name),
        "page": page,
        "title": _(label),
        "nav": _nav(),
    }
    if page in WEB_PAGES:
        # connected-apps answers as `connected_apps`.
        screen[page.replace("-", "_")] = _BUILDERS[page](request)
    return screen


class SettingsNavItemSerializer(serializers.Serializer):
    """A settings page in the nav (`web`: the web draws it)."""

    slug = serializers.CharField()
    label = serializers.CharField()
    href = serializers.CharField()
    web = serializers.BooleanField()


class SettingsNavSectionSerializer(serializers.Serializer):
    """A settings nav section."""

    label = serializers.CharField()
    items = SettingsNavItemSerializer(many=True)


class SettingsAccountSerializer(serializers.Serializer):
    """Account: the username and password forms post to `save_url`."""

    username = serializers.CharField()
    is_demo = serializers.BooleanField()
    authenticator_enabled = serializers.BooleanField()
    unused_recovery_codes = serializers.IntegerField()
    social_connections_url = serializers.CharField(allow_blank=True)
    save_url = serializers.CharField()


class SettingsItemSerializer(serializers.Serializer):
    """An item excluded from notifications, or a search result."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    media_type = serializers.CharField()
    image = serializers.CharField()


class SettingsNotificationUrlsSerializer(serializers.Serializer):
    """Where the Notifications page saves, searches and tests."""

    save = serializers.CharField()
    search = serializers.CharField()
    exclusions = serializers.CharField()
    test = serializers.CharField()
    rss = serializers.CharField()


class SettingsNotificationsSerializer(serializers.Serializer):
    """Notifications: every form field posts back to `urls.save`."""

    notification_urls = serializers.CharField(allow_blank=True)
    daily_digest_enabled = serializers.BooleanField()
    release_notifications_enabled = serializers.BooleanField()
    premiere_notifications_enabled = serializers.BooleanField()
    excluded = SettingsItemSerializer(many=True)
    urls = SettingsNotificationUrlsSerializer()


class SettingsMediaTypeSerializer(serializers.Serializer):
    """A media type on the Media types page, in sidebar order."""

    value = serializers.CharField()
    label = serializers.CharField()
    enabled = serializers.BooleanField()


class SettingsSidebarSerializer(serializers.Serializer):
    """Media types: the page posts every type (one left out is turned off)."""

    clickable_media_cards = serializers.BooleanField()
    media_types = SettingsMediaTypeSerializer(many=True)
    save_url = serializers.CharField()


class SettingsChoiceSerializer(serializers.Serializer):
    """An appearance option."""

    value = serializers.CharField()
    label = serializers.CharField()
    hint = serializers.CharField(allow_blank=True)


class SettingsAppearanceSerializer(serializers.Serializer):
    """Appearance: post `detail_layouts` back with the sidebar choices."""

    sidebar_style = serializers.CharField()
    floating_sidebar = serializers.CharField()
    sidebar_styles = SettingsChoiceSerializer(many=True)
    floating_choices = SettingsChoiceSerializer(many=True)
    detail_layouts = serializers.JSONField()
    is_demo = serializers.BooleanField()
    save_url = serializers.CharField()


class SettingsAboutUrlsSerializer(serializers.Serializer):
    """The API documents About links to."""

    docs = serializers.CharField()
    openapi = serializers.CharField()
    jsonld = serializers.CharField()
    schema = serializers.CharField()
    asyncapi = serializers.CharField()


class SettingsAboutSerializer(serializers.Serializer):
    """About: the running version."""

    version = serializers.CharField()
    commit = serializers.CharField(allow_blank=True)
    urls = SettingsAboutUrlsSerializer()


class SettingsScreenSerializer(serializers.Serializer):
    """A settings page for the web app (`handled: false`: open `django_url`)."""

    handled = serializers.BooleanField()
    django_url = serializers.CharField()
    page = serializers.CharField()
    title = serializers.CharField(required=False)
    nav = SettingsNavSectionSerializer(many=True)
    account = SettingsAccountSerializer(required=False)
    notifications = SettingsNotificationsSerializer(required=False)
    sidebar = SettingsSidebarSerializer(required=False)
    appearance = SettingsAppearanceSerializer(required=False)
    about = SettingsAboutSerializer(required=False)
    preferences = preferences_screen.SettingsPreferencesSerializer(required=False)
    metadata = data_screen.SettingsMetadataSerializer(required=False)
    export = data_screen.SettingsExportSerializer(required=False)
    advanced = data_screen.SettingsAdvancedSerializer(required=False)
    connected_apps = data_screen.SettingsConnectedAppsSerializer(required=False)
    integrations = integrations_screen.SettingsIntegrationsSerializer(required=False)
    rss = integrations_screen.SettingsRssSerializer(required=False)
    import_ = import_screen.SettingsImportSerializer(required=False, source="import")
