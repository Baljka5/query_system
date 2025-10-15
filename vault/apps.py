# vault/apps.py
from django.apps import AppConfig


class VaultConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "vault"

    def ready(self):
        try:
            from .ai import ai_generate_sql
            ai_generate_sql("ping", "mysql", "", {"select"})
        except Exception:
            pass
