# Smart Memory Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade ClaudeClaw's memory system with structured observations, token-budgeted injection, content deduplication, and structured session summaries — inspired by claude-mem's architecture but adapted to our file-first, no-new-dependencies approach.

**Architecture:** Four improvements to the existing memory pipeline: (1) Replace free-form auto-extraction with typed observations containing metadata, (2) Add token estimation to context injection so memory fits a budget instead of a fixed count, (3) Add content-hash deduplication to prevent redundant memory storage, (4) Replace raw bullet consolidation with structured session summaries.

**Tech Stack:** Python 3.12, existing fastembed/numpy for embeddings, no new dependencies.

---

### File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app/observations.py` | **Create** | Observation dataclass, types, serialization, dedup |
| `app/auto_memory.py` | **Modify** | Replace free-form extraction with structured observation extraction |
| `app/memory.py` | **Modify** | Add observation storage/retrieval, dedup on write, structured consolidation |
| `app/context_builder.py` | **Modify** | Token-budgeted injection replacing fixed top-4 |
| `app/embeddings.py` | **Modify** | Index observations with typed metadata |
| `app/config.py` | **Modify** | Add `memory_token_budget` config knob |
| `app/router.py` | **Modify** | Pass token budget to context builder |
| `tests/test_observations.py` | **Create** | Tests for observation model, serialization, dedup |
| `tests/test_auto_memory.py` | **Modify** | Update tests for structured extraction |
| `tests/test_memory.py` | **Modify** | Add tests for observation storage, dedup, structured consolidation |
| `tests/test_context_builder.py` | **Modify** | Add tests for token-budgeted injection |

---

### Task 1: Observation Data Model

**Files:**
- Create: `app/observations.py`
- Create: `tests/test_observations.py`

- [ ] **Step 1: Write the test file for observations**

```python
# tests/test_observations.py
from __future__ import annotations

from app.observations import Observation, ObservationType, observation_from_dict, observation_to_dict


def test_observation_roundtrip():
    obs = Observation(
        type=ObservationType.DECISION,
        title="Use file-first storage",
        narrative="Decided to keep flat files instead of adding SQLite.",
        facts=["No new dependencies", "Simpler backup story"],
        concepts=["architecture", "storage"],
        files_read=["app/memory.py"],
        files_modified=[],
    )
    d = observation_to_dict(obs)
    restored = observation_from_dict(d)
    assert restored.type == ObservationType.DECISION
    assert restored.title == obs.title
    assert restored.narrative == obs.narrative
    assert restored.facts == obs.facts
    assert restored.concepts == obs.concepts
    assert restored.files_read == obs.files_read


def test_observation_content_hash_stable():
    obs = Observation(
        type=ObservationType.BUGFIX,
        title="Fix auth timeout",
        narrative="Increased timeout from 30s to 120s.",
        facts=["Timeout was too short for slow networks"],
    )
    h1 = obs.content_hash
    h2 = obs.content_hash
    assert h1 == h2
    assert len(h1) == 16


def test_observation_content_hash_differs_on_content_change():
    obs1 = Observation(type=ObservationType.BUGFIX, title="Fix A", narrative="narrative A")
    obs2 = Observation(type=ObservationType.BUGFIX, title="Fix B", narrative="narrative B")
    assert obs1.content_hash != obs2.content_hash


def test_observation_content_hash_ignores_timestamp():
    obs1 = Observation(type=ObservationType.FEATURE, title="Add X", narrative="Added X", timestamp="2026-04-12T10:00:00")
    obs2 = Observation(type=ObservationType.FEATURE, title="Add X", narrative="Added X", timestamp="2026-04-12T11:00:00")
    assert obs1.content_hash == obs2.content_hash


def test_observation_to_markdown():
    obs = Observation(
        type=ObservationType.DISCOVERY,
        title="Memory system uses embeddings",
        narrative="Found that fastembed powers the semantic search.",
        facts=["Uses BAAI/bge-small-en-v1.5", "384-dim vectors"],
        concepts=["memory", "embeddings"],
        files_read=["app/embeddings.py"],
    )
    md = obs.to_markdown()
    assert "**discovery**" in md
    assert "Memory system uses embeddings" in md
    assert "fastembed" in md
    assert "BAAI/bge-small-en-v1.5" in md


def test_observation_token_estimate():
    short = Observation(type=ObservationType.CHANGE, title="Short", narrative="x")
    long = Observation(
        type=ObservationType.FEATURE,
        title="Long observation",
        narrative="A " * 500,
        facts=["fact " * 20] * 5,
    )
    assert short.estimated_tokens < long.estimated_tokens
    assert short.estimated_tokens > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_observations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.observations'`

- [ ] **Step 3: Implement the observations module**

```python
# app/observations.py
"""Structured observation model for memory storage.

Observations are typed, structured records extracted from conversations.
Each has a content hash for deduplication and a token estimate for
budget-aware context injection.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ObservationType(Enum):
    DECISION = "decision"
    BUGFIX = "bugfix"
    FEATURE = "feature"
    REFACTOR = "refactor"
    DISCOVERY = "discovery"
    CHANGE = "change"


@dataclass
class Observation:
    type: ObservationType
    title: str
    narrative: str
    facts: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().astimezone().isoformat())

    @property
    def content_hash(self) -> str:
        """16-char SHA256 hash of content fields (excludes timestamp)."""
        content = f"{self.type.value}|{self.title}|{self.narrative}|{'|'.join(self.facts)}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    @property
    def estimated_tokens(self) -> int:
        """Rough token estimate (~4 chars per token)."""
        text = self.to_markdown()
        return max(1, len(text) // 4)

    def to_markdown(self) -> str:
        """Render as compact markdown for prompt injection."""
        lines = [f"**{self.type.value}**: {self.title}"]
        if self.narrative:
            lines.append(self.narrative)
        if self.facts:
            for fact in self.facts:
                lines.append(f"  - {fact}")
        tags = []
        if self.concepts:
            tags.append(f"concepts: {', '.join(self.concepts)}")
        if self.files_read:
            tags.append(f"read: {', '.join(self.files_read)}")
        if self.files_modified:
            tags.append(f"modified: {', '.join(self.files_modified)}")
        if tags:
            lines.append(f"  [{' | '.join(tags)}]")
        return "\n".join(lines)


def observation_to_dict(obs: Observation) -> dict[str, Any]:
    return {
        "type": obs.type.value,
        "title": obs.title,
        "narrative": obs.narrative,
        "facts": obs.facts,
        "concepts": obs.concepts,
        "files_read": obs.files_read,
        "files_modified": obs.files_modified,
        "timestamp": obs.timestamp,
        "content_hash": obs.content_hash,
    }


def observation_from_dict(d: dict[str, Any]) -> Observation:
    return Observation(
        type=ObservationType(d["type"]),
        title=d["title"],
        narrative=d["narrative"],
        facts=d.get("facts", []),
        concepts=d.get("concepts", []),
        files_read=d.get("files_read", []),
        files_modified=d.get("files_modified", []),
        timestamp=d.get("timestamp", ""),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_observations.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/observations.py tests/test_observations.py
git commit -m "feat: add structured observation data model with content hashing and token estimation"
```

---

### Task 2: Observation Storage with Deduplication

**Files:**
- Modify: `app/memory.py` (add `store_observation`, `load_observations`, dedup logic)
- Modify: `tests/test_memory.py` (add observation storage tests)

- [ ] **Step 1: Write tests for observation storage and dedup**

Append to `tests/test_memory.py`:

```python
from app.observations import Observation, ObservationType


def test_store_observation_writes_jsonl(tmp_path: Path) -> None:
    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    (tmp_path / "agents" / "main" / "memory").mkdir(parents=True)

    obs = Observation(
        type=ObservationType.DECISION,
        title="Use flat files",
        narrative="Decided to keep flat file storage.",
        facts=["Simple", "No deps"],
    )
    stored = store.store_observation("main", obs)
    assert stored is True

    observations = store.load_observations("main")
    assert len(observations) == 1
    assert observations[0].title == "Use flat files"


def test_store_observation_deduplicates(tmp_path: Path) -> None:
    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    (tmp_path / "agents" / "main" / "memory").mkdir(parents=True)

    obs = Observation(
        type=ObservationType.BUGFIX,
        title="Fix timeout",
        narrative="Increased timeout.",
    )
    assert store.store_observation("main", obs) is True
    assert store.store_observation("main", obs) is False  # duplicate

    observations = store.load_observations("main")
    assert len(observations) == 1


def test_store_observation_allows_different_content(tmp_path: Path) -> None:
    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    (tmp_path / "agents" / "main" / "memory").mkdir(parents=True)

    obs1 = Observation(type=ObservationType.FEATURE, title="Add A", narrative="Added A")
    obs2 = Observation(type=ObservationType.FEATURE, title="Add B", narrative="Added B")
    assert store.store_observation("main", obs1) is True
    assert store.store_observation("main", obs2) is True

    observations = store.load_observations("main")
    assert len(observations) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_memory.py::test_store_observation_writes_jsonl tests/test_memory.py::test_store_observation_deduplicates tests/test_memory.py::test_store_observation_allows_different_content -v`
Expected: FAIL — `AttributeError: 'MemoryStore' object has no attribute 'store_observation'`

- [ ] **Step 3: Implement observation storage in memory.py**

Add these imports at the top of `app/memory.py`:

```python
from .observations import Observation, observation_from_dict, observation_to_dict
```

Add these methods to the `MemoryStore` class:

```python
    def _observations_path(self, agent: str) -> Path:
        return self._agents_dir / agent / "memory" / "observations.jsonl"

    def store_observation(self, agent: str, obs: Observation) -> bool:
        """Store an observation. Returns False if duplicate (same content_hash)."""
        path = self._observations_path(agent)
        path.parent.mkdir(parents=True, exist_ok=True)
        content_hash = obs.content_hash

        # Check for duplicates
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    existing = json.loads(line)
                    if existing.get("content_hash") == content_hash:
                        return False
                except json.JSONDecodeError:
                    continue

        with self._write_lock:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(observation_to_dict(obs), ensure_ascii=False) + "\n")

        # Update embedding index
        try:
            index = self._get_embedding_index(agent)
            index.add_snippet("observation", obs.to_markdown())
        except Exception:
            pass

        return True

    def load_observations(self, agent: str, *, limit: int = 0) -> list[Observation]:
        """Load observations from JSONL. Returns newest first. limit=0 means all."""
        path = self._observations_path(agent)
        if not path.exists():
            return []

        observations: list[Observation] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                observations.append(observation_from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, ValueError):
                LOGGER.warning("Skipping malformed observation in %s", path)

        observations.reverse()  # newest first
        if limit > 0:
            observations = observations[:limit]
        return observations
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_memory.py -v`
Expected: All tests PASS (including original tests)

- [ ] **Step 5: Commit**

```bash
git add app/memory.py tests/test_memory.py
git commit -m "feat: add observation storage with content-hash deduplication"
```

---

### Task 3: Structured Auto-Memory Extraction

**Files:**
- Modify: `app/auto_memory.py` (extract structured observations instead of free-form bullets)
- Modify: `tests/test_auto_memory.py` (update tests)
- Modify: `app/router.py` (pass MemoryStore to extraction)

- [ ] **Step 1: Write updated tests**

Replace `tests/test_auto_memory.py` contents:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_auto_memory.py -v`
Expected: FAIL — signature mismatch (missing `memory_store` / `agent` params)

- [ ] **Step 3: Rewrite auto_memory.py**

Replace `app/auto_memory.py` with:

```python
"""Automatic memory extraction from conversations.

After each exchange, asynchronously asks Claude to extract a structured
observation (typed, with facts/concepts/files) and stores it via MemoryStore.

Enabled via ``auto_memory: true`` in config.json. Uses low effort to minimize cost.
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .memory import MemoryStore

LOGGER = logging.getLogger(__name__)

_EXTRACT_PROMPT = (
    "Below is a conversation exchange. Extract ONLY information worth "
    "remembering across future conversations.\n\n"
    "Be extremely selective — most messages contain nothing worth saving. "
    "If nothing is worth saving, return exactly: NOTHING\n\n"
    "If there IS something worth saving, return a single JSON object with these fields:\n"
    '  "type": one of "decision", "bugfix", "feature", "refactor", "discovery", "change"\n'
    '  "title": short title (under 60 chars)\n'
    '  "narrative": one sentence describing what happened\n'
    '  "facts": list of concise fact strings (3 max)\n'
    '  "concepts": list of topic tags (3 max)\n\n'
    "Return ONLY the JSON object or the word NOTHING. No other text.\n\n"
    "User: {user_message}\n\n"
    "Assistant: {assistant_message}"
)


def extract_and_save(
    user_message: str,
    assistant_message: str,
    *,
    model_runner: Any,
    working_directory: Path,
    memory_store: MemoryStore,
    agent: str,
) -> None:
    """Run memory extraction in a background thread (fire-and-forget)."""
    thread = threading.Thread(
        target=_extract,
        kwargs={
            "user_message": user_message,
            "assistant_message": assistant_message,
            "model_runner": model_runner,
            "working_directory": working_directory,
            "memory_store": memory_store,
            "agent": agent,
        },
        name="auto-memory",
        daemon=True,
    )
    thread.start()


def _extract(
    *,
    user_message: str,
    assistant_message: str,
    model_runner: Any,
    working_directory: Path,
    memory_store: MemoryStore,
    agent: str,
) -> None:
    """Extract a structured observation and store it. Runs in background thread."""
    from .observations import Observation, ObservationType

    prompt = _EXTRACT_PROMPT.format(
        user_message=user_message[:2000],
        assistant_message=assistant_message[:2000],
    )

    try:
        result = model_runner.run_prompt(
            prompt=prompt,
            working_directory=working_directory,
            effort="low",
        )
        raw = result.stdout.strip()
    except Exception:
        LOGGER.exception("Auto-memory extraction failed")
        return

    if not raw or raw.upper() == "NOTHING":
        return

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        LOGGER.debug("Auto-memory: model returned non-JSON: %s", raw[:200])
        return

    try:
        obs = Observation(
            type=ObservationType(data.get("type", "discovery")),
            title=data.get("title", ""),
            narrative=data.get("narrative", ""),
            facts=data.get("facts", []),
            concepts=data.get("concepts", []),
            files_read=data.get("files_read", []),
            files_modified=data.get("files_modified", []),
        )
    except (ValueError, TypeError) as exc:
        LOGGER.debug("Auto-memory: failed to parse observation: %s", exc)
        return

    if not obs.title:
        return

    stored = memory_store.store_observation(agent, obs)
    if stored:
        LOGGER.info("Auto-memory: stored observation '%s' for agent=%s", obs.title, agent)
    else:
        LOGGER.debug("Auto-memory: duplicate observation '%s' skipped", obs.title)
```

- [ ] **Step 4: Update router.py call site**

In `app/router.py`, find the auto_memory block (around line 910) and change it from:

```python
        if self._config.auto_memory and reply and not is_silent:
            try:
                from .auto_memory import extract_and_save
                agent_notes_dir = self._config.agents_dir / active_agent / "memory"
                extract_and_save(
                    message.text or "",
                    reply,
                    model_runner=self._model_runner,
                    working_directory=self._config.project_root,
                    notes_dir=agent_notes_dir,
                )
            except Exception:
                LOGGER.debug("Auto-memory dispatch failed", exc_info=True)
```

To:

```python
        if self._config.auto_memory and reply and not is_silent:
            try:
                from .auto_memory import extract_and_save
                extract_and_save(
                    message.text or "",
                    reply,
                    model_runner=self._model_runner,
                    working_directory=self._config.project_root,
                    memory_store=self._memory,
                    agent=active_agent,
                )
            except Exception:
                LOGGER.debug("Auto-memory dispatch failed", exc_info=True)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_auto_memory.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add app/auto_memory.py app/router.py tests/test_auto_memory.py
git commit -m "feat: structured observation extraction replacing free-form auto-memory"
```

---

### Task 4: Token-Budgeted Context Injection

**Files:**
- Modify: `app/context_builder.py` (replace fixed top-4 with token budget)
- Modify: `app/config.py` (add `memory_token_budget`)
- Modify: `app/memory.py` (add `find_relevant_memory_budgeted`)
- Modify: `tests/test_context_builder.py` (test budgeted injection)
- Modify: `tests/test_memory.py` (test budgeted retrieval)

- [ ] **Step 1: Write test for budgeted memory retrieval**

Append to `tests/test_memory.py`:

```python
def test_find_relevant_memory_budgeted_respects_token_limit(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    agent_dir = agents_dir / "main"
    memory_dir = agent_dir / "memory"
    memory_dir.mkdir(parents=True)

    # Write observations of varying sizes
    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=agents_dir)
    for i in range(10):
        obs = Observation(
            type=ObservationType.DISCOVERY,
            title=f"Fact {i}",
            narrative=f"This is fact number {i} with some detail. " * 5,
            facts=[f"detail {i}"],
        )
        store.store_observation("main", obs)

    # With a tiny budget, should get fewer results
    small = store.find_relevant_memory_budgeted("main", "fact", token_budget=100)
    large = store.find_relevant_memory_budgeted("main", "fact", token_budget=2000)
    assert len(small) < len(large)
    assert len(small) >= 1


def test_find_relevant_memory_budgeted_returns_empty_when_no_observations(tmp_path: Path) -> None:
    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=tmp_path / "agents")
    result = store.find_relevant_memory_budgeted("main", "anything", token_budget=1000)
    assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_memory.py::test_find_relevant_memory_budgeted_respects_token_limit tests/test_memory.py::test_find_relevant_memory_budgeted_returns_empty_when_no_observations -v`
Expected: FAIL — `AttributeError: 'MemoryStore' object has no attribute 'find_relevant_memory_budgeted'`

- [ ] **Step 3: Implement budgeted retrieval in memory.py**

Add this method to `MemoryStore`:

```python
    def find_relevant_memory_budgeted(
        self,
        agent: str,
        query: str,
        *,
        token_budget: int = 800,
        semantic: bool = True,
    ) -> list[str]:
        """Find relevant memory snippets that fit within a token budget.

        Returns observation markdown strings, most relevant first, until
        the budget is exhausted. Falls back to the original find_relevant_memory
        if no observations exist.
        """
        observations = self.load_observations(agent)
        if not observations:
            # Fall back to legacy snippet search
            return self.find_relevant_memory(agent, query, limit=4, semantic=semantic)

        # Get ranked candidates — use semantic search if available, else all observations
        candidates: list[str] = []
        if semantic:
            try:
                index = self._get_embedding_index(agent)
                if index.size > 0:
                    # Get more candidates than we might need
                    candidates = index.query(query, limit=20)
            except Exception:
                pass

        if not candidates:
            # Keyword fallback: rank observations by keyword overlap
            query_terms = self._keyword_terms(query)
            scored: list[tuple[int, Observation]] = []
            for obs in observations:
                text = obs.to_markdown().lower()
                score = sum(1 for t in query_terms if t in text)
                if score > 0:
                    scored.append((score, obs))
            scored.sort(key=lambda x: -x[0])
            candidates = [obs.to_markdown() for _, obs in scored]

        # Fill budget
        result: list[str] = []
        tokens_used = 0
        for snippet in candidates:
            est = max(1, len(snippet) // 4)
            if tokens_used + est > token_budget and result:
                break
            result.append(snippet)
            tokens_used += est

        return result
```

- [ ] **Step 4: Add config knob**

In `app/config.py`, add to the `AppConfig` dataclass (after `auto_memory`):

```python
    # Token budget for relevant memory injection
    memory_token_budget: int = 800
```

In `load_config()`, add to the return statement:

```python
        memory_token_budget=int(raw.get("memory_token_budget", 800)),
```

- [ ] **Step 5: Write test for token-budgeted injection in context builder**

Append to `tests/test_context_builder.py`:

```python
def test_format_relevant_memory_respects_content(tmp_path: Path) -> None:
    """Relevant memory block renders all provided snippets."""
    builder = ContextBuilder(tmp_path)
    snippets = [
        "**decision**: Use flat files\nKeep it simple.",
        "**discovery**: User prefers terse output\nNo essays.",
    ]
    result = builder._format_relevant_memory(snippets)
    assert "flat files" in result
    assert "terse output" in result
```

- [ ] **Step 6: Update router.py to use budgeted retrieval**

In `app/router.py`, find the `find_relevant_memory` call (around line 790) and change:

```python
            relevant_memory = self._memory.find_relevant_memory(
                active_agent,
                message.text,
                limit=4,
                semantic=self._config.semantic_search_enabled,
            )
```

To:

```python
            relevant_memory = self._memory.find_relevant_memory_budgeted(
                active_agent,
                message.text,
                token_budget=self._config.memory_token_budget,
                semantic=self._config.semantic_search_enabled,
            )
```

Also update the command handler's memory preview call (around line 660) similarly:

```python
            memory_preview = self._memory.find_relevant_memory_budgeted(
                active_agent,
                message.text,
                token_budget=self._config.memory_token_budget,
                semantic=self._config.semantic_search_enabled,
            )
```

- [ ] **Step 7: Run all tests**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_memory.py tests/test_context_builder.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add app/memory.py app/config.py app/context_builder.py app/router.py tests/test_memory.py tests/test_context_builder.py
git commit -m "feat: token-budgeted memory injection replacing fixed top-4 limit"
```

---

### Task 5: Structured Session Summaries in Consolidation

**Files:**
- Modify: `app/memory.py` (`consolidate_agent_notes` method)
- Modify: `tests/test_memory.py` (test structured consolidation)

- [ ] **Step 1: Write test for structured consolidation**

Append to `tests/test_memory.py`:

```python
import json as _json

def test_consolidate_produces_structured_summary(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    memory_dir = agents_dir / "main" / "memory"
    memory_dir.mkdir(parents=True)

    # Create an old daily note
    from datetime import datetime, timedelta
    old_date = (datetime.now().astimezone() - timedelta(days=5)).strftime("%Y-%m-%d")
    (memory_dir / f"{old_date}.md").write_text(
        "## 10:00\nUser: How do I add multi-account?\n\nAssistant: You need to...",
        encoding="utf-8",
    )

    structured_response = _json.dumps({
        "request": "How to add multi-account support",
        "learned": "User needs multi-account routing for Telegram",
        "completed": "Explained the multi-account architecture",
        "next_steps": "User may implement multi-account routing next",
    })

    class FakeRunner:
        def run_prompt(self, prompt, working_directory, **kwargs):
            from dataclasses import dataclass
            @dataclass
            class R:
                stdout: str
                stderr: str = ""
                exit_code: int = 0
                session_id: str | None = None
            return R(stdout=structured_response)

    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=agents_dir)
    result = store.consolidate_agent_notes(
        "main", FakeRunner(), tmp_path, keep_days=3
    )

    assert "Consolidated" in result
    memory_content = (agents_dir / "main" / "MEMORY.md").read_text(encoding="utf-8")
    assert "multi-account" in memory_content.lower()
    assert "Learned" in memory_content or "learned" in memory_content


def test_consolidate_falls_back_on_non_json(tmp_path: Path) -> None:
    """If the model returns plain bullets instead of JSON, still works."""
    agents_dir = tmp_path / "agents"
    memory_dir = agents_dir / "main" / "memory"
    memory_dir.mkdir(parents=True)

    from datetime import datetime, timedelta
    old_date = (datetime.now().astimezone() - timedelta(days=5)).strftime("%Y-%m-%d")
    (memory_dir / f"{old_date}.md").write_text("## Old note\nSome conversation.", encoding="utf-8")

    class FakeRunner:
        def run_prompt(self, prompt, working_directory, **kwargs):
            from dataclasses import dataclass
            @dataclass
            class R:
                stdout: str
                stderr: str = ""
                exit_code: int = 0
                session_id: str | None = None
            return R(stdout="- User likes Python\n- Prefers terse output")

    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=agents_dir)
    result = store.consolidate_agent_notes("main", FakeRunner(), tmp_path, keep_days=3)

    assert "Consolidated" in result
    memory_content = (agents_dir / "main" / "MEMORY.md").read_text(encoding="utf-8")
    assert "Python" in memory_content
```

- [ ] **Step 2: Run tests to verify current behavior**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_memory.py::test_consolidate_produces_structured_summary tests/test_memory.py::test_consolidate_falls_back_on_non_json -v`
Expected: First test may FAIL (structured format not yet produced), second should PASS (current behavior)

- [ ] **Step 3: Update consolidation prompt and formatting**

In `app/memory.py`, replace the `consolidate_agent_notes` method's prompt and formatting section. Change the prompt (around line 334):

```python
        prompt = (
            f"The following are daily conversation notes for agent '{agent}'. "
            "Analyze these conversations and return a JSON object summarizing them:\n\n"
            '  "request": what the user was trying to accomplish\n'
            '  "learned": key facts, decisions, or preferences discovered\n'
            '  "completed": what was actually done or resolved\n'
            '  "next_steps": what the user might want to do next (or null)\n\n'
            "Return ONLY the JSON object. If there are multiple distinct topics, "
            "include all of them in each field.\n\n"
            f"{combined_text}"
        )
```

Replace the section that writes to MEMORY.md (around line 356):

```python
        if not extracted:
            return "No facts extracted from notes."

        # Try to parse as structured JSON; fall back to raw text
        structured = None
        try:
            structured = json.loads(extracted)
        except json.JSONDecodeError:
            pass

        memory_path = self.long_term_memory_path(agent)
        memory_path.parent.mkdir(parents=True, exist_ok=True)

        if structured and isinstance(structured, dict):
            lines = [f"\n\n## Session Summary — {self._now_human()}"]
            for key in ("request", "learned", "completed", "next_steps"):
                value = structured.get(key)
                if value:
                    lines.append(f"- **{key.replace('_', ' ').title()}:** {value}")
            block = "\n".join(lines) + "\n"
        else:
            block = f"\n\n## Consolidated {self._now_human()}\n{extracted}\n"

        with memory_path.open("a", encoding="utf-8") as fh:
            fh.write(block)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_memory.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/memory.py tests/test_memory.py
git commit -m "feat: structured session summaries in nightly consolidation"
```

---

### Task 6: Wire Observations into Memory Sources

**Files:**
- Modify: `app/memory.py` (`_memory_sources` to include observations)
- Modify: `app/embeddings.py` (ensure observation markdown gets indexed)

- [ ] **Step 1: Write test that observations appear in memory sources**

Append to `tests/test_memory.py`:

```python
def test_memory_sources_includes_observations(tmp_path: Path) -> None:
    agents_dir = tmp_path / "agents"
    (agents_dir / "main" / "memory").mkdir(parents=True)

    store = MemoryStore(shared_dir=tmp_path / "shared", agents_dir=agents_dir)
    obs = Observation(
        type=ObservationType.DECISION,
        title="Use token budgeting",
        narrative="Memory injection now respects token budgets.",
    )
    store.store_observation("main", obs)

    sources = store._memory_sources("main")
    joined = "\n".join(sources)
    assert "token budget" in joined.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_memory.py::test_memory_sources_includes_observations -v`
Expected: FAIL — observations not yet in `_memory_sources`

- [ ] **Step 3: Update _memory_sources to include observations**

In `app/memory.py`, update `_memory_sources`:

```python
    def _memory_sources(self, agent: str) -> list[str]:
        sources: list[str] = []
        long_term_memory = self.read_long_term_memory(agent)
        if long_term_memory:
            sources.append(long_term_memory)

        # Include stored observations
        observations = self.load_observations(agent, limit=50)
        if observations:
            obs_text = "\n\n".join(obs.to_markdown() for obs in observations)
            sources.append(obs_text)

        memory_dir = self._daily_notes_dir(agent)
        if memory_dir.exists():
            for path in sorted(memory_dir.glob("*.md"), reverse=True)[:3]:
                if path.name.upper() == "README.MD":
                    continue
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    sources.append(content)
        return sources
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_memory.py tests/test_auto_memory.py tests/test_context_builder.py tests/test_observations.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/memory.py
git commit -m "feat: include observations in memory sources for search indexing"
```

---

### Task 7: Full Integration Test

**Files:**
- Run all existing tests to verify no regressions

- [ ] **Step 1: Run the full test suite**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest -v`
Expected: All 159+ tests PASS (plus new tests added in this plan)

- [ ] **Step 2: Fix any regressions if needed**

If any tests fail, fix them. Common issues:
- Import paths changed
- Router tests mocking `find_relevant_memory` need updating to `find_relevant_memory_budgeted`
- Config tests may need `memory_token_budget` added to fixtures

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "test: verify full test suite passes with smart memory upgrade"
```

Only commit if there were fixes needed. If everything passed, skip this step.

---

## Summary of Changes

| What | Before | After |
|------|--------|-------|
| Auto-extraction | Free-form bullets via Claude | Typed JSON observations (decision/bugfix/feature/discovery/etc.) |
| Memory injection | Fixed top-4 snippets | Token-budgeted (default 800 tokens, configurable) |
| Deduplication | None | SHA256 content hash — exact duplicates rejected |
| Consolidation | Raw bullet list | Structured summary (request/learned/completed/next_steps) with fallback |
| Storage | Daily notes only | Daily notes + observations.jsonl |
| Search material | Raw transcripts | Structured observation markdown with metadata |
