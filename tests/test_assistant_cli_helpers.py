from __future__ import annotations

from pathlib import Path

from app.assistant_cli import _mask_secret, _seed_project_paths


def test_mask_secret_masks_short_values() -> None:
    assert _mask_secret("abcd") == "****"


def test_mask_secret_masks_long_values() -> None:
    assert _mask_secret("1234567890abcdef") == "1234...cdef"


def test_seed_project_paths_sets_missing_defaults() -> None:
    seeded = _seed_project_paths({"default_agent": "main"}, Path("C:/repo"))

    assert Path(seeded["project_root"]) == Path("C:/repo")
    assert Path(seeded["agents_dir"]) == Path("C:/repo/agents")
    assert Path(seeded["shared_dir"]) == Path("C:/repo/shared")


def test_seed_project_paths_preserves_existing_values() -> None:
    seeded = _seed_project_paths(
        {
            "project_root": "D:/custom-root",
            "agents_dir": "D:/custom-agents",
            "shared_dir": "D:/custom-shared",
        },
        Path("C:/repo"),
    )

    assert Path(seeded["project_root"]) == Path("D:/custom-root")
    assert Path(seeded["agents_dir"]) == Path("D:/custom-agents")
    assert Path(seeded["shared_dir"]) == Path("D:/custom-shared")
