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
