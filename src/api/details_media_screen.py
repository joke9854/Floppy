"""The web detail pages for music artists, albums and podcast shows (v2 P4-L2).

Like `details_screen`, each is the Django page's own context builder
(`app.music_views.build_music_artist_context`, `build_music_album_context`,
`app.media_details_views.build_podcast_show_context`) shaped as JSON, so the
web shows exactly what /details/... shows. A builder answers the page's
`HttpResponse` (a redirect, a merge, a canonical move) as is; the view turns it
into a 400 and the web opens the Django page, which redirects.

Every play carries its historical row's `history_id`: what the page's play
dialog (`fill_track_song.html`) sends to `delete_history_record`, and what
`DELETE /api/v1/history/<music|podcast>/<history_id>/` deletes.
"""

from __future__ import annotations

from urllib.parse import quote

from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import NoReverseMatch, reverse
from rest_framework import serializers

from app.models import Artist, MediaTypes
from app.templatetags import app_tags
from users.templatetags import user_tags

from .details_screen import (
    DetailInfoSerializer,
    DetailLinkSectionSerializer,
    DetailNamedLinkSerializer,
    _links,
    _text,
)

PODCAST_SOURCES = ("pocketcasts", "gpodder", "audiobookshelf")
EPISODES_PAGE_SIZE = 20


def _image(value) -> str:
    return app_tags.image_url(value or settings.IMG_NONE)


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _score(value) -> float | None:
    return float(value) if value is not None else None


def _activity(subtitle, text_key) -> dict | None:
    if not subtitle:
        return None
    return {
        "primary_text": _text(subtitle.get(text_key)),
        "date_start": _iso(subtitle.get("date_start")),
        "date_end": _iso(subtitle.get("date_end")),
    }


def _tracker(tracker) -> dict | None:
    if tracker is None:
        return None
    return {"status": tracker.status or None, "score": _score(tracker.score)}


def _plays(history, user) -> list[dict]:
    """Return the completed plays, newest first, as the page's dialog lists them."""
    plays = [
        entry
        for entry in history
        if entry.end_date and getattr(entry, "history_user_id", None) in (None, user.id)
    ]
    plays.sort(key=lambda entry: entry.end_date, reverse=True)
    return [
        {"history_id": entry.history_id, "end_date": entry.end_date.isoformat()}
        for entry in plays
    ]


def _music_genres(names) -> list[dict]:
    base = reverse("medialist", kwargs={"media_type": MediaTypes.MUSIC.value})
    return [
        {"name": _text(name), "url": f"{base}?genre={quote(_text(name))}"}
        for name in names or []
    ]


def _relation(relation) -> dict:
    related = relation["artist"]
    return {
        "id": related.id,
        "name": _text(related.name),
        "image": _image(related.image),
        "url": app_tags.music_artist_url(related),
        "role": _text(relation.get("role")),
        "is_current": bool(relation.get("is_current")),
    }


def build_artist_screen(request, artist_id) -> dict | HttpResponse | None:
    """Return the artist page, its redirect, or None for no such artist."""
    from app.music_views import build_music_artist_context

    artist = Artist.objects.filter(id=artist_id).first()
    if artist is None:
        return None
    context = build_music_artist_context(request, artist)
    if isinstance(context, HttpResponse):
        return context
    artist = context["artist"]
    metadata = context.get("music_artist_metadata") or {}
    rating = context.get("music_artist_rating") or {}
    is_group = metadata.get("type") == "Group"
    details = [
        ("Type", metadata.get("type")),
        ("Origin", metadata.get("area") or metadata.get("country")),
        ("Formed" if is_group else "Born", metadata.get("begin_date")),
        ("Disbanded" if is_group else "Died", metadata.get("end_date")),
        ("Releases", context.get("total_releases")),
    ]
    return {
        "artist": {
            "id": artist.id,
            "name": _text(artist.name),
            "image": _image(artist.image),
            "url": app_tags.music_artist_url(artist),
            "bio": _text(context.get("bio")),
            "musicbrainz_url": f"https://musicbrainz.org/artist/{artist.musicbrainz_id}"
            if artist.musicbrainz_id
            else None,
        },
        "activity": _activity(
            context.get("music_artist_activity_subtitle"), "primary_text"
        ),
        "rating": {
            "rating": rating.get("rating"),
            "rating_count": rating.get("rating_count")
            if rating.get("rating") is not None
            else None,
        },
        "tracker": _tracker(context.get("artist_tracker")),
        "genres": [
            {"name": _text(name), "url": ""}
            for name in context.get("genre_chips") or []
        ],
        "details": [
            {"label": label, "value": _text(value)}
            for label, value in details
            if value not in (None, "")
        ],
        "members": [_relation(item) for item in context.get("band_members") or []],
        "member_of": [_relation(item) for item in context.get("member_of_bands") or []],
        "discography": [
            {
                "label": _text(group["label"]),
                "albums": [
                    {
                        "id": album.id,
                        "title": _text(album.title),
                        "image": _image(album.image),
                        "release_date": _iso(album.release_date),
                        "release_type": _text(album.release_type),
                        "url": app_tags.music_album_url(album),
                        "play_count": getattr(album, "play_count", 0),
                        "score": _score(getattr(album, "score", None)),
                    }
                    for album in group["albums"]
                ],
            }
            for group in context.get("discography_groups") or []
        ],
        "history_url": _text(context.get("detail_history_url")),
        "sync_url": f"/api/v1/music/artists/{artist.id}/sync-discography/",
        "links": _links(context),
    }


def build_album_screen(request, artist_id, album_id) -> dict | HttpResponse | None:
    """Return the album page, its redirect, or None for no such album."""
    from django.http import Http404

    from app.music_views import build_music_album_context, resolve_music_album

    try:
        album = resolve_music_album(request, artist_id, album_id)
    except Http404:
        return None
    if isinstance(album, HttpResponse):
        return album
    context = build_music_album_context(request, album.artist, album)
    if isinstance(context, HttpResponse):
        return context
    album = context["album"]
    user = request.user
    credited_artists = [credit.artist for credit in album.artist_credits.all()]
    if not credited_artists and context.get("artist"):
        credited_artists = [context["artist"]]
    metadata = context.get("music_album_metadata") or {}
    genres = _music_genres(album.genres)
    seen = {genre["name"].casefold() for genre in genres}
    for name in album.implied_genres or []:
        if _text(name).casefold() not in seen:
            seen.add(_text(name).casefold())
            genres.append({"name": _text(name), "url": ""})
    details = [
        ("Format", metadata.get("format")),
        (
            "Release date",
            user_tags.user_date_format(album.release_date, user)
            if album.release_date
            else "",
        ),
        ("Tracks", context.get("total_tracks")),
        ("Runtime", context.get("total_runtime")),
    ]
    selected = context.get("selected_music_release")
    tracks = []
    for row in context.get("tracks") or []:
        track = row["track"]
        music = row["music"]
        plays = _plays(row["history"], user)
        tracks.append(
            {
                "track_id": track.id,
                "recording_id": track.musicbrainz_recording_id,
                "title": _text(track.title),
                "disc": track.disc_number,
                "number": track.track_number,
                "duration": _text(track.duration_formatted),
                "music_id": music.id if music else None,
                "play_count": len(plays),
                "last_played": plays[0]["end_date"] if plays else None,
                "plays": plays,
            }
        )
    return {
        "album": {
            "id": album.id,
            "title": _text(album.title),
            "image": _image(context.get("album_display_image")),
            "url": app_tags.music_album_url(album),
            "artists": [
                {
                    "id": credited.id,
                    "name": _text(credited.name),
                    "url": app_tags.music_artist_url(credited),
                }
                for credited in credited_artists
            ],
            "musicbrainz_url": metadata.get("musicbrainz_url") or None,
        },
        "activity": _activity(
            context.get("music_album_activity_subtitle"), "progress_text"
        ),
        "tracker": _tracker(context.get("album_tracker")),
        "genres": genres,
        "details": [
            {"label": label, "value": _text(value)}
            for label, value in details
            if value not in (None, "")
        ],
        "release": {"title": _text(selected.get("title"))} if selected else None,
        "tracks": tracks,
        "total_tracks": context.get("total_tracks") or 0,
        "total_runtime": _text(context.get("total_runtime")),
        "release_date": _iso(album.release_date),
        "history_url": _text(context.get("detail_history_url")),
        "sync_url": f"/api/v1/music/albums/{album.id}/resync/",
        "links": _links(context),
    }


def _episodes_page(context, user) -> dict:
    episodes = []
    for episode in context.get("episodes") or []:
        adapter = episode["track_adapter"]
        plays = _plays(episode["music_wrapper"].history.all(), user)
        episodes.append(
            {
                "id": adapter.id,
                "uuid": _text(adapter.episode_uuid),
                "title": _text(episode.get("title")),
                "number": adapter.track_number,
                "published": _iso(episode.get("air_date")),
                "duration": _text(episode.get("runtime")),
                "website_url": episode.get("website_url") or None,
                "play_count": len(plays),
                "plays": plays,
            }
        )
    return {
        "episodes": episodes,
        "total": context.get("total_episodes") or 0,
        "has_more": bool(context.get("has_more")),
        "next_page": context.get("next_page"),
    }


def build_podcast_screen(
    request, source, podcast_uuid, episode_page=1
) -> dict | HttpResponse | None:
    """Return a show page (the first page of episodes) or one page of episodes.

    The feed refresh runs on the first read only, never on an episode page.
    None: no such show. An iTunes id the page would import answers its redirect.
    """
    from app.media_details_views import build_podcast_show_context
    from app.models import PodcastShow

    show = PodcastShow.objects.filter(podcast_uuid=podcast_uuid, source=source).first()
    if show is None:
        if str(podcast_uuid).isdigit():
            return HttpResponseRedirect(
                reverse(
                    "media_details",
                    kwargs={
                        "source": source,
                        "media_type": MediaTypes.PODCAST.value,
                        "media_id": podcast_uuid,
                        "title": "podcast",
                    },
                )
            )
        return None
    context = build_podcast_show_context(
        request,
        show,
        source,
        podcast_uuid,
        public_view=False,
        refresh_feed=episode_page == 1,
        episode_page=episode_page,
    )
    user = request.user
    episodes = _episodes_page(context, user)
    if episode_page > 1:
        return episodes
    media = context["media"]
    details = media.get("details") or {}
    try:
        url = reverse(
            "media_details",
            kwargs={
                "source": source,
                "media_type": MediaTypes.PODCAST.value,
                "media_id": show.podcast_uuid,
                "title": app_tags.slug(show.title or "podcast"),
            },
        )
    except NoReverseMatch:
        url = ""
    return {
        "show": {
            "id": show.id,
            "uuid": show.podcast_uuid,
            "source": source,
            "title": _text(show.title),
            "author": _text(show.author),
            "image": _image(show.image),
            "description": _text(show.description),
            "url": url,
            "website_url": show.website_url or None,
        },
        "activity": _activity(context.get("activity_subtitle"), "primary_text"),
        "tracker": _tracker(context.get("podcast_tracker")),
        "genres": [{"name": _text(name), "url": ""} for name in show.genres or []],
        "details": [
            {"label": label, "value": _text(value)}
            for label, value in (
                ("Author", details.get("author")),
                ("Language", details.get("language")),
            )
            if value
        ],
        "links": _links(context),
        "episodes": episodes,
    }


# --- serializers -------------------------------------------------------------


class MediaTrackerSerializer(serializers.Serializer):
    """Your tracker for an artist, album or show."""

    status = serializers.CharField(allow_null=True)
    score = serializers.FloatField(allow_null=True)


class MediaActivitySerializer(serializers.Serializer):
    """The page's activity subtitle: the line under the title."""

    primary_text = serializers.CharField(allow_blank=True)
    date_start = serializers.CharField(allow_null=True)
    date_end = serializers.CharField(allow_null=True)


class MediaPlaySerializer(serializers.Serializer):
    """One completed play."""

    history_id = serializers.IntegerField(
        help_text="DELETE /api/v1/history/<music|podcast>/<history_id>/ removes it."
    )
    end_date = serializers.CharField(
        help_text="The exact instant, ISO 8601 with offset."
    )


class ArtistRefSerializer(serializers.Serializer):
    """An artist with its web page."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    url = serializers.CharField()


class ArtistInfoSerializer(serializers.Serializer):
    """The artist."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    image = serializers.CharField()
    url = serializers.CharField()
    bio = serializers.CharField(allow_blank=True)
    musicbrainz_url = serializers.CharField(allow_null=True)


class ArtistRatingSerializer(serializers.Serializer):
    """MusicBrainz's rating."""

    rating = serializers.FloatField(allow_null=True)
    rating_count = serializers.IntegerField(allow_null=True)


class ArtistRelationSerializer(serializers.Serializer):
    """A band member, or a band the artist is also in."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    image = serializers.CharField()
    url = serializers.CharField()
    role = serializers.CharField(allow_blank=True)
    is_current = serializers.BooleanField()


class DiscographyAlbumSerializer(serializers.Serializer):
    """A release in the discography."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    image = serializers.CharField()
    release_date = serializers.CharField(allow_null=True)
    release_type = serializers.CharField(allow_blank=True)
    url = serializers.CharField()
    play_count = serializers.IntegerField()
    score = serializers.FloatField(allow_null=True)


class DiscographyGroupSerializer(serializers.Serializer):
    """A discography group (Albums, EPs, Singles, ...)."""

    label = serializers.CharField()
    albums = DiscographyAlbumSerializer(many=True)


class ArtistScreenSerializer(serializers.Serializer):
    """The artist page."""

    artist = ArtistInfoSerializer()
    activity = MediaActivitySerializer(allow_null=True)
    rating = ArtistRatingSerializer()
    tracker = MediaTrackerSerializer(allow_null=True)
    genres = DetailNamedLinkSerializer(many=True)
    details = DetailInfoSerializer(many=True)
    members = ArtistRelationSerializer(many=True)
    member_of = ArtistRelationSerializer(many=True)
    discography = DiscographyGroupSerializer(many=True)
    history_url = serializers.CharField()
    sync_url = serializers.CharField(help_text="POST re-syncs the discography.")
    links = DetailLinkSectionSerializer(many=True)


class AlbumInfoSerializer(serializers.Serializer):
    """The album."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    image = serializers.CharField()
    url = serializers.CharField()
    artists = ArtistRefSerializer(many=True)
    musicbrainz_url = serializers.CharField(allow_null=True)


class AlbumReleaseSerializer(serializers.Serializer):
    """The release the user picked."""

    title = serializers.CharField(allow_blank=True)


class AlbumTrackSerializer(serializers.Serializer):
    """A track with your plays of it."""

    track_id = serializers.IntegerField(allow_null=True)
    recording_id = serializers.CharField(allow_null=True)
    title = serializers.CharField()
    disc = serializers.IntegerField(allow_null=True)
    number = serializers.IntegerField(allow_null=True)
    duration = serializers.CharField(allow_blank=True)
    music_id = serializers.IntegerField(allow_null=True)
    play_count = serializers.IntegerField()
    last_played = serializers.CharField(allow_null=True)
    plays = MediaPlaySerializer(many=True, help_text="Newest first.")


class AlbumScreenSerializer(serializers.Serializer):
    """The album page."""

    album = AlbumInfoSerializer()
    activity = MediaActivitySerializer(allow_null=True)
    tracker = MediaTrackerSerializer(allow_null=True)
    genres = DetailNamedLinkSerializer(many=True)
    details = DetailInfoSerializer(many=True)
    release = AlbumReleaseSerializer(allow_null=True)
    tracks = AlbumTrackSerializer(many=True)
    total_tracks = serializers.IntegerField()
    total_runtime = serializers.CharField(allow_blank=True)
    release_date = serializers.CharField(allow_null=True, help_text="ISO date.")
    history_url = serializers.CharField()
    sync_url = serializers.CharField(help_text="POST re-syncs the album.")
    links = DetailLinkSectionSerializer(many=True)


class PodcastShowInfoSerializer(serializers.Serializer):
    """The show."""

    id = serializers.IntegerField()
    uuid = serializers.CharField()
    source = serializers.CharField()
    title = serializers.CharField()
    author = serializers.CharField(allow_blank=True)
    image = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    url = serializers.CharField()
    website_url = serializers.CharField(allow_null=True)


class PodcastEpisodeSerializer(serializers.Serializer):
    """An episode with your plays of it."""

    id = serializers.IntegerField()
    uuid = serializers.CharField()
    title = serializers.CharField()
    number = serializers.IntegerField(allow_null=True)
    published = serializers.CharField(allow_null=True)
    duration = serializers.CharField(allow_blank=True)
    website_url = serializers.CharField(allow_null=True)
    play_count = serializers.IntegerField()
    plays = MediaPlaySerializer(many=True, help_text="Newest first.")


class PodcastEpisodesPageSerializer(serializers.Serializer):
    """One page (20) of a show's episodes, newest first."""

    episodes = PodcastEpisodeSerializer(many=True)
    total = serializers.IntegerField()
    has_more = serializers.BooleanField()
    next_page = serializers.IntegerField(allow_null=True)


class PodcastScreenSerializer(serializers.Serializer):
    """The podcast show page."""

    show = PodcastShowInfoSerializer()
    activity = MediaActivitySerializer(allow_null=True)
    tracker = MediaTrackerSerializer(allow_null=True)
    genres = DetailNamedLinkSerializer(many=True)
    details = DetailInfoSerializer(many=True)
    links = DetailLinkSectionSerializer(many=True)
    episodes = PodcastEpisodesPageSerializer()
