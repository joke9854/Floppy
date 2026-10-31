import secrets

from django.db import migrations, models

import users.models


def _column_exists(schema_editor, table_name, column_name):
    """Return True when a database column already exists."""
    connection = schema_editor.connection
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema = current_schema() "
                "AND table_name = %s AND column_name = %s",
                [table_name, column_name],
            )
            return cursor.fetchone() is not None
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table_name)
        columns = {getattr(column, "name", column[0]) for column in description}
        return column_name in columns


class AddFieldIfNotExists(migrations.AddField):
    """Add a field only when the backing column doesn't already exist."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        to_model = to_state.apps.get_model(app_label, self.model_name)
        field = to_model._meta.get_field(self.name)
        if _column_exists(schema_editor, to_model._meta.db_table, field.column):
            return
        super().database_forwards(app_label, schema_editor, from_state, to_state)


def fill_calendar_tokens(apps, _schema_editor):
    """Give every existing user their own calendar token.

    The column is added nullable first: a callable default is evaluated once
    for AddField, which would hand every row the same value and fail the
    unique constraint.
    """
    User = apps.get_model("users", "User")
    for user in User.objects.filter(calendar_token__isnull=True).iterator():
        user.calendar_token = secrets.token_urlsafe(24)
        user.save(update_fields=["calendar_token"])


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0136_user_theme_cinetrack"),
    ]

    operations = [
        AddFieldIfNotExists(
            model_name="user",
            name="calendar_token",
            field=models.CharField(max_length=32, null=True),
        ),
        migrations.RunPython(fill_calendar_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="calendar_token",
            field=models.CharField(
                default=users.models.generate_token,
                help_text="Token for the iCalendar subscription URL",
                max_length=32,
                unique=True,
            ),
        ),
    ]
