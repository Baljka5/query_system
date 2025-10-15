from django.contrib import admin
from django.db.models import Count
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.html import format_html

from .models import QuerySnippet, UserDBAccess, SnippetCopyLog


# --------------------------
# Inline: User → DB type rights
# --------------------------
class UserDBAccessInline(admin.TabularInline):
    model = UserDBAccess
    extra = 0
    can_delete = True
    verbose_name = "Allowed DB type"
    verbose_name_plural = "Allowed DB types"


# Хэрэв User admin-даа inline нэммээр байвал:
try:
    from django.contrib.auth.admin import UserAdmin
    from django.contrib.auth.models import User


    class UserAdminWithDBAccess(UserAdmin):
        inlines = [UserDBAccessInline]


    # байх бүртгэлийг солино
    admin.site.unregister(User)
    admin.site.register(User, UserAdminWithDBAccess)
except admin.sites.NotRegistered:
    # Зарим төсөлд User-г өөр app дээр аль хэдийн өөрчилсөн байж болно
    pass


# --------------------------
# QuerySnippet Admin
# --------------------------
@admin.register(QuerySnippet)
class QuerySnippetAdmin(admin.ModelAdmin):
    # ТАНЫ байгааг үлдээж, нэмэлтүүдийг өргөтгөл болгож өглөө
    list_display = (
        "id",
        "title",
        "db_type",
        "sql_kind_badge",  # NEW: өнгөт badge
        "created_by",
        "updated_at",
        "use_count",
        "logs_link",  # NEW: copy лог руу богино линк
    )
    search_fields = ("title", "description", "sql_text", "tags")
    list_filter = ("db_type", "sql_kind", "created_by")
    readonly_fields = ("use_count", "created_at", "updated_at")
    autocomplete_fields = ("created_by",)  # NEW
    list_select_related = ("created_by",)
    date_hierarchy = "updated_at"
    ordering = ("-updated_at",)

    actions = ["recount_use_from_logs"]  # NEW

    def sql_kind_badge(self, obj):
        # SELECT / modify / dangerous-ийг өнгөөр ялгана
        label = obj.sql_kind or "select"
        color = {
            "select": "#16a34a",  # green
            "modify": "#2563eb",  # blue
            "dangerous": "#b91c1c",  # red
        }.get(label, "#334155")
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:12px;background:{}20;color:{};border:1px solid {}40;font-size:12px;">{}</span>',
            color, color, color, label
        )

    sql_kind_badge.short_description = "SQL kind"
    sql_kind_badge.admin_order_field = "sql_kind"

    def logs_link(self, obj):
        url = (
                reverse("admin:vault_snippetcopylog_changelist")
                + "?"
                + urlencode({"snippet__id__exact": obj.id})
        )
        return format_html('<a href="{}">View logs</a>', url)

    logs_link.short_description = "Copy logs"

    @admin.action(description="Recount use_count from copy logs")
    def recount_use_from_logs(self, request, queryset):
        # SnippetCopyLog-аас дахин тооцоод use_count-ыг update хийнэ
        counts = (
            SnippetCopyLog.objects
            .filter(snippet__in=queryset)
            .values("snippet_id")
            .annotate(c=Count("id"))
        )
        map_cnt = {row["snippet_id"]: row["c"] for row in counts}
        updated = 0
        for s in queryset:
            new_val = map_cnt.get(s.id, 0)
            if s.use_count != new_val:
                s.use_count = new_val
                s.save(update_fields=["use_count"])
                updated += 1
        self.message_user(request, f"Updated use_count for {updated} snippet(s).")


# --------------------------
# UserDBAccess Admin
# --------------------------
@admin.register(UserDBAccess)
class UserDBAccessAdmin(admin.ModelAdmin):
    list_display = ("user", "db_type")
    list_filter = ("db_type",)
    search_fields = ("user__username",)


# --------------------------
# SnippetCopyLog Admin
# --------------------------
@admin.register(SnippetCopyLog)
class SnippetCopyLogAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "snippet",
        "user",
        "copied_at",
        "ip_address",
        "ua_short",
        "chars",
    )
    list_filter = ("user", "snippet", "copied_at")
    search_fields = ("snippet__title", "user__username", "user_agent", "sql_snapshot")
    readonly_fields = (
    "snippet", "user", "copied_at", "ip_address", "user_agent", "referer", "sql_snapshot", "sql_chars")

    # Performance ба хэрэглэхэд амар болгох тохиргоо
    raw_id_fields = ("user", "snippet")  # NEW: том дата дээр хурдан болно
    list_select_related = ("user", "snippet")  # NEW: FK-уудыг join-оор татна
    date_hierarchy = "copied_at"  # NEW: огноогоор навигац
    ordering = ("-copied_at",)

    def ua_short(self, obj):
        ua = obj.user_agent or ""
        return (ua[:60] + "…") if len(ua) > 60 else ua

    ua_short.short_description = "User-Agent"

    def chars(self, obj):
        return getattr(obj, "sql_chars", None)

    chars.short_description = "SQL chars"


# --------------------------
# Admin site branding
# --------------------------
admin.site.site_header = "QueryVault Admin"
admin.site.site_title = "QueryVault Admin"
admin.site.index_title = "Administration"
