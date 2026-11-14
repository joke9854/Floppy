"""Make a copy of a production database safe to run as a beta instance."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django_celery_beat.models import PeriodicTask


class Command(BaseCommand):
    """Disable every per-user integration schedule in a copied database."""

    help = (
        "Disable the per-user periodic tasks (integration imports and polls) "
        "in a copied database. Refuses to run unless FLOPPY_BETA_MODE is on. "
        "Deletes nothing and is safe to run again."
    )

    def handle(self, *args, **options):
        """Disable periodic tasks that are not part of the built-in schedule."""
        if not settings.FLOPPY_BETA_MODE:
            message = (
                "Refusing to run: FLOPPY_BETA_MODE is not enabled. This command "
                "disables schedules and must never run against the real instance."
            )
            raise CommandError(message)

        builtin_names = list(settings.CELERY_BEAT_SCHEDULE)
        disabled = (
            PeriodicTask.objects.filter(enabled=True)
            .exclude(name__in=builtin_names)
            .update(enabled=False)
        )
        self.stdout.write(
            self.style.SUCCESS(f"Disabled {disabled} per-user periodic task(s)."),
        )
