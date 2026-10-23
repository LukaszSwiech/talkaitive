from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("conversations/start/", views.conversation_start, name="conversation_start"),
    path(
        "conversations/start/random/",
        views.conversation_start_random,
        name="conversation_start_random",
    ),
    path(
        "conversations/<int:pk>/",
        views.conversation_detail,
        name="conversation_detail",
    ),
    path(
        "conversations/<int:pk>/messages/",
        views.conversation_send,
        name="conversation_send",
    ),
    path(
        "conversations/<int:pk>/retry/",
        views.conversation_retry,
        name="conversation_retry",
    ),
    path(
        "conversations/<int:pk>/end/", views.conversation_end, name="conversation_end"
    ),
    path(
        "conversations/<int:pk>/analysis/",
        views.conversation_analyze,
        name="conversation_analyze",
    ),
    # Always registered; the view returns 404 outside DEBUG.
    path("ui/", views.ui_kitchen_sink, name="ui_kitchen_sink"),
]
