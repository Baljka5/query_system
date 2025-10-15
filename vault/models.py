# vault/models.py
from django.contrib.auth import get_user_model
from django.db import models
from django.contrib.auth.models import User

class QuerySnippet(models.Model):
    DB_CHOICES = [
        ('postgres', 'PostgreSQL'),
        ('mysql', 'MySQL/MariaDB'),
        ('sqlite', 'SQLite'),
        ('mssql', 'SQL Server'),
        ('clickhouse', 'ClickHouse'),
        ('other', 'Other'),
    ]
    SQL_KIND_CHOICES = [
        ('select', 'SELECT only'),
        ('modify', 'INSERT/UPDATE/MERGE'),
        ('dangerous', 'DELETE/DDL (DROP/ALTER/TRUNCATE/CREATE/GRANT/REVOKE)'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    sql_text = models.TextField()
    db_type = models.CharField(max_length=20, choices=DB_CHOICES, default='mysql')
    tags = models.CharField(max_length=200, blank=True)
    use_count = models.IntegerField(default=0)
    created_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    sql_kind = models.CharField(max_length=16, choices=SQL_KIND_CHOICES,
                                default='select', db_index=True)

    def save(self, *args, **kwargs):
        self.sql_kind = classify_sql_kind(self.sql_text)
        super().save(*args, **kwargs)

    @property
    def tag_list(self):
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

def _strip_comments(sql: str) -> str:
    import re
    s = sql or ""
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S)
    s = re.sub(r"--.*?$", " ", s, flags=re.M)
    return s.strip()

def classify_sql_kind(sql: str) -> str:
    import re
    s = _strip_comments(sql).lower()
    if not s:
        return 'select'
    m = re.match(r"^(with|select|insert|update|merge|delete|truncate|drop|alter|create|grant|revoke)", s)
    kw = m.group(1) if m else ''
    if kw in ('select', 'with'):
        if re.search(r"\b(insert|update|merge|delete|truncate|drop|alter|create|grant|revoke)\b", s):
            if re.search(r"\b(delete|truncate|drop|alter|create|grant|revoke)\b", s):
                return 'dangerous'
            return 'modify'
        return 'select'
    if kw in ('insert', 'update', 'merge'):
        return 'modify'
    if kw in ('delete', 'truncate', 'drop', 'alter', 'create', 'grant', 'revoke'):
        return 'dangerous'
    return 'select'


class UserDBAccess(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='db_accesses')
    db_type = models.CharField(max_length=20, choices=QuerySnippet.DB_CHOICES)

    class Meta:
        unique_together = ('user', 'db_type')

    def __str__(self):
        return f"{self.user.username} → {self.db_type}"

class SnippetCopyLog(models.Model):
    snippet = models.ForeignKey(QuerySnippet, on_delete=models.CASCADE, related_name="copy_logs")
    user = models.ForeignKey(get_user_model(), null=True, blank=True, on_delete=models.SET_NULL)
    copied_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True)
    referer = models.URLField(blank=True)
    sql_snapshot = models.TextField(blank=True)
    sql_chars = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-copied_at"]
        indexes = [
            models.Index(fields=["copied_at"]),
        ]

    def __str__(self):
        u = self.user.username if self.user else "anon"
        return f"Copy #{self.id} • {self.snippet.title} • {u}"
