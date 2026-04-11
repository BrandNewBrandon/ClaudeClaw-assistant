"""Voice memo transcription utilities."""
from __future__ import annotations

import logging
from pathlib import Path

LOGGER = logging.getLogger(__name__)


def is_available() -> bool:
    """Check if whisper transcription is available."""
    try:
        import whisper  # noqa: F401
        return True
    except ImportError:
        return False


def transcribe(audio_path: Path, *, model_name: str = "base") -> str:
    """Transcribe an audio file using OpenAI Whisper.

    Returns the transcribed text, or a status message if unavailable.
    """
    try:
        import whisper
    except ImportError:
        return "[Voice memo received but transcription unavailable. Install: pip install openai-whisper]"

    try:
        model = whisper.load_model(model_name)
        result = model.transcribe(str(audio_path))
        text = result.get("text", "").strip()
        if not text:
            return "[Voice memo received but no speech detected]"
        return text
    except Exception as exc:
        LOGGER.exception("Whisper transcription failed")
        return f"[Voice memo transcription failed: {exc}]"
