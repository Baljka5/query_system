from django.views import View
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator

@method_decorator(login_required, name="dispatch")
class QuickSave(View):
    def get(self, request):
        return render(request, "vault/quick_save.html", {})
