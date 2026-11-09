"""Retire the classic themes: every account moves to CineTrack v2.

The custom palette column is left in place (unused) so a user's saved colours
are not deleted by an upgrade.
"""

from django.db import migrations, models


def move_to_cinetrack(apps, schema_editor):
    user_model = apps.get_model("users", "User")
    user_model.objects.exclude(theme="cinetrack").update(theme="cinetrack")


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0139_user_hide_episode_overviews"),
    ]

    operations = [
        migrations.RunPython(move_to_cinetrack, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="theme",
            field=models.CharField(
                choices=[("cinetrack", "CineTrack")],
                default="cinetrack",
                max_length=20,
            ),
        ),
    ]
