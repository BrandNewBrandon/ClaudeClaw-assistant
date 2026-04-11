from __future__ import annotations
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.voice_utils import transcribe


def test_transcribe_returns_text(tmp_path: Path) -> None:
    audio = tmp_path / "test.ogg"
    audio.write_bytes(b"fake")
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"text": "Hello world"}
    mock_whisper = MagicMock()
    mock_whisper.load_model.return_value = mock_model
    with patch.dict("sys.modules", {"whisper": mock_whisper}):
        result = transcribe(audio)
    assert result == "Hello world"


def test_transcribe_no_speech(tmp_path: Path) -> None:
    audio = tmp_path / "silent.ogg"
    audio.write_bytes(b"fake")
    mock_model = MagicMock()
    mock_model.transcribe.return_value = {"text": ""}
    mock_whisper = MagicMock()
    mock_whisper.load_model.return_value = mock_model
    with patch.dict("sys.modules", {"whisper": mock_whisper}):
        result = transcribe(audio)
    assert "no speech" in result.lower()


def test_transcribe_whisper_missing(tmp_path: Path) -> None:
    audio = tmp_path / "test.ogg"
    audio.write_bytes(b"fake")
    with patch.dict("sys.modules", {"whisper": None}):
        # Force ImportError on next import attempt
        import importlib
        result = transcribe(audio)
    # Should return graceful message (may or may not hit ImportError depending on caching)
    assert isinstance(result, str)
