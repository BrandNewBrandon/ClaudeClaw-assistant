from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.compaction import SessionCompactor
from app.memory import MemoryStore, TranscriptEntry


@dataclass(frozen=True)
class _FakeResult:
    stdout: str
    stderr: str = ""
    exit_code: int = 0
    session_id: str | None = None


class _FakeRunner:
    """Minimal ModelRunner stand-in."""

    def __init__(self, stdout: str = "Summary of conversation.", *, raise_exc: Exception | None = None) -> None:
        self.stdout = stdout
        self.raise_exc = raise_exc
        self.calls: list[dict[str, Any]] = []

    def ensure_available(self) -> None:
        pass

    def run_prompt(self, prompt: str, working_directory: str | Path, *, model: str | None = None, effort: str | None = None) -> _FakeResult:
        self.calls.append({"prompt": prompt, "effort": effort})
        if self.raise_exc:
            raise self.raise_exc
        return _FakeResult(stdout=self.stdout)


def _make_entries(count: int, chars_each: int = 200) -> list[TranscriptEntry]:
    """Create transcript entries with known text sizes."""
    return [
        TranscriptEntry(
            timestamp=f"2026-04-10T10:{i:02d}:00",
            surface="telegram",
            account_id="primary",
            chat_id="123",
            direction="in" if i % 2 == 0 else "out",
            agent="main",
            message_text="x" * chars_each,
            metadata={},
        )
        for i in range(count)
    ]


def test_maybe_compact_returns_false_when_under_threshold(tmp_path: Path) -> None:
    """Short transcript stays below threshold — no compaction."""
    memory = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    runner = _FakeRunner()

    # Write a small transcript that won't exceed threshold
    tpath = memory.transcript_path("telegram", "123", account_id="primary")
    tpath.parent.mkdir(parents=True, exist_ok=True)
    tpath.write_text("", encoding="utf-8")

    compactor = SessionCompactor(memory, runner, token_budget=12_000)
    result = compactor.maybe_compact("telegram", "123", "main")

    assert result is False
    assert len(runner.calls) == 0  # Model was never called


def test_maybe_compact_performs_compaction_when_over_threshold(tmp_path: Path, monkeypatch: Any) -> None:
    """When transcript exceeds threshold, compaction runs and returns True."""
    memory = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    runner = _FakeRunner(stdout="Summarized conversation about routing.")

    # Create entries that exceed the threshold
    # Budget=100, ratio=0.8 → threshold=80 tokens → 320 chars
    entries = _make_entries(10, chars_each=100)  # 10*100=1000 chars → 250 tokens

    monkeypatch.setattr(
        memory, "read_transcript_with_compaction",
        lambda surface, chat_id, account_id="primary": (None, entries),
    )

    appended: list[dict[str, Any]] = []
    original_append = memory.append_compaction_summary

    def fake_append(**kwargs: Any) -> None:
        appended.append(kwargs)

    monkeypatch.setattr(memory, "append_compaction_summary", fake_append)

    compactor = SessionCompactor(memory, runner, token_budget=100, trigger_ratio=0.8)
    result = compactor.maybe_compact("telegram", "123", "main")

    assert result is True
    assert len(runner.calls) == 1
    assert runner.calls[0]["effort"] == "low"
    assert len(appended) == 1
    assert appended[0]["summary_text"] == "Summarized conversation about routing."
    assert appended[0]["compacted_count"] == 6  # 60% of 10


def test_maybe_compact_returns_false_on_model_exception(tmp_path: Path, monkeypatch: Any) -> None:
    """Model failure is caught gracefully."""
    memory = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    runner = _FakeRunner(raise_exc=RuntimeError("API down"))

    entries = _make_entries(10, chars_each=100)
    monkeypatch.setattr(
        memory, "read_transcript_with_compaction",
        lambda surface, chat_id, account_id="primary": (None, entries),
    )

    compactor = SessionCompactor(memory, runner, token_budget=100, trigger_ratio=0.8)
    result = compactor.maybe_compact("telegram", "123", "main")

    assert result is False


def test_maybe_compact_returns_false_on_empty_summary(tmp_path: Path, monkeypatch: Any) -> None:
    """Empty model output is treated as a failure."""
    memory = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    runner = _FakeRunner(stdout="   ")

    entries = _make_entries(10, chars_each=100)
    monkeypatch.setattr(
        memory, "read_transcript_with_compaction",
        lambda surface, chat_id, account_id="primary": (None, entries),
    )

    compactor = SessionCompactor(memory, runner, token_budget=100, trigger_ratio=0.8)
    result = compactor.maybe_compact("telegram", "123", "main")

    assert result is False


def test_maybe_compact_includes_previous_summary_in_prompt(tmp_path: Path, monkeypatch: Any) -> None:
    """When a prior compaction summary exists, it's included in the prompt."""
    memory = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    runner = _FakeRunner(stdout="Updated summary.")

    entries = _make_entries(10, chars_each=100)
    monkeypatch.setattr(
        memory, "read_transcript_with_compaction",
        lambda surface, chat_id, account_id="primary": ("Previous summary here.", entries),
    )
    monkeypatch.setattr(memory, "append_compaction_summary", lambda **kw: None)

    compactor = SessionCompactor(memory, runner, token_budget=100, trigger_ratio=0.8)
    compactor.maybe_compact("telegram", "123", "main")

    prompt_sent = runner.calls[0]["prompt"]
    assert "Previous summary here." in prompt_sent
    assert "[Previous conversation summary:]" in prompt_sent
