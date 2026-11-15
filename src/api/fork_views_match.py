"""Match review: fix titles an integration matched wrongly (P1-H).

The web's match review on the Integrations page. A correction moves one
user's tracking of a movie or show to the right TMDB title and makes future
imports from that source use it. Preview first: the preview's `token` must
come back with the apply, and an apply against changed data is refused
(409) so nothing moves on a stale preview.
"""

from http import HTTPStatus as HTTP  # noqa: N814

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from app.models import TV, Item, MediaTypes, Movie, Sources
from app.providers import credentials, services
from integrations.match_corrections import (
    InvalidMatchCorrectionError,
    MissingEpisodeMappingError,
    StaleCorrectionPreviewError,
    apply_match_correction,
    preview_match_correction,
)
from integrations.models import ExternalReference, ExternalReferenceReviewStatus

from .contract_serializers import DetailErrorSerializer
from .provider_errors import PROVIDER_UNAVAILABLE_DETAIL, resolution_failure_response

REFERENCE_LIMIT = 100
CORRECTABLE_TYPES = (MediaTypes.MOVIE.value, MediaTypes.TV.value)


class MatchItemSerializer(serializers.Serializer):
    """A Floppy title."""

    id = serializers.IntegerField()
    media_type = serializers.CharField()
    source = serializers.CharField()
    media_id = serializers.CharField()
    title = serializers.CharField()


class MatchReferenceSerializer(serializers.Serializer):
    """How one external identity was matched."""

    id = serializers.IntegerField()
    integration = serializers.CharField()
    source_account = serializers.CharField(allow_blank=True)
    external_namespace = serializers.CharField()
    external_identity = serializers.CharField()
    media_type = serializers.CharField()
    review_status = serializers.CharField()
    matched_item = MatchItemSerializer(allow_null=True)
    corrected_item = MatchItemSerializer(allow_null=True)
    decision_note = serializers.CharField(allow_blank=True)
    updated_at = serializers.DateTimeField()


class MatchReferenceListSerializer(serializers.Serializer):
    """Matches waiting for review, and decisions already saved."""

    needs_review = MatchReferenceSerializer(many=True)
    saved = MatchReferenceSerializer(many=True)


class MatchDecisionRequestSerializer(serializers.Serializer):
    """What to do with a reference."""

    decision = serializers.ChoiceField(
        choices=["ignore", "remove_correction"],
        help_text=(
            "`ignore`: future imports skip this identity. `remove_correction`: "
            "drop a saved correction or ignore, back to the automatic match."
        ),
    )


class MatchPreviewRequestSerializer(serializers.Serializer):
    """The TMDB title to move to."""

    destination_media_id = serializers.CharField(help_text="TMDB id, same media type.")
    episode_mapping = serializers.DictField(
        required=False,
        help_text="For shows: source `season:episode` -> {season, episode}.",
    )


class MatchPreviewSerializer(serializers.Serializer):
    """What the correction would move."""

    token = serializers.CharField(help_text="Send back with the apply.")
    destination_item_id = serializers.IntegerField()
    counts = serializers.DictField(child=serializers.IntegerField())
    episodes = serializers.ListField(child=serializers.DictField())
    required_episode_keys = serializers.ListField(child=serializers.CharField())
    episode_mapping = serializers.DictField()
    scalar_conflicts = serializers.DictField(
        help_text="Fields set differently on both sides; pick one per field.",
    )


class MatchApplyRequestSerializer(serializers.Serializer):
    """The previewed correction."""

    destination_item_id = serializers.IntegerField()
    token = serializers.CharField()
    episode_mapping = serializers.DictField(required=False)
    decisions = serializers.DictField(
        child=serializers.CharField(),
        required=False,
        help_text="Per conflicting field: `source` or `destination`.",
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


def _item_payload(item):
    if item is None:
        return None
    return {
        "id": item.id,
        "media_type": item.media_type,
        "source": item.source,
        "media_id": str(item.media_id),
        "title": item.title or "",
    }


def _reference_payload(reference):
    return {
        "id": reference.id,
        "integration": reference.integration,
        "source_account": reference.source_account,
        "external_namespace": reference.external_namespace,
        "external_identity": reference.external_identity,
        "media_type": reference.media_type,
        "review_status": reference.review_status,
        "matched_item": _item_payload(reference.matched_item),
        "corrected_item": _item_payload(reference.corrected_item),
        "decision_note": reference.decision_note,
        "updated_at": reference.updated_at,
    }


def _references(user, statuses):
    return [
        _reference_payload(reference)
        for reference in ExternalReference.objects.filter(
            user=user,
            review_status__in=statuses,
        )
        .select_related("matched_item", "corrected_item")
        .order_by("-updated_at")[:REFERENCE_LIMIT]
    ]


class MatchReferencesView(drf_views.APIView):
    """Matches to review and saved decisions."""

    @extend_schema(
        operation_id="listMatchReferences",
        responses={200: MatchReferenceListSerializer},
    )
    def get(self, request):
        """Return up to 100 of each, most recent first."""
        return Response(
            {
                "needs_review": _references(
                    request.user,
                    (ExternalReferenceReviewStatus.NEEDS_REVIEW.value,),
                ),
                "saved": _references(
                    request.user,
                    (
                        ExternalReferenceReviewStatus.CORRECTED.value,
                        ExternalReferenceReviewStatus.IGNORED.value,
                    ),
                ),
            },
            status=HTTP.OK,
        )


class MatchReferenceDecisionView(drf_views.APIView):
    """Ignore an identity, or remove a saved decision."""

    @extend_schema(
        operation_id="decideMatchReference",
        request=MatchDecisionRequestSerializer,
        responses={
            200: MatchReferenceSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def post(self, request, reference_id):
        """Save the decision and return the reference."""
        reference = (
            ExternalReference.objects.select_related("matched_item", "corrected_item")
            .filter(pk=reference_id, user=request.user)
            .first()
        )
        if reference is None:
            return Response({"detail": "Reference not found."}, status=HTTP.NOT_FOUND)
        decision = (request.data or {}).get("decision")
        if decision == "ignore":
            reference.review_status = ExternalReferenceReviewStatus.IGNORED.value
            reference.save(update_fields=["review_status", "updated_at"])
        elif decision == "remove_correction":
            reference.review_status = ExternalReferenceReviewStatus.RESOLVED.value
            reference.corrected_item = None
            reference.episode_mapping = {}
            reference.decision_note = ""
            reference.save(
                update_fields=[
                    "review_status",
                    "corrected_item",
                    "episode_mapping",
                    "decision_note",
                    "updated_at",
                ],
            )
        else:
            return Response(
                {"detail": "decision must be 'ignore' or 'remove_correction'."},
                status=HTTP.BAD_REQUEST,
            )
        return Response(_reference_payload(reference), status=HTTP.OK)


def _tracked_source(user, item_id):
    """Return the movie or show item this user tracks, or None."""
    item = Item.objects.filter(pk=item_id, media_type__in=CORRECTABLE_TYPES).first()
    if item is None:
        return None
    model = Movie if item.media_type == MediaTypes.MOVIE.value else TV
    return item if model.objects.filter(user=user, item=item).exists() else None


def _reference_ids(user, source_item):
    """Return this user's references the correction affects (title and episodes)."""
    from django.db.models import Q

    item_ids = [source_item.pk]
    if source_item.media_type == MediaTypes.TV.value:
        item_ids.extend(
            Item.objects.filter(
                media_id=source_item.media_id,
                source=source_item.source,
                media_type=MediaTypes.EPISODE.value,
            ).values_list("pk", flat=True),
        )
    return list(
        ExternalReference.objects.filter(user=user)
        .filter(Q(matched_item_id__in=item_ids) | Q(corrected_item_id__in=item_ids))
        .values_list("id", flat=True),
    )


def _destination(user, media_type, media_id):
    """Fetch the TMDB title and return its Item, creating it if needed."""
    with credentials.current_user_scope(user):
        metadata = services.get_media_metadata(media_type, media_id, Sources.TMDB.value)
    destination, _created = Item.objects.get_or_create(
        media_id=str(media_id),
        source=Sources.TMDB.value,
        media_type=media_type,
        defaults={
            "title": metadata.get("title") or "",
            "original_title": metadata.get("original_title"),
            "localized_title": metadata.get("localized_title"),
            "image": metadata.get("image") or "",
        },
    )
    return destination


_SOURCE_NOT_FOUND = {"detail": "This movie or show is not tracked."}


class MatchFixPreviewView(drf_views.APIView):
    """Preview moving one tracked title to another TMDB title."""

    @extend_schema(
        operation_id="previewMatchFix",
        request=MatchPreviewRequestSerializer,
        responses={
            200: MatchPreviewSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
            503: OpenApiResponse(
                DetailErrorSerializer,
                description=f"{PROVIDER_UNAVAILABLE_DETAIL} Code `provider_unavailable`.",
            ),
        },
    )
    def post(self, request, item_id):
        """Return the preview and its token; nothing moves yet."""
        source_item = _tracked_source(request.user, item_id)
        if source_item is None:
            return Response(_SOURCE_NOT_FOUND, status=HTTP.NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else {}
        media_id = str(data.get("destination_media_id") or "").strip()
        mapping = data.get("episode_mapping") or None
        if not media_id or (mapping is not None and not isinstance(mapping, dict)):
            return Response(
                {
                    "detail": (
                        "destination_media_id is required; episode_mapping must be "
                        "an object."
                    ),
                },
                status=HTTP.BAD_REQUEST,
            )
        try:
            destination = _destination(request.user, source_item.media_type, media_id)
        except services.ProviderAPIError as error:
            return resolution_failure_response(error, "TMDB has no such title.")
        try:
            preview = preview_match_correction(
                request.user,
                source_item,
                destination,
                episode_mapping=mapping,
            )
        except InvalidMatchCorrectionError as error:
            return Response({"detail": str(error)}, status=HTTP.BAD_REQUEST)
        return Response(
            {
                "token": preview["token"],
                "destination_item_id": destination.pk,
                "counts": preview["counts"],
                "episodes": preview["episodes"],
                "required_episode_keys": preview["required_episode_keys"],
                "episode_mapping": preview["episode_mapping"],
                "scalar_conflicts": preview["scalar_conflicts"],
            },
            status=HTTP.OK,
        )


class MatchFixApplyView(drf_views.APIView):
    """Apply a previewed correction."""

    @extend_schema(
        operation_id="applyMatchFix",
        request=MatchApplyRequestSerializer,
        responses={
            200: MatchItemSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
            409: OpenApiResponse(
                DetailErrorSerializer,
                description="The preview is out of date; preview again.",
            ),
        },
    )
    def post(self, request, item_id):
        """Move the tracking and return the title it now lives on."""
        source_item = _tracked_source(request.user, item_id)
        if source_item is None:
            return Response(_SOURCE_NOT_FOUND, status=HTTP.NOT_FOUND)
        data = request.data if isinstance(request.data, dict) else {}
        destination_id = data.get("destination_item_id")
        token = data.get("token")
        mapping = data.get("episode_mapping") or None
        decisions = data.get("decisions") or {}
        note = data.get("note") or ""
        if (
            isinstance(destination_id, bool)
            or not isinstance(destination_id, int)
            or not isinstance(token, str)
            or (mapping is not None and not isinstance(mapping, dict))
            or not isinstance(decisions, dict)
            or not isinstance(note, str)
        ):
            return Response(
                {"detail": "destination_item_id and token from the preview are required."},
                status=HTTP.BAD_REQUEST,
            )
        if not Item.objects.filter(pk=destination_id).exists():
            return Response(
                {"detail": "Destination not found."}, status=HTTP.NOT_FOUND
            )
        try:
            destination_item = apply_match_correction(
                request.user,
                source_item.pk,
                destination_id,
                token,
                episode_mapping=mapping,
                decisions={key: str(value) for key, value in decisions.items()},
                reference_ids=_reference_ids(request.user, source_item),
                note=note[:500],
            )
        except StaleCorrectionPreviewError as error:
            return Response(
                {"detail": str(error), "code": "conflict"}, status=HTTP.CONFLICT
            )
        except (InvalidMatchCorrectionError, MissingEpisodeMappingError) as error:
            return Response({"detail": str(error)}, status=HTTP.BAD_REQUEST)
        return Response(_item_payload(destination_item), status=HTTP.OK)
