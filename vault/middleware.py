# vault/middleware.py
from django.utils import timezone
from django.contrib import auth
from django.shortcuts import redirect
from django.urls import reverse

INACTIVITY_TIMEOUT = 180

class IdleLogoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt_paths = {
            reverse('vault:login'),
            reverse('vault:logout'),
            '/admin/login/',
            '/admin/logout/',
        }

    def __call__(self, request):
        if not request.user.is_authenticated:
            return self.get_response(request)

        path = request.path
        if path.startswith('/static/') or path.startswith('/media/') or path in self.exempt_paths:
            return self.get_response(request)

        now = timezone.now()
        last_activity = request.session.get('last_activity')

        if last_activity:
            idle_seconds = (now - timezone.datetime.fromisoformat(last_activity)).total_seconds()
            if idle_seconds > INACTIVITY_TIMEOUT:
                auth.logout(request)
                return redirect(reverse('vault:login'))

        request.session['last_activity'] = now.isoformat()

        return self.get_response(request)
