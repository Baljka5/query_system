from django.contrib.auth.decorators import login_required
from django.db.models import Q, F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, ListView
from django.contrib import messages
from django.http import Http404, JsonResponse, HttpResponseForbidden

from .models import QuerySnippet, SnippetCopyLog, classify_sql_kind
from .forms import SnippetForm
from django.contrib.auth.mixins import LoginRequiredMixin
from .utils_perms import allowed_sql_kinds_for, allowed_db_types_for


def _search_queryset(qs, q):
    if not q:
        return qs
    try:
        # Postgres FTS байвал ашиглана
        from django.contrib.postgres.search import SearchQuery, SearchVector, SearchRank
        vector = (
                SearchVector("title", weight="A")
                + SearchVector("description", weight="B")
                + SearchVector("sql_text", weight="C")
                + SearchVector("tags", weight="B")
        )
        query = SearchQuery(q)
        qs = qs.annotate(rank=SearchRank(vector, query)).filter(vector=query).order_by("-rank", "-updated_at")
    except Exception:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(description__icontains=q)
            | Q(sql_text__icontains=q)
            | Q(tags__icontains=q)
        )
    return qs


class SnippetList(LoginRequiredMixin, ListView):
    model = QuerySnippet
    template_name = "vault/snippet_list.html"
    context_object_name = "snippets"
    paginate_by = 10

    def get_queryset(self):
        qs = super().get_queryset().order_by("-updated_at")
        q = self.request.GET.get("q", "")
        tag = self.request.GET.get("tag", "")
        dbt = self.request.GET.get("db_type", "")

        # хайлт/шүүлт
        if q:
            qs = qs.filter(
                Q(title__icontains=q)
                | Q(description__icontains=q)
                | Q(sql_text__icontains=q)
                | Q(tags__icontains=q)
            )
        if tag:
            qs = qs.filter(tags__icontains=tag)
        if dbt:
            qs = qs.filter(db_type=dbt)

        # ЭРХИЙН ШҮҮЛТ
        kinds = allowed_sql_kinds_for(self.request.user)
        qs = qs.filter(sql_kind__in=kinds)

        db_types = allowed_db_types_for(self.request.user)
        if db_types is not None:
            qs = qs.filter(db_type__in=db_types)

        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # template-д хэрэгтэй query params
        ctx["q"] = self.request.GET.get("q", "")
        ctx["tag"] = self.request.GET.get("tag", "")
        ctx["dbt"] = self.request.GET.get("db_type", "")
        return ctx


class SnippetDetail(LoginRequiredMixin, DetailView):
    model = QuerySnippet
    template_name = "vault/snippet_detail.html"
    context_object_name = "obj"

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        # ЭРХ: харах эрхгүй бол 404
        kinds = allowed_sql_kinds_for(self.request.user)
        db_types = allowed_db_types_for(self.request.user)
        if obj.sql_kind not in kinds:
            raise Http404("Not found")
        if db_types is not None and obj.db_type not in db_types:
            raise Http404("Not found")
        return obj


@method_decorator(login_required, name="dispatch")
class SnippetCreate(View):
    def get(self, request):
        form = SnippetForm()
        _limit_form_db_types(form, request.user)
        return render(request, "vault/snippet_form.html", {"form": form})

    def post(self, request):
        form = SnippetForm(request.POST)
        _limit_form_db_types(form, request.user)
        if form.is_valid():
            # Эрх шалгалт
            candidate = form.save(commit=False)
            candidate.created_by = request.user
            # SQL төрөл ангил
            sql_kind = classify_sql_kind(candidate.sql_text)
            kinds = allowed_sql_kinds_for(request.user)
            if sql_kind not in kinds:
                form.add_error("sql_text", "Таны роль энэ төрлийн SQL хадгалах эрхгүй.")
            db_types = allowed_db_types_for(request.user)
            if db_types is not None and candidate.db_type not in db_types:
                form.add_error("db_type", "Таны DB type эрх хүрэхгүй байна.")

            if form.errors:
                return render(request, "vault/snippet_form.html", {"form": form}, status=403)

            candidate.save()
            messages.success(request, "Амжилттай хадгаллаа.")
            return redirect("vault:snippet_detail", pk=candidate.pk)

        return render(request, "vault/snippet_form.html", {"form": form})


@method_decorator(login_required, name="dispatch")
class SnippetUpdate(View):
    def get(self, request, pk):
        obj = get_object_or_404(QuerySnippet, pk=pk)
        ...
        form = SnippetForm(instance=obj)
        _limit_form_db_types(form, request.user)
        return render(request, "vault/snippet_form.html", {"form": form, "obj": obj})

    def post(self, request, pk):
        obj = get_object_or_404(QuerySnippet, pk=pk)
        form = SnippetForm(request.POST, instance=obj)
        _limit_form_db_types(form, request.user)
        if form.is_valid():
            candidate = form.save(commit=False)
            # Эрхийн шалгалт (шинэ утгаар)
            sql_kind = classify_sql_kind(candidate.sql_text)
            kinds = allowed_sql_kinds_for(request.user)
            if sql_kind not in kinds:
                form.add_error("sql_text", "Таны роль энэ төрлийн SQL засах эрхгүй.")
            db_types = allowed_db_types_for(request.user)
            if db_types is not None and candidate.db_type not in db_types:
                form.add_error("db_type", "Таны DB type эрх хүрэхгүй байна.")

            if form.errors:
                return render(request, "vault/snippet_form.html", {"form": form, "obj": obj}, status=403)

            candidate.save()
            messages.success(request, "Амжилттай шинэчиллээ.")
            return redirect("vault:snippet_detail", pk=obj.pk)

        return render(request, "vault/snippet_form.html", {"form": form, "obj": obj})


@login_required
def increment_use(request, pk):
    obj = get_object_or_404(QuerySnippet, pk=pk)
    # харах эрхгүй бол тоолуур нэмэхийг хориглоё
    kinds = allowed_sql_kinds_for(request.user)
    db_types = allowed_db_types_for(request.user)
    if obj.sql_kind not in kinds or (db_types is not None and obj.db_type not in db_types):
        raise Http404("Not found")

    obj.use_count = (obj.use_count or 0) + 1
    obj.save(update_fields=["use_count"])
    return redirect("vault:snippet_detail", pk=pk)


@login_required
def copy_event(request, pk):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "POST required"}, status=405)

    obj = get_object_or_404(QuerySnippet, pk=pk)

    # --- ХАРАХ ЭРХИЙГ давхар шалгана ---
    kinds = allowed_sql_kinds_for(request.user)
    db_types = allowed_db_types_for(request.user)
    if obj.sql_kind not in kinds or (db_types is not None and obj.db_type not in db_types):
        return JsonResponse({"ok": False, "error": "Permission denied"}, status=403)

    # Client info
    ip = (
            request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
            or request.META.get("REMOTE_ADDR")
    )
    ua = (request.META.get("HTTP_USER_AGENT", "") or "")[:512]
    ref = request.META.get("HTTP_REFERER", "")

    # Atomic increment
    QuerySnippet.objects.filter(pk=obj.pk).update(use_count=F("use_count") + 1)
    obj.refresh_from_db(fields=["use_count"])

    # Log copy
    SnippetCopyLog.objects.create(
        snippet=obj,
        user=request.user if request.user.is_authenticated else None,
        ip_address=ip or None,
        user_agent=ua,
        referer=ref,
        sql_snapshot=obj.sql_text,
        sql_chars=len(obj.sql_text or ""),
    )

    return JsonResponse({"ok": True, "use_count": obj.use_count})


def _limit_form_db_types(form, user):
    allowed = allowed_db_types_for(user)
    if allowed is None:
        return form  # бүх DB type OK

    field = form.fields.get("db_type")
    if field:
        field.choices = [(val, label) for val, label in field.choices if val in allowed]
    return form

@method_decorator(login_required, name="dispatch")
class SnippetDelete(View):
    def post(self, request, pk):
        if not request.user.is_superuser:
            return HttpResponseForbidden("Only admins can delete snippets.")

        obj = get_object_or_404(QuerySnippet, pk=pk)
        obj.delete()
        messages.success(request, "Snippet амжилттай устлаа.")
        return redirect("vault:snippet_list")