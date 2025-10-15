# vault/api_views.py
from rest_framework import viewsets, permissions, serializers
from django.db.models import Q
from rest_framework.decorators import action
from rest_framework.response import Response
from django.core.cache import cache

import hashlib
import json
import re

from .models import QuerySnippet, classify_sql_kind
from .serializers import QuerySnippetSerializer
from .sql_validation import validate_sql as _validate_sql, SQLSyntaxError

from .ai import ai_generate_sql as _ai_generate_sql, ai_fix_sql as _ai_fix_sql
from .utils_perms import allowed_sql_kinds_for, allowed_db_types_for, user_role


# ------------- helpers -------------
def _tokenize(text: str):
    tokens = re.findall(r"[0-9A-Za-z_А-Яа-яӨөҮүЁё]+", (text or "").lower())
    return [t for t in tokens if len(t) > 2]


def _search_queryset(qs, q: str):
    tokens = _tokenize(q)
    if not tokens:
        return qs
    q_obj = Q()
    for t in tokens:
        q_obj |= (
                Q(title__icontains=t)
                | Q(description__icontains=t)
                | Q(sql_text__icontains=t)
                | Q(tags__icontains=t)
        )
    return qs.filter(q_obj)


def _trim(s: str, n: int) -> str:
    return (s or "")[:n]


def _mk_cache_key(ask, db_type, schema, kinds, examples):
    payload = {
        "ask": (ask or "").strip(),
        "db_type": db_type,
        "schema": (schema or "").strip(),
        "kinds": sorted(list(kinds or [])),
        "ex": [{"nl": _trim(e.get("nl", ""), 200), "sql": _trim(e.get("sql", ""), 600)} for e in (examples or [])],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return "ai:sql:" + hashlib.sha1(raw).hexdigest()


# ------------- rule-based (fast path) -------------
def _simple_rule_based_sql(ask: str, db_type: str, schema: str) -> str:
    toks = _tokenize(ask)

    def quoted_keyword(s: str):
        m = re.search(r"'([^']+)'|\"([^\"]+)\"", s or "")
        return (m.group(1) or m.group(2)) if m else ""

    kw = quoted_keyword(ask)

    if db_type == "mysql":
        if any(w in toks for w in ["системтэй", "систем", "schema", "metadata", "мэдээллийн", "таблиц", "хүснэгт"]):
            if any(w in toks for w in ["column", "columns", "багана", "талбар"]) and kw:
                kw_sql = kw.replace("'", "''")
                return f"""
SELECT table_schema, table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE CONCAT(table_schema,'.',table_name,'.',column_name) LIKE CONCAT('%','{kw_sql}','%')
  AND table_schema NOT IN ('mysql','performance_schema','sys','information_schema')
ORDER BY table_schema, table_name, ordinal_position;
""".strip()
            if any(w in toks for w in ["fk", "foreign", "гадаад", "гадаадтүлхүүр", "гадаад_түлхүүр"]):
                return """
SELECT
  kcu.constraint_name,
  kcu.table_schema, kcu.table_name, kcu.column_name,
  kcu.referenced_table_name AS ref_table,
  kcu.referenced_column_name AS ref_column
FROM information_schema.key_column_usage AS kcu
WHERE kcu.referenced_table_name IS NOT NULL
ORDER BY kcu.table_schema, kcu.table_name, kcu.constraint_name, kcu.ordinal_position;
""".strip()
            if any(w in toks for w in ["index", "indexes", "индекс", "unique"]):
                return """
SELECT
  s.table_schema, s.table_name, s.index_name,
  GROUP_CONCAT(s.column_name ORDER BY s.seq_in_index) AS columns,
  MIN(s.non_unique) = 0 AS is_unique
FROM information_schema.statistics AS s
WHERE s.table_schema NOT IN ('mysql','performance_schema','sys','information_schema')
GROUP BY s.table_schema, s.table_name, s.index_name
ORDER BY s.table_schema, s.table_name, s.index_name;
""".strip()
            return """
SELECT table_schema, table_name, engine, table_rows
FROM information_schema.tables
WHERE table_schema NOT IN ('mysql','performance_schema','sys','information_schema')
ORDER BY table_schema, table_name;
""".strip()
        return "SELECT *\nFROM sales;"

    if db_type == "postgres":
        if any(w in toks for w in ["систем", "schema", "metadata", "таблиц", "хүснэгт"]):
            if any(w in toks for w in ["column", "columns", "багана", "талбар"]) and kw:
                kw_sql = kw.replace("'", "''")
                return f"""
SELECT table_schema, table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE (table_schema || '.' || table_name || '.' || column_name) ILIKE '%{kw_sql}%'
  AND table_schema NOT IN ('pg_catalog','information_schema')
ORDER BY table_schema, table_name, ordinal_position;
""".strip()
            if any(w in toks for w in ["fk", "foreign", "гадаад"]):
                return """
SELECT
  tc.constraint_name,
  kcu.table_schema, kcu.table_name, kcu.column_name,
  ccu.table_name AS ref_table, ccu.column_name AS ref_column
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu USING (constraint_name, table_schema)
JOIN information_schema.constraint_column_usage AS ccu USING (constraint_name, table_schema)
WHERE tc.constraint_type = 'FOREIGN KEY'
ORDER BY kcu.table_schema, kcu.table_name, tc.constraint_name;
""".strip()
            if any(w in toks for w in ["index", "индекс"]):
                return """
SELECT
  schemaname AS table_schema, tablename AS table_name, indexname,
  indexdef
FROM pg_indexes
WHERE schemaname NOT IN ('pg_catalog','information_schema')
ORDER BY schemaname, tablename, indexname;
""".strip()
            return """
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog','information_schema')
ORDER BY table_schema, table_name;
""".strip()

    if db_type == "clickhouse":
        if any(w in toks for w in ["систем", "schema", "metadata", "таблиц", "хүснэгт"]):
            if any(w in toks for w in ["column", "columns", "багана"]) and kw:
                kw_sql = kw.replace("'", "''")
                return f"""
SELECT database, table, name AS column, type
FROM system.columns
WHERE (database || '.' || table || '.' || name) ILIKE '%{kw_sql}%'
ORDER BY database, table, position;
""".strip()
            if any(w in toks for w in ["index", "индекс"]):
                return """
SELECT database, table, name, type, expr
FROM system.data_skipping_indices
ORDER BY database, table, name;
""".strip()
            return """
SELECT database, name AS table, engine
FROM system.tables
ORDER BY database, name;
""".strip()

    if db_type == "sqlite":
        return "SELECT name AS table_name FROM sqlite_master WHERE type='table' ORDER BY name;"
    if db_type == "mssql":
        return "SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES ORDER BY TABLE_SCHEMA, TABLE_NAME;"

    return "SELECT *\nFROM sales;"


# ------------- ViewSet -------------
class QuerySnippetViewSet(viewsets.ModelViewSet):
    queryset = QuerySnippet.objects.all().order_by("-updated_at")
    serializer_class = QuerySnippetSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["db_type"]
    search_fields = ["title", "description", "sql_text", "tags"]

    def get_queryset(self):
        qs = super().get_queryset()
        request = self.request

        q = request.query_params.get("q", "").strip()
        tag = request.query_params.get("tag", "").strip()
        dbt = request.query_params.get("db_type", "").strip()

        if tag:
            qs = qs.filter(tags__icontains=tag)
        if dbt:
            qs = qs.filter(db_type=dbt)

        kinds = allowed_sql_kinds_for(request.user)
        qs = qs.filter(sql_kind__in=kinds)

        db_types = allowed_db_types_for(request.user)
        if db_types is not None:
            qs = qs.filter(db_type__in=db_types)

        return _search_queryset(qs, q)

    def perform_create(self, serializer):
        data = serializer.validated_data
        sql_kind = classify_sql_kind(data.get("sql_text", ""))

        kinds = allowed_sql_kinds_for(self.request.user)
        if sql_kind not in kinds and user_role(self.request.user) != "admin":
            raise serializers.ValidationError({"sql_text": "Таны роль энэ төрлийн SQL хадгалах эрхгүй."})

        db_types = allowed_db_types_for(self.request.user)
        if db_types is not None and data.get("db_type") not in db_types:
            raise serializers.ValidationError({"db_type": "Таны DB type эрх хүрэхгүй байна."})

        obj = serializer.save(created_by=self.request.user)
        obj.sql_kind = sql_kind
        obj.save(update_fields=["sql_kind"])

    def perform_update(self, serializer):
        data = serializer.validated_data
        sql_kind = classify_sql_kind(data.get("sql_text", ""))

        kinds = allowed_sql_kinds_for(self.request.user)
        if sql_kind not in kinds and user_role(self.request.user) != "admin":
            raise serializers.ValidationError({"sql_text": "Таны роль энэ төрлийн SQL засах эрхгүй."})

        db_types = allowed_db_types_for(self.request.user)
        if db_types is not None and data.get("db_type") not in db_types:
            raise serializers.ValidationError({"db_type": "Таны DB type эрх хүрэхгүй байна."})

        obj = serializer.save()
        obj.sql_kind = sql_kind
        obj.save(update_fields=["sql_kind"])

    @action(detail=False, methods=["get"])
    def search(self, request):
        qs = self.get_queryset()
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=False, methods=["post"])
    def validate_sql(self, request):
        sql_text = request.data.get("sql_text", "")
        db_type = request.data.get("db_type", "other")
        try:
            dialect = _validate_sql(sql_text, db_type)
        except SQLSyntaxError as e:
            return Response({"ok": False, "error": str(e)}, status=400)
        return Response({"ok": True, "dialect": dialect})

    @action(detail=False, methods=["post"])
    def generate_sql(self, request):
        ask = request.data.get("ask", "")
        db_type = request.data.get("db_type", "other")
        schema = request.data.get("schema", "")

        qs = _search_queryset(self.get_queryset(), ask)
        suggestions = list(qs.values("id", "title", "tags", "use_count", "db_type")[:8])

        sql = _simple_rule_based_sql(ask, db_type, schema)
        return Response({"ok": True, "sql": sql, "suggestions": suggestions})

    @action(detail=False, methods=["post"])
    def ai_generate_sql(self, request):
        ask = request.data.get("ask", "") or ""
        db_type = request.data.get("db_type", "other")
        schema = request.data.get("schema", "") or ""

        kinds = allowed_sql_kinds_for(request.user)

        # few-shot (богиноруулж өгнө)
        base_qs = self.get_queryset()
        sugg_qs = _search_queryset(base_qs, ask)[:5]
        examples = [{"nl": _trim(s.description or s.title, 200),
                     "sql": _trim(s.sql_text, 800),
                     "schema": ""} for s in sugg_qs]

        # ---- CACHE ----
        cache_key = _mk_cache_key(ask, db_type, schema, kinds, examples)
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        # 1) эхний генерац
        try:
            sql = _ai_generate_sql(ask, db_type, schema, kinds, examples=examples)
        except Exception as e:
            return Response({"ok": False, "error": str(e)}, status=503)

        # 2) цэвэрлэгээ
        sql = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]", "", sql).strip()

        # 3) баталгаажуулах + self-repair (2 хүртэл)
        last_err = None
        for _ in range(3):
            try:
                _validate_sql(sql, db_type)
                break
            except SQLSyntaxError as e:
                last_err = str(e)
                try:
                    sql = _ai_fix_sql(sql, db_type, kinds, last_err)
                    sql = re.sub(r"[^\x09\x0A\x0D\x20-\x7E\u00A0-\uFFFF]", "", sql).strip()
                except Exception as ie:
                    last_err = f"{last_err} / fix failed: {ie}"
                    break
        else:
            return Response({"ok": False, "error": f"AI generated invalid SQL: {last_err}"}, status=400)

        # 4) эрхийн шүүлт
        k = classify_sql_kind(sql)
        if k not in kinds and user_role(request.user) != "admin":
            try:
                sql2 = _ai_generate_sql(ask, db_type, schema, {"select"}, examples=examples)
                _validate_sql(sql2, db_type)
                k2 = classify_sql_kind(sql2)
                if k2 not in kinds:
                    return Response({"ok": False, "error": "Generated SQL violates your permissions."}, status=403)
                sql, k = sql2, k2
            except Exception:
                return Response({"ok": False, "error": "Generated SQL violates your permissions."}, status=403)

        # 5) төстэй snippet-үүд
        qs = _search_queryset(self.get_queryset(), ask)
        suggestions = list(qs.values("id", "title", "tags", "use_count", "db_type")[:8])

        result = {"ok": True, "sql": sql, "kind": k, "suggestions": suggestions}
        cache.set(cache_key, result, timeout=3600)  # 1 цаг
        return Response(result)
