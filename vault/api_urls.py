from django.urls import path, include
from rest_framework import routers
from .api_views import QuerySnippetViewSet

router = routers.DefaultRouter()
router.register(r"snippets", QuerySnippetViewSet, basename="snippets")

urlpatterns = [
    path("", include(router.urls)),
]
