from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ObservationType(Enum):
    DECISION = "decision"
    BUGFIX = "bugfix"
    FEATURE = "feature"
    REFACTOR = "refactor"
    DISCOVERY = "discovery"
    CHANGE = "change"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Observation:
    type: ObservationType
    title: str
    narrative: str
    facts: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    files_read: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=_now_iso)

    @property
    def content_hash(self) -> str:
        raw = f"{self.type.value}|{self.title}|{self.narrative}|{'|'.join(self.facts)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @property
    def estimated_tokens(self) -> int:
        return max(1, len(self.to_markdown()) // 4)

    def to_markdown(self) -> str:
        lines: list[str] = []
        lines.append(f"**{self.type.value}**: {self.title}")
        lines.append(self.narrative)
        for fact in self.facts:
            lines.append(f"  - {fact}")
        meta_parts: list[str] = []
        if self.concepts:
            meta_parts.append(f"concepts: {', '.join(self.concepts)}")
        if self.files_read:
            meta_parts.append(f"read: {', '.join(self.files_read)}")
        if self.files_modified:
            meta_parts.append(f"modified: {', '.join(self.files_modified)}")
        if meta_parts:
            lines.append(f"  [{' | '.join(meta_parts)}]")
        return "\n".join(lines)


def observation_to_dict(obs: Observation) -> dict:
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


def observation_from_dict(d: dict) -> Observation:
    return Observation(
        type=ObservationType(d["type"]),
        title=d["title"],
        narrative=d["narrative"],
        facts=d.get("facts", []),
        concepts=d.get("concepts", []),
        files_read=d.get("files_read", []),
        files_modified=d.get("files_modified", []),
        timestamp=d.get("timestamp", _now_iso()),
    )
