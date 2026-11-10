from django.urls import include
from django.urls import path
from django.urls import re_path
from rest_framework.routers import DefaultRouter

from documents import api

router = DefaultRouter()
router.register(r"documents", api.DocumentViewSet, basename="documents")
router.register(r"tags", api.TagViewSet, basename="tags")
router.register(r"correspondents", api.CorrespondentViewSet, basename="correspondents")
router.register(r"document_types", api.DocumentTypeViewSet, basename="document_types")
router.register(r"users", api.UserViewSet, basename="users")

urlpatterns = [
    path("api/auth/session/", api.session_view),
    path("api/auth/login/", api.login_view),
    path("api/auth/logout/", api.logout_view),
    path("api/auth/setup/", api.setup_view),
    path("api/documents/upload/", api.upload_view),
    path("api/documents/<int:pk>/<str:kind>/", api.document_file),
    path("api/search/autocomplete/", api.autocomplete_view),
    path("api/", include(router.urls)),
    path("healthz", api.health_view),
    re_path(r"^(?!api/|static/).*$", api.index_view),
]
