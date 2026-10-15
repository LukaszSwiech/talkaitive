"""A scripted OpenAI provider on the SDK's HTTP transport.

The real `openai.OpenAI` client runs as in production (its retry loop, its
`Retry-After` handling, its timeouts); only the transport under it is replaced by
`httpx2.MockTransport`. A test queues what the provider does for each next request
(hang, fail with a status, reply) and then checks what happened: the requests the
SDK sent (with their timeouts) and how long the SDK wanted to sleep between them.

Nothing here touches the network, and nothing sleeps: the `fake_provider` fixture
(`tests/conftest.py`) records `time.sleep` instead of sleeping.
"""

import json
from collections.abc import Callable, Sequence
from typing import Any, Self

import httpx2
import openai

from conversations.llm import FoundMistake

# Every successful answer reports this usage, so later tests can rely on the
# numbers (for example to compute the cost of a turn with the configured prices).
USAGE_INPUT_TOKENS = 1200
USAGE_CACHED_INPUT_TOKENS = 1000
USAGE_OUTPUT_TOKENS = 40

Step = Callable[[httpx2.Request], httpx2.Response]


class UnscriptedRequest(AssertionError):
    """The SDK sent a request the scenario did not plan for."""


class FakeProvider:
    """One scenario: what the provider does for each next request, in order.

    Build it with `hang`, `fail`, `reply` and `analysis`; each call queues one or
    more requests' worth of behaviour and returns the provider, so steps chain.
    A request with nothing queued fails the test instead of getting an answer.
    """

    def __init__(self) -> None:
        self._steps: list[Step] = []
        self.requests: list[httpx2.Request] = []
        self.sleeps: list[float] = []
        self.unscripted: list[httpx2.Request] = []

    # --- scenario ---------------------------------------------------------------

    def hang(self, times: int = 1) -> Self:
        """The provider does not answer until the read timeout cuts the request.

        The fake raises `ReadTimeout` at once (what httpx raises once the read
        timeout runs out); `read_timeouts` shows the limit each request carried.
        """
        for _ in range(times):
            self._steps.append(_hang)
        return self

    def fail(self, status: int, *, retry_after: float | None = None) -> Self:
        """An error status, optionally with a `Retry-After` header in seconds."""
        headers = {} if retry_after is None else {"retry-after": _seconds(retry_after)}

        def step(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(
                status,
                headers=headers,
                json={"error": {"message": "fake provider error", "type": "fake"}},
                request=request,
            )

        self._steps.append(step)
        return self

    def reply(self, text: str, *, end_conversation: bool = False) -> Self:
        """A valid agent turn (`AgentTurn`)."""
        return self._answer({"reply": text, "end_conversation": end_conversation})

    def analysis(
        self,
        mistakes: Sequence[FoundMistake] = (),
        learner_facts: Sequence[str] = (),
        scene_notes: Sequence[str] = (),
    ) -> Self:
        """A valid post-conversation analysis (`MistakeReport`)."""
        return self._answer(
            {
                "mistakes": [mistake.model_dump() for mistake in mistakes],
                "learner_facts": list(learner_facts),
                "scene_notes": list(scene_notes),
            }
        )

    # --- what happened ----------------------------------------------------------

    @property
    def read_timeouts(self) -> list[float | None]:
        """The read timeout each request carried, in seconds, in order."""
        return [request.extensions["timeout"]["read"] for request in self.requests]

    # --- wiring (used by the fixture) -------------------------------------------

    def make_client(self, **kwargs: Any) -> openai.OpenAI:
        """A real SDK client with the caller's settings, on the fake transport."""
        http_client = httpx2.Client(transport=httpx2.MockTransport(self._handle))
        return openai.OpenAI(**kwargs, http_client=http_client)

    def record_sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        if not self._steps:
            # Not an httpx error, so the SDK neither retries nor wraps it; the
            # fixture also checks `unscripted` in case a caller swallows it.
            self.unscripted.append(request)
            raise UnscriptedRequest(
                f"Unscripted request #{len(self.requests) + 1}: "
                f"{request.method} {request.url}"
            )
        self.requests.append(request)
        return self._steps.pop(0)(request)

    def _answer(self, payload: dict[str, Any]) -> Self:
        def step(request: httpx2.Request) -> httpx2.Response:
            return httpx2.Response(200, json=_response_body(payload), request=request)

        self._steps.append(step)
        return self


def _hang(request: httpx2.Request) -> httpx2.Response:
    raise httpx2.ReadTimeout("fake provider did not answer", request=request)


def _seconds(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _response_body(payload: dict[str, Any]) -> dict[str, Any]:
    """The smallest Responses API body the SDK parses into `output_parsed`."""
    return {
        "id": "resp_fake",
        "object": "response",
        "created_at": 1_760_000_000,
        "model": "gpt-5.4",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "id": "msg_fake",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                        "type": "output_text",
                        "annotations": [],
                        "text": json.dumps(payload),
                    }
                ],
            }
        ],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "usage": {
            "input_tokens": USAGE_INPUT_TOKENS,
            "input_tokens_details": {"cached_tokens": USAGE_CACHED_INPUT_TOKENS},
            "output_tokens": USAGE_OUTPUT_TOKENS,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": USAGE_INPUT_TOKENS + USAGE_OUTPUT_TOKENS,
        },
    }
