"""Utility for masking sensitive values in logs and output."""
from __future__ import annotations


def mask_token(value: str | None, *, visible_chars: int = 4) -> str:
    """Mask a sensitive string, showing only the last few characters.

    Returns '(not set)' for None/empty, 'xxxx...last4' for values.
    """
    if not value:
        return "(not set)"
    if len(value) <= visible_chars:
        return "****"
    return "****..." + value[-visible_chars:]
