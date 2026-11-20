from datetime import date

from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from app import (
    people_data,
)
from app.media_list_views import build_filter_data_from_items
from users.models import MediaSortChoices

logger = __import__("logging").getLogger(__name__)


KNOWN_FOR_LIMIT = 10


def _person_age(person_data):
    """Return a person's age (at death, if they died), or None without a birth date."""
    try:
        born = date.fromisoformat(str(person_data.get("birth_date") or ""))
    except ValueError:
        return None
    try:
        until = date.fromisoformat(str(person_data.get("death_date") or ""))
    except ValueError:
        until = timezone.localdate()
    return until.year - born.year - ((until.month, until.day) < (born.month, born.day))


@require_GET
def person_detail(request, source, person_id, name):
    """Render a provider-backed person or author profile page."""
    del name  # URL slug is cosmetic; person_id is canonical.
    context = build_person_context(request, source, person_id)
    if isinstance(context, HttpResponse):
        return context
    if request.headers.get("HX-Request"):
        return render(
            request, "app/components/person_filmography_fragment.html", context
        )
    return render(request, "app/person_detail.html", context)


def build_person_context(request, source, person_id):
    """Build the person page's context, or the 400 for a source without pages.

    The ``person_detail`` view and the web person screen API both call it, so
    they show the same person, numbers and filmography.
    """
    page = people_data.build_person_page(request.user, source, person_id)
    if page is None:
        return HttpResponseBadRequest("Person pages are not available for this source.")
    person_data = page["person"]
    is_author = page["is_author"]
    filmography = page["filmography"]
    watched_filmography = page["watched_filmography"]
    known_for = page["known_for"]
    all_departments = page["all_departments"]
    all_filmography_years = page["all_filmography_years"]

    filter_department = request.GET.get("department", "")
    filter_year = request.GET.get("year", "")
    filter_genre = request.GET.get("genre", "")
    filter_implied_genre = request.GET.get("implied_genre", "")
    filter_source = request.GET.get("source", "")
    filter_rating = request.GET.get("rating", "all")
    filter_collection = request.GET.get("collection", "all")
    # Use the same sort key names as MediaSortChoices for consistency with the
    # rest of the app. "release_date" desc is the default provider ordering.
    person_valid_sorts = {
        MediaSortChoices.RELEASE_DATE.value,
        MediaSortChoices.TITLE.value,
        MediaSortChoices.CRITIC_RATING.value,
        MediaSortChoices.POPULARITY.value,
        "votes",
    }
    sort_by = request.GET.get("sort", MediaSortChoices.RELEASE_DATE.value)
    if sort_by not in person_valid_sorts:
        sort_by = MediaSortChoices.RELEASE_DATE.value
    sort_dir = request.GET.get("direction", "")
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "asc" if sort_by == MediaSortChoices.TITLE.value else "desc"

    def _apply_common_filters(entries):
        """Build the filters that apply to every filmography entry."""
        result = entries
        if filter_department:
            result = [
                e
                for e in result
                if filter_department in e.get("all_departments", [e.get("department")])
            ]
        if filter_year:
            result = [e for e in result if str(e.get("year") or "") == filter_year]
        return result

    def _apply_watched_filters(entries):
        """Build the filters that need tracked_item data, for watched entries only."""
        result = entries
        if filter_genre:
            result = [
                e
                for e in result
                if filter_genre
                in (getattr(e.get("tracked_item"), "genres", None) or [])
            ]
        if filter_implied_genre:
            result = [
                e
                for e in result
                if filter_implied_genre
                in (getattr(e.get("tracked_item"), "implied_genres", None) or [])
            ]
        if filter_source:
            result = [
                e
                for e in result
                if getattr(e.get("tracked_item"), "source", None) == filter_source
            ]
        if filter_rating == "rated":
            result = [
                e
                for e in result
                if getattr(e.get("tracked_item"), "score", None) is not None
            ]
        elif filter_rating == "not_rated":
            result = [
                e
                for e in result
                if getattr(e.get("tracked_item"), "score", None) is None
            ]
        if filter_collection == "collected":
            result = [
                e
                for e in result
                if getattr(e.get("tracked_item"), "in_collection", False)
            ]
        elif filter_collection == "not_collected":
            result = [
                e
                for e in result
                if not getattr(e.get("tracked_item"), "in_collection", False)
            ]
        return result

    def _sort_with_nulls_last(entries, key_fn, reverse):
        """Sort entries by key_fn, always placing None-valued entries at the end."""
        has_value = [e for e in entries if key_fn(e) is not None]
        no_value = [e for e in entries if key_fn(e) is None]
        return sorted(has_value, key=key_fn, reverse=reverse) + no_value

    def _apply_sort(entries):
        rev = sort_dir == "desc"
        if sort_by == MediaSortChoices.TITLE.value:
            return sorted(
                entries, key=lambda e: e.get("title", "").lower(), reverse=rev
            )
        if sort_by == MediaSortChoices.CRITIC_RATING.value:
            return _sort_with_nulls_last(entries, lambda e: e.get("vote_average"), rev)
        if sort_by == MediaSortChoices.POPULARITY.value:
            return _sort_with_nulls_last(entries, lambda e: e.get("popularity"), rev)
        if sort_by == "votes":

            def _vote_count_key(e):
                vc = e.get("vote_count")
                if vc is None:
                    item = e.get("tracked_item")
                    if item is not None:
                        vc = item.provider_rating_count
                return vc

            return _sort_with_nulls_last(entries, _vote_count_key, rev)
        # release_date: entries arrive from provider already sorted newest-first;
        # asc reverses to oldest-first (chronological).
        if sort_dir == "asc":
            return list(reversed(entries))
        return entries

    # Collect tracked items from the unfiltered watched list for filter option building.
    watched_items_for_filter_data = [
        e["tracked_item"] for e in watched_filmography if e.get("tracked_item")
    ]

    filmography = _apply_sort(_apply_common_filters(filmography))
    watched_filmography = _apply_sort(
        _apply_common_filters(_apply_watched_filters(watched_filmography))
    )

    from django.urls import reverse

    history_filter_url = (
        f"{reverse('history')}?person_source={source}&person_id={person_id}"
    )

    person_sort_choices = (
        [
            (MediaSortChoices.RELEASE_DATE.value, MediaSortChoices.RELEASE_DATE.label),
            (MediaSortChoices.TITLE.value, MediaSortChoices.TITLE.label),
        ]
        if is_author
        else [
            (MediaSortChoices.RELEASE_DATE.value, MediaSortChoices.RELEASE_DATE.label),
            (MediaSortChoices.TITLE.value, MediaSortChoices.TITLE.label),
            (
                MediaSortChoices.CRITIC_RATING.value,
                MediaSortChoices.CRITIC_RATING.label,
            ),
            (MediaSortChoices.POPULARITY.value, MediaSortChoices.POPULARITY.label),
            ("votes", "Votes"),
        ]
    )

    # Build filter options from tracked (watched) items using the shared function so
    # any new filter dimension added there automatically appears here too.
    filter_data = build_filter_data_from_items(watched_items_for_filter_data)

    # Supplement with filmography-level data not available from tracked items.
    filter_data["departments"] = all_departments if not is_author else []
    filter_data["tags"] = []
    filter_data["show_progress"] = False

    # Years: merge watched-item years with years from the full unfiltered filmography
    # so the year filter covers films not yet tracked by the user.
    watched_years = {
        int(y["value"]) for y in filter_data["years"] if y["value"].isdigit()
    }
    combined_years = sorted(watched_years | set(all_filmography_years), reverse=True)
    filter_data["years"] = [{"value": str(y), "label": str(y)} for y in combined_years]

    return {
        "user": request.user,
        "person": person_data,
        "is_author": is_author,
        "watched_filmography": watched_filmography,
        "watched_movie_count": page["watched_movie_count"],
        "watched_show_count": page["watched_show_count"],
        "watched_book_count": page["watched_book_count"],
        "filmography": filmography,
        "known_for": known_for,
        "person_age": _person_age(person_data),
        "history_filter_url": history_filter_url,
        "tracked_plays_count": page["tracked_plays_count"],
        "tracked_hours_count": page["tracked_hours_count"],
        "source": source,
        "source_url": page["source_url"],
        # Filter/sort state (named to match media_list convention)
        "current_sort": sort_by,
        "current_direction": sort_dir,
        "current_department": filter_department,
        "current_year": filter_year,
        "current_genre": filter_genre,
        "current_implied_genre": filter_implied_genre,
        "current_source": filter_source,
        "current_rating": filter_rating,
        "current_collection": filter_collection,
        "sort_choices": person_sort_choices,
        "status_choices": [],
        "filter_data": filter_data,
        "supports_critic_rating_sort": not is_author,
        "person_detail_url": request.path,
    }


def studio_detail(request, source, studio_id, name):
    """Render a provider-backed studio/company profile page."""
    del name  # URL slug is cosmetic; studio_id is canonical.

    page = people_data.build_studio_page(source, studio_id)

    context = {
        "user": request.user,
        "studio": page["studio"],
        "source": source,
        "credited_titles": page["credited_titles"],
        "credited_media_type": page["credited_media_type"],
        "studio_description": page["studio_description"],
        "studio_source_url": page["studio_source_url"],
        "studio_founded": page["studio_founded"],
        "studio_developed_count": page["studio_developed_count"],
        "studio_published_count": page["studio_published_count"],
        "studio_games_count": len(page["credited_titles"]),
        "IMG_NONE": settings.IMG_NONE,
    }
    return render(request, "app/studio_detail.html", context)
