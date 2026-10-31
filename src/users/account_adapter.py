from allauth.account.adapter import DefaultAccountAdapter
from django.contrib.auth import get_user_model


class NoNewUsersAccountAdapter(DefaultAccountAdapter):
    """Closed sign-up, except for the first account on a fresh install."""

    def is_open_for_signup(self, request):
        """Allow sign-up only while no real (non-demo) account exists.

        Queried directly rather than through the cached is_first_run, so a
        second visitor cannot sign up in the minutes after the first one.
        """
        return not get_user_model().objects.filter(is_demo=False).exists()
