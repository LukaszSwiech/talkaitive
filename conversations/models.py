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
    # Memory block for the prompt, computed once at the start from the user's past
    # conversations and never recomputed, so the cached prompt prefix stays the same
    # for every turn. Empty for conversations from before this field and for a user
    # without memory.
    memory_prompt = models.TextField(blank=True)
    # Copied from the user at the start.
    language = models.CharField(max_length=2, choices=PracticeLanguage)
    status = models.CharField(max_length=10, choices=Status, default=Status.ACTIVE)
    end_reason = models.CharField(max_length=20, choices=EndReason, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    # Set while the model generates the agent's turn, so a refresh shows "Agent is
    # typing" and a parallel retry is refused. It expires on its own (see services).
    agent_turn_started_at = models.DateTimeField(null=True, blank=True)
    # Post-conversation mistake analysis. Set while the analysis runs, so a refresh
    # shows the spinner and a parallel start is refused.
    analysis_started_at = models.DateTimeField(null=True, blank=True)
    # The last failed analysis; the page offers "Try again".
    analysis_failed_at = models.DateTimeField(null=True, blank=True)
    # The analysis finished (also with zero mistakes); it never runs again.
    analyzed_at = models.DateTimeField(null=True, blank=True)
    # Cost of the analysis; counted in the daily budget on the `analyzed_at` day.
    analysis_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    # Notes from the same analysis, for the user's next conversations: short
    # English sentences. `learner_facts` are lasting facts the learner said about
    # themselves (a dog's name, a job); `scene_notes` are about this scene (what was
    # talked about, what the partner asked or said about their own character).
    # Neither ever describes mistakes. Empty for conversations from before these
    # notes, without learner messages, or not analysed yet.
    learner_facts = models.JSONField(default=list, blank=True)
    scene_notes = models.JSONField(default=list, blank=True)

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


class Mistake(UserOwned):
    """One mistake found in a conversation by the post-conversation analysis.

    `user` is always the conversation's user (set by the service).
    """

    class Category(models.TextChoices):
        GRAMMAR = "grammar", "Grammar"
        VOCABULARY = "vocabulary", "Vocabulary"
        WORD_ORDER = "word_order", "Word order"

    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="mistakes"
    )
    # Place on the list, starting at 1.
    position = models.PositiveIntegerField()
    category = models.CharField(max_length=20, choices=Category)
    wrong = models.TextField()
    correct = models.TextField()
    # The user's sentence the mistake comes from.
    sentence = models.TextField()
    explanation = models.TextField()
    # How many times the same mistake appeared in the conversation.
    occurrences = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self) -> str:
        return f"{self.category}: {self.wrong} -> {self.correct}"
