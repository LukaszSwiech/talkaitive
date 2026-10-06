from django.contrib.auth.views import LoginView
from django.urls import path

urlpatterns = [
    path("login/", LoginView.as_view(redirect_authenticated_user=True), name="login"),
]
