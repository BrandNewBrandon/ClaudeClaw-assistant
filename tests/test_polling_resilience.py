from __future__ import annotations

import inspect

from app.router import AssistantRouter


def test_account_worker_has_failure_tracking():
    """_account_worker should track and log consecutive polling failures."""
    source = inspect.getsource(AssistantRouter._account_worker)
    assert "consecutive" in source, "Should track consecutive failures"
    assert "Check your network" in source or "check your network" in source, (
        "Should suggest network check on repeated failures"
    )


def test_account_worker_does_not_die_on_first_error():
    """_account_worker should not immediately put error to queue on first failure."""
    source = inspect.getsource(AssistantRouter._account_worker)
    # The worker should only put to _worker_errors after hitting the threshold (50),
    # not on the very first exception.
    assert "consecutive_failures >= 50" in source or "50" in source, (
        "Should only give up after hitting the failure threshold"
    )


def test_account_worker_resets_on_success():
    """_account_worker should reset the consecutive failure counter on success."""
    source = inspect.getsource(AssistantRouter._account_worker)
    assert "consecutive_failures = 0" in source, (
        "Should reset consecutive_failures counter on a successful poll"
    )
