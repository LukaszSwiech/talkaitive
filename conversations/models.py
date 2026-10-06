from django.db import models
from django.db.models import Q

from accounts.models import PracticeLanguage
from accounts.ownership import UserOwned


class Conversation(UserOwned):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ENDED = "ended", "Ended"

    class EndReason(models.TextChoices):
        USER = "user", "Ended by the user"
        AGENT_GOODBYE = "agent_goodbye", "Agent said goodbye"
        DAILY_LIMIT = "daily_limit", "Daily limit reached"

    # No `choices` on purpose: Django stores choices in migrations, so every change
    # of the topic list would need a new migration. The key is validated in the
    # service through `topics.get_topic`.
    topic = models.CharField(max_length=50)
    # Copy of the topic at the start: the conversation keeps its scene even if the
    # topic is changed or removed in code.
    topic_title = models.TextField()
    topic_scenario = models.TextField()
    # Copied from the user at the start.
    language = models.CharField(max_length=2, choices=PracticeLanguage)
    status = models.CharField(max_length=10, choices=Status, default=Status.ACTIVE)
    end_reason = models.CharField(max_length=20, choices=EndReason, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(status="active"),
                name="conversations_one_active_per_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.topic_title} ({self.status})"

    @property
    def awaiting_agent_reply(self) -> bool:
        """True when the conversation is active and the agent should speak next."""
        if self.status != self.Status.ACTIVE:
            return False
        last_message = self.messages.order_by("-created_at", "-id").first()
        return last_message is None or last_message.role == Message.Role.USER


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=Role)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # Only for agent turns (role=assistant).
    model = models.CharField(max_length=50, blank=True)
    input_tokens = models.PositiveIntegerField(null=True, blank=True)
    cached_input_tokens = models.PositiveIntegerField(null=True, blank=True)
    output_tokens = models.PositiveIntegerField(null=True, blank=True)
    cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.role}: {self.text[:40]}"
