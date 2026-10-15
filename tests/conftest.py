import time
from collections.abc import Iterator

import pytest

from conversations import llm
from tests.fake_provider import FakeProvider


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeProvider]:
    """A scripted provider under the real SDK client; see `tests/fake_provider.py`.

    `llm._get_client` still builds the client from Django settings (key, base URL,
    timeout, retries); the fixture only adds the fake transport. `time.sleep` is
    recorded, not slept, so the SDK's retry loop runs at full speed and the test
    sees how long it wanted to wait.
    """
    provider = FakeProvider()
    monkeypatch.setattr(llm, "OpenAI", provider.make_client)
    monkeypatch.setattr(time, "sleep", provider.record_sleep)
    yield provider
    if provider.unscripted:
        pytest.fail(
            f"{len(provider.unscripted)} request(s) reached the fake provider with "
            "nothing queued for them."
        )
