from django.contrib.auth import views as auth_views

class LogoutGetOK(auth_views.LogoutView):
    http_method_names = ['get', 'post', 'options']