"""Create or update the local E2E test user from E2E_USERNAME / E2E_PASSWORD.

Playwright's webServer (playwright.config.ts) runs it on every start through
`manage.py shell < tests/e2e/ensure_e2e_user.py`. The app has no sign-up page,
so this is how the user that auth.setup.ts signs in as comes to exist.
"""

import os

from django.conf import settings
from django.contrib.auth import get_user_model

# Never create test users in the dev database or in Postgres on Railway.
database = str(settings.DATABASES["default"]["NAME"])
if not database.endswith("e2e.sqlite3"):
    raise SystemExit(f"Refusing to create the E2E user outside e2e.sqlite3: {database}")

User = get_user_model()
user, _ = User.objects.get_or_create(email=os.environ["E2E_USERNAME"])
user.set_password(os.environ["E2E_PASSWORD"])
user.save()
