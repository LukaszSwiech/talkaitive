from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def home(request: HttpRequest) -> HttpResponse:
    """Temporary welcome page; S-01 replaces it with the conversation screen."""
    return render(request, "accounts/home.html")
