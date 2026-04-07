"""Lightweight semantic embedding index for agent memory search.

Uses ``fastembed`` (ONNX-based, ~100 MB) to embed memory snippets and
answer queries via cosine similarity.  Falls back gracefully when
fastembed is not installed — the rest of the runtime works fine without it.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

# Lazy-loaded singleton — avoids importing fastembed at module level.
_model_lock = threading.Lock()
_model_instance: Any = None
_model_name: str = "BAAI/bge-small-en-v1.5"


def _get_model(model_name: str | None = None) -> Any:
    """Return a shared ``TextEmbedding`` instance, creating it on first call."""
    global _model_instance, _model_name
    name = model_name or _model_name
    with _model_lock:
        if _model_instance is None or name != _model_name:
            try:
                from fastembed import TextEmbedding  # type: ignore[import-untyped]
            except ImportError:
                raise ImportError(
                    "fastembed is required for semantic search. "
                    "Install it with: pip install fastembed"
                )
            _model_name = name
            _model_instance = TextEmbedding(model_name=name)
            LOGGER.info("Loaded embedding model: %s", name)
        return _model_instance


def is_available() -> bool:
    """Return True if fastembed + numpy are importable."""
    try:
        import fastembed  # noqa: F401
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


class EmbeddingIndex:
    """In-memory vector index backed by numpy arrays on disk.

    On-disk layout at ``{index_dir}/``::

        vectors.npz   — numpy array of shape (N, dim)
        manifest.json — list of {"source": "...", "text": "...", "hash": "..."}
    """

    def __init__(self, agent_name: str, index_dir: Path, *, model_name: str | None = None) -> None:
        self._agent_name = agent_name
        self._index_dir = index_dir
        self._model_name = model_name
        self._vectors: Any = None  # numpy ndarray (N, dim) or None
        self._manifest: list[dict[str, str]] = []
        self._loaded = False

    # ── Public API ───────────────────────────────────────────────────────────

    def build_from_sources(self, snippets: list[tuple[str, str]]) -> int:
        """Embed a list of ``(source_label, text)`` pairs and save to disk.

        Returns the number of snippets indexed.
        """
        import numpy as np

        if not snippets:
            self._vectors = np.empty((0, 384), dtype=np.float32)
            self._manifest = []
            self._save()
            return 0

        texts = [text for _, text in snippets]
        vectors = self._embed(texts)

        self._manifest = [
            {"source": src, "text": txt, "hash": _text_hash(txt)}
            for src, txt in snippets
        ]
        self._vectors = vectors
        self._loaded = True
        self._save()
        return len(self._manifest)

    def add_snippet(self, source_label: str, text: str) -> None:
        """Incrementally embed and append one snippet to the index."""
        import numpy as np

        self._ensure_loaded()
        h = _text_hash(text)
        # Skip if already indexed
        if any(entry["hash"] == h for entry in self._manifest):
            return

        vec = self._embed([text])
        if self._vectors is None or len(self._vectors) == 0:
            self._vectors = vec
        else:
            self._vectors = np.vstack([self._vectors, vec])
        self._manifest.append({"source": source_label, "text": text, "hash": h})
        self._save()

    def query(self, query_text: str, limit: int = 4) -> list[str]:
        """Return the top-k most similar snippets to ``query_text``."""
        import numpy as np

        self._ensure_loaded()
        if self._vectors is None or len(self._vectors) == 0:
            return []

        query_vec = self._embed([query_text])  # (1, dim)
        # Cosine similarity
        norms = np.linalg.norm(self._vectors, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        normed = self._vectors / norms
        q_norm = query_vec / max(np.linalg.norm(query_vec), 1e-9)
        scores = (normed @ q_norm.T).flatten()

        top_indices = scores.argsort()[::-1][:limit]
        return [self._manifest[i]["text"] for i in top_indices if scores[i] > 0.1]

    @property
    def size(self) -> int:
        """Number of indexed snippets."""
        self._ensure_loaded()
        return len(self._manifest)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _embed(self, texts: list[str]) -> Any:
        """Embed a batch of texts, returning an ndarray of shape (N, dim)."""
        import numpy as np

        model = _get_model(self._model_name)
        # fastembed returns a generator of arrays
        embeddings = list(model.embed(texts))
        return np.array(embeddings, dtype=np.float32)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._load()

    def _load(self) -> None:
        import numpy as np

        vectors_path = self._index_dir / "vectors.npz"
        manifest_path = self._index_dir / "manifest.json"

        if vectors_path.exists() and manifest_path.exists():
            try:
                data = np.load(str(vectors_path))
                self._vectors = data["vectors"]
                self._manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                LOGGER.debug("Loaded embedding index for %s: %d snippets", self._agent_name, len(self._manifest))
            except Exception:
                LOGGER.warning("Failed to load embedding index for %s, will rebuild", self._agent_name)
                self._vectors = np.empty((0, 384), dtype=np.float32)
                self._manifest = []
        else:
            self._vectors = np.empty((0, 384), dtype=np.float32)
            self._manifest = []
        self._loaded = True

    def _save(self) -> None:
        import numpy as np

        self._index_dir.mkdir(parents=True, exist_ok=True)
        vectors_path = self._index_dir / "vectors.npz"
        manifest_path = self._index_dir / "manifest.json"

        np.savez_compressed(str(vectors_path), vectors=self._vectors)
        manifest_path.write_text(
            json.dumps(self._manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _text_hash(text: str) -> str:
    """Short content hash for dedup."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]
