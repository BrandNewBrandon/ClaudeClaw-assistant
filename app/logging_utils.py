from __future__ import annotations

import logging
import re
from pathlib import Path

from .app_paths import ensure_runtime_dirs, get_logs_file


# Patterns that look like secrets — redact them from log output
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    # Telegram bot tokens: 1234567890:AAH...
    re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{30,}\b"),
    # Discord bot tokens: base64-ish with dots
    re.compile(r"\b[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{27,}\b"),
    # Slack tokens: xoxb-, xoxp-, xapp-
    re.compile(r"\bxo(?:xb|xp|xa(?:pp))-[A-Za-z0-9-]{20,}\b"),
    # Generic long hex/base64 strings that look like API keys (40+ chars)
    re.compile(r"\b(?:sk-|key-|token-)[A-Za-z0-9_-]{32,}\b"),
    # Bearer tokens in log lines
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9_-]{20,}"),
]

_REDACTED = "***REDACTED***"


class _RedactionFilter(logging.Filter):
    """Logging filter that replaces secret-looking strings with ***REDACTED***."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _redact(str(v)) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(_redact(str(a)) if isinstance(a, str) else a for a in record.args)
        return True


def _redact(text: str) -> str:
    """Replace secret-looking patterns in text."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


def configure_logging(_shared_dir: Path) -> None:
    ensure_runtime_dirs()
    log_path = get_logs_file()

    redaction_filter = _RedactionFilter()

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.addFilter(redaction_filter)

    stream_handler = logging.StreamHandler()
    stream_handler.addFilter(redaction_filter)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[file_handler, stream_handler],
    )
