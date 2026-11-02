"""Cost per call and a process-safe ledger that keeps the eval under its cap.

promptfoo runs the provider in separate worker processes and has no cost cap of its
own, so every call reserves its worst case in one locked JSON file first, and
settles with what it really cost afterwards. An open reservation counts as spent,
so a crash between the two can only overstate the spend. A call that cost more than
its reservation is recorded at its real cost.

Worst case: input estimated at 1 char/token (a dense-text bound, not the reviewer's
3 chars/token estimate), the highest price the model can be billed at, and the full
`MAX_OUTPUT_TOKENS`. Actual cost: OpenAI by tokens and the registry's prices (the
uncached input of a model with a cache-write price at that price, an upper bound);
OpenRouter by the `usage.cost` it bills, else by tokens at the worst prices.
"""

import fcntl
import json
import os
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts.review.cost import Prices, cost_usd
from scripts.review.eval.models import EvalModel
from scripts.review.run_review import MAX_OUTPUT_TOKENS

# Room for what the reservations cannot see, e.g. rounding in a provider's bill.
SAFETY_MARGIN_USD = Decimal("0.50")
DEFAULT_LEDGER = Path.home() / ".cache" / "talkaitive-review-eval" / "ledger.json"


@dataclass(frozen=True)
class Usage:
    """Token counts of one call; `output_tokens` includes reasoning tokens."""

    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    # What OpenRouter billed (`usage.cost`), when it said.
    billed_usd: Decimal | None = None


def _worst_prices(model: EvalModel) -> Prices:
    return {
        "input": model.worst_input,
        "cached_input": model.worst_input,
        "output": model.worst_output,
    }


def worst_case_usd(model: EvalModel, input_chars: int) -> Decimal:
    """The most one call with `input_chars` of prompt can cost."""
    return cost_usd(_worst_prices(model), input_chars, 0, MAX_OUTPUT_TOKENS)


def _token_cost(model: EvalModel, prices: Prices, usage: Usage) -> Decimal:
    if model.cache_write_input is not None:
        prices = {**prices, "input": model.cache_write_input}
    return cost_usd(
        prices, usage.input_tokens, usage.cached_input_tokens, usage.output_tokens
    )


def actual_cost_usd(model: EvalModel, usage: Usage) -> Decimal:
    """What one call cost: billed by OpenRouter, or priced from its tokens."""
    if model.route == "openai":
        return _token_cost(model, model.prices, usage)
    if usage.billed_usd is not None:
        return usage.billed_usd
    return cost_usd(
        _worst_prices(model),
        usage.input_tokens,
        usage.cached_input_tokens,
        usage.output_tokens,
    )


def regular_cost_usd(model: EvalModel, usage: Usage) -> Decimal:
    """What the call would cost after the intro price ends.

    The actual cost for a model without an intro price. A bill is scaled by the
    ratio of regular to intro token cost, so a regional markup in it stays; without
    a bill, the tokens at the worst prices, which are already regular.
    """
    actual = actual_cost_usd(model, usage)
    if model.regular_prices is None or usage.billed_usd is None:
        return actual
    intro = _token_cost(model, model.prices, usage)
    if intro == 0:
        return actual
    return actual * _token_cost(model, model.regular_prices, usage) / intro


@dataclass(frozen=True)
class Reservation:
    id: str
    amount: Decimal


class LedgerError(Exception):
    """The ledger file is unreadable, or a reservation is not open."""


class Ledger:
    """Spend shared by every process that opens the same file.

    The file holds the open reservations and the settled calls, amounts as decimal
    strings. A sidecar `.lock` file serialises access, and every write replaces the
    file whole, so a crash leaves the old or the new version, never half of one.
    """

    def __init__(self, path: Path, max_usd: Decimal) -> None:
        self.path = path
        self.cap = max_usd - SAFETY_MARGIN_USD
        self._lock_path = path.with_name(path.name + ".lock")

    @contextmanager
    def _locked(self) -> Iterator[dict[str, Any]]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                data = self._read()
                before = json.dumps(data, sort_keys=True)
                yield data
                if json.dumps(data, sort_keys=True) != before:
                    self._write(data)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"open": {}, "settled": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise LedgerError(f"cannot read the ledger {self.path}") from exc
        if not isinstance(data.get("open"), dict) or not isinstance(
            data.get("settled"), list
        ):
            raise LedgerError(f"not a ledger: {self.path}")
        return data

    def _write(self, data: dict[str, Any]) -> None:
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".ledger-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=1, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    @staticmethod
    def _spent(data: dict[str, Any]) -> Decimal:
        settled = sum((Decimal(row["actual"]) for row in data["settled"]), Decimal(0))
        reserved = sum(
            (Decimal(amount) for amount in data["open"].values()), Decimal(0)
        )
        return settled + reserved

    def reserve(self, amount: Decimal) -> Reservation | None:
        """A reservation of `amount`, or None when it would cross the cap."""
        with self._locked() as data:
            if self._spent(data) + amount > self.cap:
                return None
            reservation = Reservation(id=uuid.uuid4().hex, amount=amount)
            data["open"][reservation.id] = str(amount)
            return reservation

    def settle(self, reservation: Reservation, actual: Decimal) -> None:
        """Closes `reservation` at `actual`, even when that is more than reserved."""
        with self._locked() as data:
            if data["open"].pop(reservation.id, None) is None:
                raise LedgerError("the reservation is not open")
            data["settled"].append(
                {
                    "id": reservation.id,
                    "reserved": str(reservation.amount),
                    "actual": str(actual),
                }
            )

    def spent(self) -> Decimal:
        """Settled costs plus open reservations."""
        with self._locked() as data:
            return self._spent(data)

    def remaining(self) -> Decimal:
        return self.cap - self.spent()
