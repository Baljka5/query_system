# vault/views_generate.py
from django.views import View
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required


@method_decorator(login_required, name="dispatch")
class GenerateSQL(View):
    def get(self, request):
        return render(request, "vault/generate.html")
