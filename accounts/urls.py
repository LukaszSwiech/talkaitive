from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

urlpatterns = [
    path("login/", LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
]
