from django.db import models


class ApplicationSettings(models.Model):
    """Instance-wide settings that are not tied to a user account."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    image_caching_enabled = models.BooleanField(default=False)
    # How long a cached image is kept: unused ones are removed after this many
    # days, and older copies are downloaded again to pick up provider changes.
    image_cache_days = models.PositiveSmallIntegerField(
        default=30,
        choices=[(7, "7 days"), (15, "15 days"), (30, "30 days")],
    )

    class Meta:
        """Model metadata."""

        verbose_name = "application setting"
        verbose_name_plural = "application settings"

    def __str__(self):
        """Return the singleton's human-readable label."""
        return "Application settings"
