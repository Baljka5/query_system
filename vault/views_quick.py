from django.views import View
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from .forms import SnippetForm
from .utils_perms import allowed_db_types_for

@method_decorator(login_required, name="dispatch")
class QuickSave(View):
    def get(self, request):
        form = SnippetForm()
        allowed = allowed_db_types_for(request.user)
        field = form.fields["db_type"]
        choices = field.choices
        if allowed is not None:
            choices = [(v, lbl) for v, lbl in choices if v in allowed]

        return render(
            request,
            "vault/quick_save.html",
            {"db_type_choices": choices},
        )