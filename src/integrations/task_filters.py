"""Match a periodic task's kwargs to one user."""


def user_kwargs_regex(user_id):
    """Return a regex for `"user_id": <user_id>` followed by `,` or `}`.

    A plain `kwargs__contains='"user_id": 1'` also matches users 10-19, so
    a schedule lookup or delete for one user could reach another's. Quoting
    and spacing vary with how the kwargs were written.
    """
    return rf"""['"]user_id['"]:\s*{int(user_id)}\s*[,}}]"""
