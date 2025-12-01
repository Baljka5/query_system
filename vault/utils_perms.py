# vault/utils_perms.py
from django.contrib.auth.models import Group
from .models import UserDBAccess

ROLE_GROUPS = {
    "mid": "mid_user",
    "super": "super_user",
}


def user_role(user) -> str:
    if not user.is_authenticated:
        return "anon"
    if user.is_staff or user.is_superuser:
        return "admin"
    if user.groups.filter(name=ROLE_GROUPS["super"]).exists():
        return "super"
    if user.groups.filter(name=ROLE_GROUPS["mid"]).exists():
        return "mid"
    return "user"


def allowed_sql_kinds_for(user):
    r = user_role(user)

    if r == "admin":
        return ["select", "modify", "insert", "dangerous"]

    if r == "super":
        return ["select", "modify", "insert", "dangerous"]

    if r == "mid":
        return ["select", "modify", "insert"]

    if r == "user":
        return ["select"]

    # anon
    return []


def allowed_db_types_for(user):
    if user_role(user) == "admin":
        return None
    qs = UserDBAccess.objects.filter(user=user).values_list("db_type", flat=True)
    return list(qs)
