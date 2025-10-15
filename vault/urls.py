# vault/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from views_auth import LogoutGetOK
from . import views
from .views_quick import QuickSave
from .view_generate import \
    GenerateSQL  # Хэрвээ GenerateSQL танай views.py-д байвал энэ мөрийг: from .views import GenerateSQL гэж солиорой.
from .api_views import QuerySnippetViewSet
from django.contrib.auth import views as auth_views

# DEBUG үед static serve хийхэд
from django.conf import settings
from django.conf.urls.static import static

app_name = "vault"

# --- API router ---
router = DefaultRouter()
router.register(r"snippets", QuerySnippetViewSet, basename="snippets")

urlpatterns = [
    # --- Auth (login/logout) ---
    path("login/", auth_views.LoginView.as_view(template_name="vault/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="vault:login"), name="logout"),

    # --- Нэмэлт: Password change/reset урсгалууд (хүсвэл ашиглана) ---
    # Эдгээрийг ашиглах бол template бэлдэх эсвэл default template-уудыг ашиглана.
    path("accounts/password_change/",
         auth_views.PasswordChangeView.as_view(template_name="vault/password_change.html"),
         name="password_change"),
    path("accounts/password_change/done/",
         auth_views.PasswordChangeDoneView.as_view(template_name="vault/password_change_done.html"),
         name="password_change_done"),
    path("accounts/password_reset/",
         auth_views.PasswordResetView.as_view(template_name="vault/password_reset.html"),
         name="password_reset"),
    path("accounts/password_reset/done/",
         auth_views.PasswordResetDoneView.as_view(template_name="vault/password_reset_done.html"),
         name="password_reset_done"),
    path("accounts/reset/<uidb64>/<token>/",
         auth_views.PasswordResetConfirmView.as_view(template_name="vault/password_reset_confirm.html"),
         name="password_reset_confirm"),
    path("accounts/reset/done/",
         auth_views.PasswordResetCompleteView.as_view(template_name="vault/password_reset_complete.html"),
         name="password_reset_complete"),

    # --- App views ---
    path("s/<int:pk>/copy/", views.copy_event, name="snippet_copy"),

    path("", views.SnippetList.as_view(), name="snippet_list"),
    path("s/<int:pk>/", views.SnippetDetail.as_view(), name="snippet_detail"),
    path("create/", views.SnippetCreate.as_view(), name="snippet_create"),
    path("s/<int:pk>/edit/", views.SnippetUpdate.as_view(), name="snippet_update"),

    path("quick/", QuickSave.as_view(), name="quick_save"),
    path("generate/", GenerateSQL.as_view(), name="generate_sql"),

    # --- API endpoints ---
    path("api/", include(router.urls)),
]

# Dev (DEBUG=True) үед static файлууд
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
