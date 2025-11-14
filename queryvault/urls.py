# /var/www/query_system/queryvault/urls.py

from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path(
        "admin/logout/",
        auth_views.LogoutView.as_view(next_page="/admin/login/"),
        name="admin-logout",
    ),

    path("admin/", admin.site.urls),

    path("", include("vault.urls")),
    path("api/", include("vault.api_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
