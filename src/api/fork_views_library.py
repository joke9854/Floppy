"""Library preferences and bulk actions the web had and the API lacked (P1-D).

Metadata languages, Hardcover editions, MusicBrainz releases, tagging many
items, adding many items to the collection, and the custom collection field
schema. The changes themselves live in `app.library_actions` (and
`app.collection_fields`), shared with the web views.
"""

import logging
from http import HTTPStatus as HTTP  # noqa: N814

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from app import library_actions
from app.collection_fields import (
    CollectionFieldNotFoundError,
    CollectionFieldValidationError,
    save_collection_field_schema,
    serialize_collection_field_schema,
)
from app.models import (
    Album,
    HardcoverEditionPreference,
    Item,
    MediaTypes,
    MusicReleasePreference,
    Sources,
    Tag,
)
from app.providers import credentials, hardcover, musicbrainz, tmdb
from app.services.music import sync_album_release_tracks

from .contract_serializers import DetailErrorSerializer
from .provider_errors import PROVIDER_UNAVAILABLE_DETAIL

logger = logging.getLogger(__name__)

# Most item ids one bulk request may carry.
MAX_BULK_ITEMS = 500

_PROVIDER_503 = OpenApiResponse(
    DetailErrorSerializer,
    description=(
        f"{PROVIDER_UNAVAILABLE_DETAIL} Code `provider_unavailable`, with "
        "`Retry-After`."
    ),
)


def _bulk_item_ids(data):
    """Return (unique positive ids, error Response or None) from `item_ids`."""
    raw_ids = data.get("item_ids") if isinstance(data, dict) else None
    if not isinstance(raw_ids, list) or not raw_ids:
        return None, Response(
            {"detail": "item_ids must be a non-empty list of item ids."},
            status=HTTP.BAD_REQUEST,
        )
    if len(raw_ids) > MAX_BULK_ITEMS:
        return None, Response(
            {"detail": f"At most {MAX_BULK_ITEMS} item ids per request."},
            status=HTTP.BAD_REQUEST,
        )
    item_ids = []
    for raw_id in raw_ids:
        try:
            item_id = 0 if isinstance(raw_id, bool) else int(raw_id)
        except (TypeError, ValueError):
            item_id = 0
        if item_id <= 0:
            return None, Response(
                {"detail": "item_ids must hold positive integers."},
                status=HTTP.BAD_REQUEST,
            )
        if item_id not in item_ids:
            item_ids.append(item_id)
    return item_ids, None


# --- /api/v1/metadata/languages/ ---------------------------------------------


class MetadataLanguageSerializer(serializers.Serializer):
    """One metadata language; the empty code is the server default."""

    code = serializers.CharField(allow_blank=True)
    name = serializers.CharField()


class MetadataLanguagesView(drf_views.APIView):
    """Languages a title's metadata can be shown in (TMDB's list)."""

    @extend_schema(
        operation_id="listMetadataLanguages",
        responses={200: MetadataLanguageSerializer(many=True), 503: _PROVIDER_503},
    )
    def get(self, request):
        """Return the language codes `provider-preference` accepts."""
        with credentials.current_user_scope(request.user):
            languages = tmdb.metadata_languages()
        return Response(
            [{"code": code, "name": name} for code, name in languages],
            status=HTTP.OK,
        )


# --- /api/v1/media/book/hardcover/{media_id}/edition/ ------------------------


class HardcoverEditionSerializer(serializers.Serializer):
    """One Hardcover edition of a book."""

    id = serializers.CharField()
    title = serializers.CharField(allow_null=True)
    image = serializers.CharField(allow_null=True)
    format = serializers.CharField(allow_null=True)
    language = serializers.CharField(allow_null=True)
    publisher = serializers.CharField(allow_null=True)
    release_date = serializers.CharField(allow_null=True)


class HardcoverEditionsResponseSerializer(serializers.Serializer):
    """The user's chosen edition and the book's editions."""

    edition_id = serializers.CharField(allow_null=True)
    editions = HardcoverEditionSerializer(many=True)


class EditionRequestSerializer(serializers.Serializer):
    """The edition to use."""

    edition_id = serializers.CharField()


class EditionResultSerializer(serializers.Serializer):
    """The edition now in use."""

    edition_id = serializers.CharField()


class HardcoverEditionView(drf_views.APIView):
    """Pick which Hardcover edition of a tracked book to show (#539)."""

    @staticmethod
    def _item(media_id):
        return Item.objects.filter(
            media_id=media_id,
            source=Sources.HARDCOVER.value,
            media_type=MediaTypes.BOOK.value,
        ).first()

    @extend_schema(
        operation_id="listHardcoverEditions",
        responses={
            200: HardcoverEditionsResponseSerializer,
            404: DetailErrorSerializer,
            503: _PROVIDER_503,
        },
    )
    def get(self, request, media_id):
        """Return the book's editions and the one this user picked."""
        item = self._item(media_id)
        if item is None:
            return Response({"detail": "Book not found."}, status=HTTP.NOT_FOUND)
        with credentials.current_user_scope(request.user):
            editions = hardcover.editions(media_id, user=request.user)
        preference = HardcoverEditionPreference.objects.filter(
            user=request.user,
            item=item,
        ).first()
        return Response(
            {
                "edition_id": preference.edition_id if preference else None,
                "editions": [
                    {
                        key: (
                            str(edition.get(key))
                            if edition.get(key) is not None
                            else None
                        )
                        for key in (
                            "id",
                            "title",
                            "image",
                            "format",
                            "language",
                            "publisher",
                            "release_date",
                        )
                    }
                    for edition in editions
                ],
            },
            status=HTTP.OK,
        )

    @extend_schema(
        operation_id="setHardcoverEdition",
        request=EditionRequestSerializer,
        responses={
            200: EditionResultSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def put(self, request, media_id):
        """Use this edition of the book for this user."""
        item = self._item(media_id)
        if item is None:
            return Response({"detail": "Book not found."}, status=HTTP.NOT_FOUND)
        edition_id = str(request.data.get("edition_id") or "").strip()
        if not edition_id:
            return Response(
                {"detail": "edition_id is required."},
                status=HTTP.BAD_REQUEST,
            )
        library_actions.set_hardcover_edition(request.user, item, edition_id)
        return Response({"edition_id": edition_id}, status=HTTP.OK)


# --- /api/v1/music/albums/{album_id}/release/ --------------------------------


class MusicReleaseSerializer(serializers.Serializer):
    """One MusicBrainz release (pressing) of an album."""

    release_id = serializers.CharField()
    title = serializers.CharField()
    release_date = serializers.CharField(allow_blank=True)
    country = serializers.CharField(allow_blank=True)
    status = serializers.CharField(allow_blank=True)
    formats = serializers.ListField(child=serializers.CharField())
    labels = serializers.ListField(child=serializers.CharField())
    catalog_numbers = serializers.ListField(child=serializers.CharField())
    barcode = serializers.CharField(allow_blank=True)
    track_count = serializers.IntegerField()


class MusicReleasesResponseSerializer(serializers.Serializer):
    """The user's chosen release and the album's releases."""

    release_id = serializers.CharField(allow_null=True)
    releases = MusicReleaseSerializer(many=True)


class MusicReleaseRequestSerializer(serializers.Serializer):
    """The release to use."""

    release_id = serializers.CharField()


class MusicReleaseResultSerializer(serializers.Serializer):
    """The release now in use and whether its tracklist was refreshed."""

    release_id = serializers.CharField()
    tracks_synced = serializers.BooleanField(
        help_text="False when MusicBrainz could not return the tracklist; retry later.",
    )
    track_count = serializers.IntegerField(allow_null=True)


class MusicReleaseView(drf_views.APIView):
    """Pick which MusicBrainz release of an album to use.

    Choosing a release also rebuilds the album's tracklist from it, which every
    user of this server shares.
    """

    @extend_schema(
        operation_id="listMusicReleases",
        responses={
            200: MusicReleasesResponseSerializer,
            404: DetailErrorSerializer,
            503: _PROVIDER_503,
        },
    )
    def get(self, request, album_id):
        """Return the album's releases and the one this user picked."""
        album = Album.objects.filter(id=album_id).first()
        if album is None:
            return Response({"detail": "Album not found."}, status=HTTP.NOT_FOUND)
        releases = (
            musicbrainz.get_release_group_releases(album.musicbrainz_release_group_id)
            if album.musicbrainz_release_group_id
            else []
        )
        preference = MusicReleasePreference.objects.filter(
            user=request.user,
            album=album,
        ).first()
        return Response(
            {
                "release_id": preference.release_id if preference else None,
                "releases": [
                    {
                        "release_id": release["release_id"],
                        "title": release.get("title") or "",
                        "release_date": release.get("release_date") or "",
                        "country": release.get("country") or "",
                        "status": release.get("status") or "",
                        "formats": list(release.get("formats") or []),
                        "labels": list(release.get("labels") or []),
                        "catalog_numbers": list(release.get("catalog_numbers") or []),
                        "barcode": release.get("barcode") or "",
                        "track_count": release.get("track_count") or 0,
                    }
                    for release in releases
                ],
            },
            status=HTTP.OK,
        )

    @extend_schema(
        operation_id="setMusicRelease",
        request=MusicReleaseRequestSerializer,
        responses={
            200: MusicReleaseResultSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
            503: _PROVIDER_503,
        },
    )
    def put(self, request, album_id):
        """Use this release for this user and rebuild the album's tracklist."""
        album = Album.objects.filter(id=album_id).first()
        if album is None:
            return Response({"detail": "Album not found."}, status=HTTP.NOT_FOUND)
        release_id = str(request.data.get("release_id") or "").strip()
        if not release_id:
            return Response(
                {"detail": "release_id is required."},
                status=HTTP.BAD_REQUEST,
            )
        if not album.musicbrainz_release_group_id:
            return Response(
                {"detail": "This album has no MusicBrainz release group."},
                status=HTTP.BAD_REQUEST,
            )
        releases = musicbrainz.get_release_group_releases(
            album.musicbrainz_release_group_id,
        )
        if not any(release.get("release_id") == release_id for release in releases):
            return Response(
                {"detail": "That release is not part of this album."},
                status=HTTP.BAD_REQUEST,
            )
        MusicReleasePreference.objects.update_or_create(
            user=request.user,
            album=album,
            defaults={"release_id": release_id},
        )
        try:
            track_count = sync_album_release_tracks(album, release_id)
        except Exception as error:
            logger.warning(
                "Release %s saved for album %s, tracklist not refreshed: %s",
                release_id,
                album.id,
                type(error).__name__,
            )
            return Response(
                {"release_id": release_id, "tracks_synced": False, "track_count": None},
                status=HTTP.OK,
            )
        return Response(
            {"release_id": release_id, "tracks_synced": True, "track_count": track_count},
            status=HTTP.OK,
        )


# --- /api/v1/tags/{tag_id}/items/ --------------------------------------------


class TagItemsRequestSerializer(serializers.Serializer):
    """Items to tag or untag."""

    action = serializers.ChoiceField(choices=["add", "remove"])
    item_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        max_length=MAX_BULK_ITEMS,
    )


class TagItemsResultSerializer(serializers.Serializer):
    """What was tagged or untagged."""

    action = serializers.CharField()
    item_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="The ids acted on; unknown item ids are left out.",
    )


class TagItemsView(drf_views.APIView):
    """Add or remove one of the user's tags on many items at once."""

    @extend_schema(
        operation_id="bulkTagItems",
        request=TagItemsRequestSerializer,
        responses={
            200: TagItemsResultSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def post(self, request, tag_id):
        """Tag (`add`) or untag (`remove`) the items."""
        tag = Tag.objects.filter(id=tag_id, user=request.user).first()
        if tag is None:
            return Response({"detail": "Tag not found."}, status=HTTP.NOT_FOUND)
        action = request.data.get("action") if isinstance(request.data, dict) else None
        if action not in {"add", "remove"}:
            return Response(
                {"detail": "action must be 'add' or 'remove'."},
                status=HTTP.BAD_REQUEST,
            )
        item_ids, error = _bulk_item_ids(request.data)
        if error is not None:
            return error
        used_ids = library_actions.toggle_tag(request.user, tag, action, item_ids)
        return Response({"action": action, "item_ids": used_ids}, status=HTTP.OK)


# --- /api/v1/collection/bulk/ ------------------------------------------------


class CollectionBulkRequestSerializer(serializers.Serializer):
    """Items to add to the collection."""

    item_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        max_length=MAX_BULK_ITEMS,
    )


class CollectionBulkResultSerializer(serializers.Serializer):
    """Counts of collection entries."""

    created = serializers.IntegerField()
    already_present = serializers.IntegerField()
    skipped_ids = serializers.ListField(
        child=serializers.IntegerField(),
        help_text=(
            "Unknown items, and shows or seasons whose episodes could not be "
            "listed."
        ),
    )


class CollectionBulkAddView(drf_views.APIView):
    """Add many items to the collection; shows and seasons add their episodes."""

    @extend_schema(
        operation_id="bulkAddToCollection",
        request=CollectionBulkRequestSerializer,
        responses={200: CollectionBulkResultSerializer, 400: DetailErrorSerializer},
    )
    def post(self, request):
        """Create the missing collection entries."""
        item_ids, error = _bulk_item_ids(request.data)
        if error is not None:
            return error
        result = library_actions.add_items_to_collection(request.user, item_ids)
        return Response(result, status=HTTP.OK)


# --- /api/v1/collection/fields/ ----------------------------------------------


class CollectionFieldProvenanceSerializer(serializers.Serializer):
    """An import that writes to this field."""

    source = serializers.CharField()
    source_label = serializers.CharField()
    created_field = serializers.BooleanField()
    import_run_id = serializers.IntegerField(allow_null=True)


class CollectionFieldSerializer(serializers.Serializer):
    """One custom collection field."""

    id = serializers.IntegerField(allow_null=True)
    label = serializers.CharField()
    field_type = serializers.CharField()
    options = serializers.ListField(child=serializers.CharField())
    media_types = serializers.ListField(child=serializers.CharField())
    provenance = CollectionFieldProvenanceSerializer(many=True, read_only=True)


class CollectionFieldGroupSerializer(serializers.Serializer):
    """A named group of custom collection fields."""

    id = serializers.IntegerField(allow_null=True)
    name = serializers.CharField()
    fields = CollectionFieldSerializer(many=True)


class CollectionFieldSchemaSerializer(serializers.Serializer):
    """The user's whole custom field schema."""

    groups = CollectionFieldGroupSerializer(many=True)


class CollectionFieldSchemaRequestSerializer(CollectionFieldSchemaSerializer):
    """The whole schema to keep."""

    known_field_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text=(
            "Field ids the client knew about. When sent, only those can be "
            "deleted, so fields an import added meanwhile survive."
        ),
    )


class CollectionFieldsView(drf_views.APIView):
    """The custom fields shown on collection entries."""

    @extend_schema(
        operation_id="getCollectionFields",
        responses={200: CollectionFieldSchemaSerializer},
    )
    def get(self, request):
        """Return the groups and fields, in display order."""
        return Response(
            {"groups": serialize_collection_field_schema(request.user)},
            status=HTTP.OK,
        )

    @extend_schema(
        operation_id="saveCollectionFields",
        request=CollectionFieldSchemaRequestSerializer,
        responses={
            200: CollectionFieldSchemaSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
        description=(
            "Replace the whole schema. Groups and fields with an id are "
            "updated, those without one are created, and the user's groups and "
            "fields missing from the payload are deleted "
            "(limited to `known_field_ids` when it is sent)."
        ),
    )
    def put(self, request):
        """Save the schema and return it as stored."""
        try:
            save_collection_field_schema(request.user, request.data)
        except CollectionFieldValidationError as error:
            return Response({"detail": str(error)}, status=HTTP.BAD_REQUEST)
        except CollectionFieldNotFoundError as error:
            return Response({"detail": str(error)}, status=HTTP.NOT_FOUND)
        return Response(
            {"groups": serialize_collection_field_schema(request.user)},
            status=HTTP.OK,
        )
