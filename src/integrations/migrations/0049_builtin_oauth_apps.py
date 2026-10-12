"""Seed the trusted apps that may sign in to Floppy (OAuth 2.0 / OpenID Connect).

The toolkit gives each app one grant type, so Nuvio's TV sign-in (device flow)
is its own app, ``nuvio-tv``. Which scopes an app may request is decided by
``api.oauth.AppScopes``, not stored here.
"""

from django.db import migrations

BUILTIN_APPS = [
    {
        "client_id": "cinetrack",
        "name": "CineTrack",
        "authorization_grant_type": "authorization-code",
        "redirect_uris": "cinetrack://floppy",
    },
    {
        "client_id": "nuvio",
        "name": "Nuvio",
        "authorization_grant_type": "authorization-code",
        # Loopback redirects match on any port (RFC 8252).
        "redirect_uris": "nuvio://floppy http://127.0.0.1/floppy",
    },
    {
        "client_id": "nuvio-tv",
        "name": "Nuvio (TV)",
        "authorization_grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "redirect_uris": "",
    },
]


def create_builtin_apps(apps, schema_editor):
    """Create the built-in public apps; never overwrite an admin's edits."""
    Application = apps.get_model("oauth2_provider", "Application")
    for spec in BUILTIN_APPS:
        Application.objects.get_or_create(
            client_id=spec["client_id"],
            defaults={
                "name": spec["name"],
                "client_type": "public",
                "authorization_grant_type": spec["authorization_grant_type"],
                "redirect_uris": spec["redirect_uris"],
                # Public apps have no secret.
                "client_secret": "",
                "hash_client_secret": False,
                # Consent is shown on every sign-in.
                "skip_authorization": False,
                # Sign ID tokens with the server's RSA key.
                "algorithm": "RS256",
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0048_alter_syncbinding_client_kind"),
        ("oauth2_provider", "0022_refreshtoken_token_family_index"),
    ]

    operations = [
        migrations.RunPython(create_builtin_apps, migrations.RunPython.noop),
    ]
