from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("login/", LoginView.as_view(redirect_authenticated_user=True), name="login"),
    path("logout/", LogoutView.as_view(next_page="login"), name="logout"),
    path("account/delete/", views.account_delete, name="account_delete"),
]
