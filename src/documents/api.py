"""
Slim API: documents, tags, search, upload and users.

Everything else paperless-ngx offered (workflows, mail, share links, custom
fields, saved views, ...) is intentionally not exposed any more.
"""

import mimetypes
import os
import tempfile
from pathlib import Path
from unicodedata import normalize

import pathvalidate
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login
from django.contrib.auth import logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count
from django.db.models import Q
from django.http import FileResponse
from django.http import Http404
from django.middleware.csrf import get_token
from rest_framework import serializers
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.decorators import authentication_classes
from rest_framework.decorators import parser_classes
from rest_framework.decorators import permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAdminUser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from documents.data_models import ConsumableDocument
from documents.data_models import DocumentMetadataOverrides
from documents.data_models import DocumentSource
from documents.models import Correspondent
from documents.models import Document
from documents.models import DocumentType
from documents.models import Tag
from documents.models import UiSettings
from documents.search import SearchMode
from documents.search import SearchQueryError
from documents.search import get_backend
from documents.search import search_query_error_messages
from documents.tasks import consume_file
from documents.tasks import empty_trash
from paperless.models import ApplicationConfiguration


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def visible_documents(user):
    qs = Document.objects.all()
    if user.is_superuser:
        return qs
    return qs.filter(Q(owner=user) | Q(owner__isnull=True))


def visible_named(model, user):
    qs = model.objects.all()
    if user.is_superuser:
        return qs
    return qs.filter(Q(owner=user) | Q(owner__isnull=True))


def visible_tags(user):
    return visible_named(Tag, user)


class Pagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 200


class CsrfSession(SessionAuthentication):
    """Session auth with CSRF enforcement (the SPA sends X-CSRFToken)."""


# --------------------------------------------------------------------------- #
# serializers
# --------------------------------------------------------------------------- #
class TagSerializer(serializers.ModelSerializer):
    document_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Tag
        fields = (
            "id",
            "name",
            "color",
            "match",
            "matching_algorithm",
            "is_insensitive",
            "is_inbox_tag",
            "document_count",
        )

    def validate_name(self, value):
        qs = Tag.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Tag existiert bereits.")
        return value


class _MatchSerializer(serializers.ModelSerializer):
    document_count = serializers.IntegerField(read_only=True)

    def validate_name(self, value):
        qs = self.Meta.model.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Name existiert bereits.")
        return value


_MATCH_FIELDS = (
    "id",
    "name",
    "match",
    "matching_algorithm",
    "is_insensitive",
    "document_count",
)


class CorrespondentSerializer(_MatchSerializer):
    class Meta:
        model = Correspondent
        fields = _MATCH_FIELDS


class DocumentTypeSerializer(_MatchSerializer):
    class Meta:
        model = DocumentType
        fields = _MATCH_FIELDS


class DocumentSerializer(serializers.ModelSerializer):
    tags = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all(),
        required=False,
    )
    correspondent = serializers.PrimaryKeyRelatedField(
        queryset=Correspondent.objects.all(),
        allow_null=True,
        required=False,
    )
    document_type = serializers.PrimaryKeyRelatedField(
        queryset=DocumentType.objects.all(),
        allow_null=True,
        required=False,
    )
    has_archive = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = (
            "id",
            "title",
            "created",
            "added",
            "modified",
            "mime_type",
            "page_count",
            "original_filename",
            "correspondent",
            "document_type",
            "tags",
            "has_archive",
        )
        read_only_fields = (
            "id",
            "added",
            "modified",
            "mime_type",
            "page_count",
            "original_filename",
        )

    def get_has_archive(self, obj) -> bool:
        return obj.has_archive_version


class DocumentDetailSerializer(DocumentSerializer):
    class Meta(DocumentSerializer.Meta):
        fields = (*DocumentSerializer.Meta.fields, "content")
        read_only_fields = (*DocumentSerializer.Meta.read_only_fields, "content")


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)

    class Meta:
        model = User
        fields = ("id", "username", "is_superuser", "password")

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError({"password": "Passwort erforderlich."})
        user = User(**validated_data)
        user.is_staff = user.is_superuser
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.is_staff = instance.is_superuser
        if password:
            instance.set_password(password)
        instance.save()
        return instance


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #
def _me(user) -> dict:
    return {"id": user.id, "username": user.username, "is_admin": user.is_superuser}


@api_view(["GET"])
@authentication_classes([SessionAuthentication])
@permission_classes([AllowAny])
def session_view(request):
    """State for the SPA bootstrap: who am I, and does an account exist yet."""
    token = get_token(request)
    user = request.user
    return Response(
        {
            "csrf": token,
            "needs_setup": not User.objects.exists(),
            "user": _me(user) if user.is_authenticated else None,
        },
    )


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def login_view(request):
    user = authenticate(
        request,
        username=request.data.get("username", ""),
        password=request.data.get("password", ""),
    )
    if user is None or not user.is_active:
        return Response(
            {"detail": "Benutzername oder Passwort falsch."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return Response({"user": _me(user), "csrf": get_token(request)})


@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def setup_view(request):
    """Create the first admin account. Only works while no user exists."""
    with transaction.atomic():
        if User.objects.select_for_update().exists():
            return Response(
                {"detail": "Einrichtung bereits abgeschlossen."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = UserSerializer(
            data={
                "username": request.data.get("username", ""),
                "password": request.data.get("password", ""),
                "is_superuser": True,
            },
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return Response({"user": _me(user), "csrf": get_token(request)})


@api_view(["POST"])
def logout_view(request):
    logout(request)
    return Response({"ok": True})


class UserViewSet(ModelViewSet):
    queryset = User.objects.all().order_by("username")
    serializer_class = UserSerializer
    permission_classes = (IsAdminUser,)

    def perform_destroy(self, instance):
        if instance.pk == self.request.user.pk:
            raise serializers.ValidationError("Du kannst dich nicht selbst löschen.")
        instance.delete()


# --------------------------------------------------------------------------- #
# tags
# --------------------------------------------------------------------------- #
class TagViewSet(ModelViewSet):
    serializer_class = TagSerializer
    permission_classes = (IsAuthenticated,)
    pagination_class = None

    def get_queryset(self):
        docs = visible_documents(self.request.user)
        counts = dict(
            Document.tags.through.objects.filter(document__in=docs)
            .values_list("tag_id")
            .annotate(c=Count("document_id"))
            .values_list("tag_id", "c"),
        )
        qs = visible_tags(self.request.user).order_by("name")
        tags = list(qs)
        for t in tags:
            t.document_count = counts.get(t.pk, 0)
        return tags

    def get_object(self):
        obj = visible_tags(self.request.user).filter(pk=self.kwargs["pk"]).first()
        if obj is None:
            raise Http404
        obj.document_count = 0
        return obj


class _NamedViewSet(ModelViewSet):
    """Correspondents and document types: same shape, one foreign key each."""

    permission_classes = (IsAuthenticated,)
    pagination_class = None
    model = None
    doc_field = ""

    def get_queryset(self):
        counts = dict(
            visible_documents(self.request.user)
            .exclude(**{f"{self.doc_field}__isnull": True})
            .order_by()
            .values_list(self.doc_field)
            .annotate(c=Count("pk"))
            .values_list(self.doc_field, "c"),
        )
        items = list(visible_named(self.model, self.request.user).order_by("name"))
        for i in items:
            i.document_count = counts.get(i.pk, 0)
        return items

    def get_object(self):
        obj = visible_named(self.model, self.request.user).filter(pk=self.kwargs["pk"]).first()
        if obj is None:
            raise Http404
        obj.document_count = 0
        return obj


class CorrespondentViewSet(_NamedViewSet):
    serializer_class = CorrespondentSerializer
    model = Correspondent
    doc_field = "correspondent_id"


class DocumentTypeViewSet(_NamedViewSet):
    serializer_class = DocumentTypeSerializer
    model = DocumentType
    doc_field = "document_type_id"


# --------------------------------------------------------------------------- #
# documents
# --------------------------------------------------------------------------- #
class DocumentViewSet(ModelViewSet):
    permission_classes = (IsAuthenticated,)
    pagination_class = Pagination
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        return DocumentDetailSerializer if self.action == "retrieve" else DocumentSerializer

    def get_queryset(self):
        qs = visible_documents(self.request.user).prefetch_related("tags")
        params = self.request.query_params

        tag_ids = [int(t) for t in params.get("tags", "").split(",") if t.strip().isdigit()]
        for tag_id in tag_ids:
            qs = qs.filter(tags__id=tag_id)
        if params.get("untagged") in ("1", "true"):
            qs = qs.filter(tags__isnull=True)
        if params.get("correspondent", "").isdigit():
            qs = qs.filter(correspondent_id=int(params["correspondent"]))
        if params.get("document_type", "").isdigit():
            qs = qs.filter(document_type_id=int(params["document_type"]))

        query = params.get("query", "").strip()
        if query:
            try:
                user = None if self.request.user.is_superuser else self.request.user
                ids = get_backend().search_ids(
                    query,
                    user=user,
                    search_mode=SearchMode.TEXT,
                )
            except SearchQueryError as e:
                raise serializers.ValidationError(
                    {"query": search_query_error_messages(e)},
                ) from e
            order = {pk: i for i, pk in enumerate(ids)}
            qs = qs.filter(pk__in=ids)
            # relevance order unless the client asked for something else
            if not params.get("ordering"):
                self._relevance = order

        ordering = params.get("ordering") or "-created"
        allowed = {"created", "-created", "added", "-added", "title", "-title"}
        if ordering in allowed:
            qs = qs.order_by(ordering, "-id")
        return qs.distinct()

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        order = getattr(self, "_relevance", None)
        if order and isinstance(response.data, dict):
            response.data["results"].sort(key=lambda d: order.get(d["id"], 1 << 30))
        return response

    def perform_update(self, serializer):
        serializer.save()
        # keep the search index in sync with edited title/tags
        get_backend().add_or_update(serializer.instance)

    def perform_destroy(self, instance):
        pk = instance.pk
        instance.delete()
        get_backend().remove(pk)


def _get_doc(request, pk) -> Document:
    if request.query_params.get("trash") in ("1", "true"):
        doc = trash_documents(request.user).filter(pk=pk).first()
    else:
        doc = visible_documents(request.user).filter(pk=pk).first()
    if doc is None:
        raise Http404
    return doc


@api_view(["GET"])
def document_file(request, pk, kind):
    """kind: download | preview | thumb"""
    doc = _get_doc(request, pk)
    if kind == "thumb":
        path, ctype = doc.thumbnail_path, "image/webp"
    else:
        original = request.query_params.get("original") in ("1", "true")
        if doc.has_archive_version and not original:
            path, ctype = doc.archive_path, "application/pdf"
        else:
            path, ctype = doc.source_path, doc.mime_type
    if not path or not Path(path).exists():
        raise Http404
    ctype = ctype or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    name = doc.get_public_filename(archive=bool(path == doc.archive_path))
    resp = FileResponse(open(path, "rb"), content_type=ctype)
    disposition = "attachment" if kind == "download" else "inline"
    resp["Content-Disposition"] = f'{disposition}; filename="{name}"'
    return resp


@api_view(["POST"])
@parser_classes([MultiPartParser])
def upload_view(request):
    files = request.FILES.getlist("files") or request.FILES.getlist("document")
    if not files:
        return Response({"detail": "Keine Datei übermittelt."}, status=400)

    tag_ids = [int(t) for t in request.data.getlist("tags") if str(t).isdigit()]
    corr = request.data.get("correspondent")
    dtype = request.data.get("document_type")
    corr_id = int(corr) if corr and str(corr).isdigit() else None
    dtype_id = int(dtype) if dtype and str(dtype).isdigit() else None
    task_ids = []
    settings.SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    for f in files:
        name = normalize("NFC", f.name)
        tmp_dir = Path(tempfile.mkdtemp(dir=settings.SCRATCH_DIR))
        target = tmp_dir / pathvalidate.sanitize_filename(name)
        with open(target, "wb") as out:
            for chunk in f.chunks():
                out.write(chunk)
        os.utime(target, None)
        result = consume_file.apply_async(
            kwargs={
                "input_doc": ConsumableDocument(
                    source=DocumentSource.WebUI,
                    original_file=target,
                ),
                "overrides": DocumentMetadataOverrides(
                    filename=name,
                    tag_ids=tag_ids or None,
                    correspondent_id=corr_id,
                    document_type_id=dtype_id,
                    owner_id=request.user.id,
                ),
            },
        )
        task_ids.append(result.id)
    return Response({"tasks": task_ids}, status=status.HTTP_202_ACCEPTED)


@api_view(["GET"])
def autocomplete_view(request):
    term = request.query_params.get("term", "")
    if not term:
        return Response([])
    user = None if request.user.is_superuser else request.user
    return Response(get_backend().autocomplete(term, 8, user))


# --------------------------------------------------------------------------- #
# trash
# --------------------------------------------------------------------------- #
def trash_documents(user):
    # A version is listed only when its root is not in the trash as well.
    qs = Document.deleted_objects.exclude(
        root_document_id__in=Document.deleted_objects.values("id"),
    )
    if user.is_superuser:
        return qs
    return qs.filter(Q(owner=user) | Q(owner__isnull=True))


class TrashSerializer(DocumentSerializer):
    class Meta(DocumentSerializer.Meta):
        fields = (*DocumentSerializer.Meta.fields, "deleted_at")
        read_only_fields = (*DocumentSerializer.Meta.read_only_fields, "deleted_at")


def _ids(request) -> list[int] | None:
    raw = request.data.get("ids")
    if raw is None:
        return None
    return [int(i) for i in raw if str(i).isdigit()]


@api_view(["GET"])
def trash_list(request):
    paginator = Pagination()
    page = paginator.paginate_queryset(
        trash_documents(request.user).prefetch_related("tags").order_by("-deleted_at"),
        request,
    )
    response = paginator.get_paginated_response(TrashSerializer(page, many=True).data)
    response.data["retention_days"] = settings.EMPTY_TRASH_DELAY
    return response


@api_view(["POST"])
def trash_restore(request):
    ids = _ids(request) or []
    docs = list(trash_documents(request.user).filter(id__in=ids))
    for doc in docs:
        doc.restore(strict=False)
    if docs:
        with get_backend().batch_update() as batch:
            batch.add_or_update_ids([d.pk for d in docs])
    return Response({"restored": [d.pk for d in docs]})


@api_view(["POST"])
def trash_empty(request):
    """Permanently delete the given ids, or everything in the user's trash."""
    ids = _ids(request)
    qs = trash_documents(request.user)
    if ids is not None:
        qs = qs.filter(id__in=ids)
    doc_ids = list(qs.values_list("id", flat=True))
    if doc_ids:
        empty_trash(doc_ids=doc_ids)
    return Response({"deleted": doc_ids})


# --------------------------------------------------------------------------- #
# settings: preferences, OCR configuration, password
# --------------------------------------------------------------------------- #
THEMES = {"system", "light", "dark"}
PAGE_SIZES = {30, 60, 100}


@api_view(["GET", "PATCH"])
def preferences_view(request):
    ui, _ = UiSettings.objects.get_or_create(user=request.user, defaults={"settings": {}})
    data = dict(ui.settings or {})
    if request.method == "PATCH":
        theme = request.data.get("theme", data.get("theme", "system"))
        size = request.data.get("page_size", data.get("page_size", 30))
        try:
            size = int(size)
        except (TypeError, ValueError):
            size = 0
        try:
            hue = int(request.data.get("hue", data.get("hue", 176)))
        except (TypeError, ValueError):
            hue = -1
        if theme not in THEMES or size not in PAGE_SIZES or not 0 <= hue <= 360:
            return Response({"detail": "Ungültiger Wert."}, status=400)
        data.update({"theme": theme, "page_size": size, "hue": hue})
        ui.settings = data
        ui.save()
    return Response(
        {
            "theme": data.get("theme", "system"),
            "page_size": data.get("page_size", 30),
            "hue": data.get("hue", 176),
        },
    )


class OcrConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApplicationConfiguration
        fields = (
            "language",
            "mode",
            "archive_file_generation",
            "output_type",
            "deskew",
            "rotate_pages",
        )

    def validate_language(self, value):
        value = (value or "").strip()
        if value and not all(p.replace("_", "").isalnum() for p in value.split("+")):
            raise serializers.ValidationError(
                "Sprachcodes mit + verbinden, z. B. deu+eng.",
            )
        return value or None


def _ocr_defaults() -> dict:
    return {
        "language": getattr(settings, "OCR_LANGUAGE", "eng"),
        "mode": getattr(settings, "OCR_MODE", "auto"),
        "archive_file_generation": getattr(settings, "ARCHIVE_FILE_GENERATION", "auto"),
        "output_type": getattr(settings, "OCR_OUTPUT_TYPE", "pdfa"),
        "deskew": getattr(settings, "OCR_DESKEW", False),
        "rotate_pages": getattr(settings, "OCR_ROTATE_PAGES", True),
    }


@api_view(["GET", "PATCH"])
def ocr_config_view(request):
    config = ApplicationConfiguration.objects.first() or ApplicationConfiguration.objects.create()
    if request.method == "PATCH":
        if not request.user.is_superuser:
            return Response({"detail": "Nur Administratoren."}, status=403)
        serializer = OcrConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
    return Response({**OcrConfigSerializer(config).data, "defaults": _ocr_defaults()})


@api_view(["POST"])
def password_view(request):
    user = request.user
    if not user.check_password(request.data.get("current", "")):
        return Response({"detail": "Das aktuelle Passwort ist falsch."}, status=400)
    new = request.data.get("new", "")
    if len(new) < 8:
        return Response({"detail": "Das neue Passwort braucht mindestens 8 Zeichen."}, status=400)
    try:
        validate_password(new, user)
    except DjangoValidationError as e:
        return Response({"detail": " ".join(e.messages)}, status=400)
    user.set_password(new)
    user.save()
    update_session_auth_hash(request, user)
    return Response({"ok": True})


# --------------------------------------------------------------------------- #
# single page app + health
# --------------------------------------------------------------------------- #
from django.http import HttpResponse  # noqa: E402
from django.views.decorators.cache import never_cache  # noqa: E402

_APP_HTML = Path(__file__).parent / "templates" / "app.html"


@never_cache
def index_view(request, *args, **kwargs):
    return HttpResponse(_APP_HTML.read_text(encoding="utf-8"), content_type="text/html")


def health_view(request):
    return HttpResponse("ok", content_type="text/plain")
