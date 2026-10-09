from django.contrib.auth.decorators import login_not_required
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views

urlpatterns = [
    path("login/", LoginView.as_view(redirect_authenticated_user=True), name="login"),
    # Open to signed-out users too (expired session, another tab): otherwise the
    # button bounces through /login/?next=/logout/ and ends on a GET 405.
    path(
        "logout/",
        login_not_required(LogoutView.as_view(next_page="login")),
        name="logout",
    ),
    path("account/delete/", views.account_delete, name="account_delete"),
]
