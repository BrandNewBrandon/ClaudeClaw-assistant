"""Tests for structured auto-memory extraction."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.auto_memory import _extract
from app.memory import MemoryStore


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


def test_extract_saves_structured_observation(tmp_path: Path) -> None:
    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    (tmp_path / "agents" / "main" / "memory").mkdir(parents=True)

    response = json.dumps({
        "type": "discovery",
        "title": "User is a data scientist",
        "narrative": "User mentioned they work as a data scientist on climate models.",
        "facts": ["User is a data scientist", "Works on climate models"],
        "concepts": ["user-profile", "career"],
    })

    _extract(
        user_message="I'm a data scientist working on climate models",
        assistant_message="That sounds fascinating!",
        model_runner=FakeRunner(response),
        working_directory=tmp_path,
        memory_store=store,
        agent="main",
    )

    observations = store.load_observations("main")
    assert len(observations) == 1
    assert observations[0].title == "User is a data scientist"
    assert observations[0].type.value == "discovery"


def test_extract_skips_nothing(tmp_path: Path) -> None:
    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    (tmp_path / "agents" / "main" / "memory").mkdir(parents=True)

    _extract(
        user_message="What time is it?",
        assistant_message="It's 3pm.",
        model_runner=FakeRunner("NOTHING"),
        working_directory=tmp_path,
        memory_store=store,
        agent="main",
    )
    assert store.load_observations("main") == []


def test_extract_handles_error(tmp_path: Path) -> None:
    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    (tmp_path / "agents" / "main" / "memory").mkdir(parents=True)

    class ErrorRunner:
        def run_prompt(self, prompt, working_directory, **kwargs):
            raise RuntimeError("model error")

    _extract(
        user_message="Hello",
        assistant_message="Hi",
        model_runner=ErrorRunner(),
        working_directory=tmp_path,
        memory_store=store,
        agent="main",
    )
    assert store.load_observations("main") == []


def test_extract_handles_malformed_json(tmp_path: Path) -> None:
    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    (tmp_path / "agents" / "main" / "memory").mkdir(parents=True)

    _extract(
        user_message="Hello",
        assistant_message="Hi",
        model_runner=FakeRunner("not valid json at all"),
        working_directory=tmp_path,
        memory_store=store,
        agent="main",
    )
    assert store.load_observations("main") == []


def test_extract_deduplicates(tmp_path: Path) -> None:
    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    (tmp_path / "agents" / "main" / "memory").mkdir(parents=True)

    response = json.dumps({
        "type": "discovery",
        "title": "User likes Python",
        "narrative": "User prefers Python for scripting.",
        "facts": ["Prefers Python"],
    })

    for _ in range(3):
        _extract(
            user_message="I love Python",
            assistant_message="Great choice!",
            model_runner=FakeRunner(response),
            working_directory=tmp_path,
            memory_store=store,
            agent="main",
        )

    assert len(store.load_observations("main")) == 1
