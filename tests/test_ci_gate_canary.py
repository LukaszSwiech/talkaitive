"""Temporary CI gate canary, removed by the next (revert) commit.

Proves that Railway "Wait for CI" skips the deploy when the CI workflow fails
(change testing-suite-trust-and-ci, phase 2).
"""

import pytest


def test_ci_gate_canary() -> None:
    pytest.fail("CI gate canary")
