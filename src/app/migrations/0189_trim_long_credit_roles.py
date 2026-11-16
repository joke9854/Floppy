"""Cut cast/crew roles longer than their 255-character column.

SQLite never enforced the length, so a few provider roles (long joined
character lists) were stored in full. Postgres refuses them, which stopped
the SQLite-to-Postgres copy. Credits are rebuilt from the provider on every
metadata refresh, and the writer now cuts roles to the column length too.

When the cut role equals another credit of the same item, person, role type
and department, the long row is a duplicate of it and is removed, because
the unique constraint would refuse the update.
"""

from django.db import migrations
from django.db.models.functions import Length

ROLE_MAX_LENGTH = 255


def trim_long_credit_roles(apps, schema_editor):
    """Cut every role over ROLE_MAX_LENGTH, dropping exact duplicates."""
    credit_model = apps.get_model("app", "ItemPersonCredit")
    long_credits = (
        credit_model.objects.annotate(role_length=Length("role"))
        .filter(role_length__gt=ROLE_MAX_LENGTH)
        .order_by("pk")
    )
    trimmed = removed = 0
    for credit in long_credits.iterator():
        role = credit.role[:ROLE_MAX_LENGTH].rstrip()
        duplicate = (
            credit_model.objects.filter(
                item_id=credit.item_id,
                person_id=credit.person_id,
                role_type=credit.role_type,
                department=credit.department,
                role=role,
            )
            .exclude(pk=credit.pk)
            .exists()
        )
        if duplicate:
            credit.delete()
            removed += 1
        else:
            credit_model.objects.filter(pk=credit.pk).update(role=role)
            trimmed += 1
    if trimmed or removed:
        print(  # noqa: T201
            f"\n  Cut {trimmed} long credit role(s) to {ROLE_MAX_LENGTH} characters;"
            f" removed {removed} that matched an existing credit.",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0188_applicationsettings_image_cache_days"),
    ]

    operations = [
        migrations.RunPython(trim_long_credit_roles, migrations.RunPython.noop),
    ]
