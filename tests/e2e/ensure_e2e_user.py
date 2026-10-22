"""Create or update the local E2E test user from E2E_USERNAME / E2E_PASSWORD.

Playwright's webServer (playwright.config.ts) runs it on every start through
`manage.py shell < tests/e2e/ensure_e2e_user.py`. The app has no sign-up page,
so this is how the user that auth.setup.ts signs in as comes to exist.

It also deletes the user's conversations and paid-call ledger, so every server
start begins with home showing the topic list: no active conversation and no
spent daily budget (ui-home.spec.ts takes screenshots of that state).
"""

import os

from django.conf import settings
from django.contrib.auth import get_user_model

from conversations.models import Conversation, LLMCharge

# Never create test users or delete data in the dev database or in Postgres on Railway.
database = str(settings.DATABASES["default"]["NAME"])
if not database.endswith("e2e.sqlite3"):
    raise SystemExit(f"Refusing to create the E2E user outside e2e.sqlite3: {database}")

User = get_user_model()
user, _ = User.objects.get_or_create(email=os.environ["E2E_USERNAME"])
user.set_password(os.environ["E2E_PASSWORD"])
user.save()

# Messages and mistakes go with their conversation (CASCADE).
LLMCharge.objects.for_user(user).delete()
Conversation.objects.for_user(user).delete()
