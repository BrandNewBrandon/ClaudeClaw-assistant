"""Tests for automatic memory extraction."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.auto_memory import _extract


@dataclass
class FakeResult:
    stdout: str
    stderr: str = ""
    exit_code: int = 0
    session_id: str | None = None


class FakeRunner:
    def __init__(self, response: str):
        self._response = response

    def run_prompt(self, prompt, working_directory, **kwargs):
        return FakeResult(stdout=self._response)


def test_extract_saves_facts(tmp_path: Path) -> None:
    notes_dir = tmp_path / "memory"
    _extract(
        user_message="I'm a data scientist working on climate models",
        assistant_message="That sounds fascinating!",
        model_runner=FakeRunner("- User is a data scientist\n- Works on climate models"),
        working_directory=tmp_path,
        notes_dir=notes_dir,
    )
    files = list(notes_dir.glob("*.md"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "data scientist" in content
    assert "climate models" in content


def test_extract_skips_nothing(tmp_path: Path) -> None:
    notes_dir = tmp_path / "memory"
    _extract(
        user_message="What time is it?",
        assistant_message="It's 3pm.",
        model_runner=FakeRunner("NOTHING"),
        working_directory=tmp_path,
        notes_dir=notes_dir,
    )
    assert not notes_dir.exists() or not list(notes_dir.glob("*.md"))


def test_extract_handles_error(tmp_path: Path) -> None:
    notes_dir = tmp_path / "memory"

    class ErrorRunner:
        def run_prompt(self, prompt, working_directory, **kwargs):
            raise RuntimeError("model error")

    # Should not raise
    _extract(
        user_message="Hello",
        assistant_message="Hi",
        model_runner=ErrorRunner(),
        working_directory=tmp_path,
        notes_dir=notes_dir,
    )
    assert not notes_dir.exists() or not list(notes_dir.glob("*.md"))


def test_extract_skips_empty(tmp_path: Path) -> None:
    notes_dir = tmp_path / "memory"
    _extract(
        user_message="Hi",
        assistant_message="Hello",
        model_runner=FakeRunner(""),
        working_directory=tmp_path,
        notes_dir=notes_dir,
    )
    assert not notes_dir.exists() or not list(notes_dir.glob("*.md"))
