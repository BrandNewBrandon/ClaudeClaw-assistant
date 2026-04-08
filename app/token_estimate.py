"""Lightweight token estimation without external tokenizer dependencies.

Uses a chars÷4 heuristic which is consistent with the existing
``max_prompt_chars`` approach used elsewhere in the codebase.
"""
from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)
