"""Transcript file rotation — archive old entries to prevent unbounded growth."""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

LOGGER = logging.getLogger(__name__)

MAX_LINES = 5000  # Rotate when transcript exceeds this many lines
KEEP_LINES = 2000  # Keep this many recent lines after rotation


def rotate_transcript(path: Path) -> bool:
    """Rotate a transcript file if it exceeds MAX_LINES.

    Moves the full file to {name}.archive.jsonl and keeps
    only the last KEEP_LINES in the original file.

    Returns True if rotation occurred.
    """
    if not path.exists():
        return False

    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) <= MAX_LINES:
        return False

    # Archive old entries
    old_entries = "\n".join(lines[:-KEEP_LINES]) + "\n"
    archive_path = path.with_suffix(".archive.jsonl")

    try:
        if archive_path.exists():
            with archive_path.open("a", encoding="utf-8") as f:
                f.write(old_entries)
        else:
            archive_path.write_text(old_entries, encoding="utf-8")
    except OSError as exc:
        LOGGER.error("Failed to write archive %s: %s — skipping rotation", archive_path, exc)
        return False

    # Only truncate original AFTER archive write succeeded
    try:
        path.write_text("\n".join(lines[-KEEP_LINES:]) + "\n", encoding="utf-8")
    except OSError as exc:
        LOGGER.error("Failed to truncate %s after archiving: %s", path, exc)
        return False

    LOGGER.info("Rotated transcript %s: %d → %d lines (%d archived)",
                path.name, len(lines), KEEP_LINES, len(lines) - KEEP_LINES)
    return True


def rotate_all_transcripts(transcript_dir: Path) -> int:
    """Rotate all transcript files in a directory. Returns count of rotated files."""
    if not transcript_dir.exists():
        return 0
    count = 0
    for path in sorted(transcript_dir.glob("*.jsonl")):
        if path.name.endswith(".archive.jsonl"):
            continue
        if rotate_transcript(path):
            count += 1
    return count
