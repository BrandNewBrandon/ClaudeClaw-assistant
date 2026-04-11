from __future__ import annotations

from pathlib import Path

from app.transcript_rotation import rotate_transcript, rotate_all_transcripts, MAX_LINES, KEEP_LINES


def test_rotate_skips_small_file(tmp_path: Path) -> None:
    path = tmp_path / "chat.jsonl"
    path.write_text("\n".join(f"line {i}" for i in range(100)) + "\n", encoding="utf-8")
    assert rotate_transcript(path) is False
    assert len(path.read_text(encoding="utf-8").splitlines()) == 100


def test_rotate_splits_large_file(tmp_path: Path) -> None:
    path = tmp_path / "chat.jsonl"
    total = MAX_LINES + 500
    path.write_text("\n".join(f"line {i}" for i in range(total)) + "\n", encoding="utf-8")
    assert rotate_transcript(path) is True

    remaining = path.read_text(encoding="utf-8").splitlines()
    assert len(remaining) == KEEP_LINES
    assert remaining[-1] == f"line {total - 1}"

    archive = path.with_suffix(".archive.jsonl")
    assert archive.exists()
    archived = archive.read_text(encoding="utf-8").splitlines()
    assert len(archived) == total - KEEP_LINES


def test_rotate_appends_to_existing_archive(tmp_path: Path) -> None:
    path = tmp_path / "chat.jsonl"
    archive = path.with_suffix(".archive.jsonl")
    archive.write_text("old archived line\n", encoding="utf-8")

    total = MAX_LINES + 100
    path.write_text("\n".join(f"line {i}" for i in range(total)) + "\n", encoding="utf-8")
    rotate_transcript(path)

    archived = archive.read_text(encoding="utf-8").splitlines()
    assert archived[0] == "old archived line"
    assert len(archived) > 1


def test_rotate_all_transcripts(tmp_path: Path) -> None:
    # One small, one large
    small = tmp_path / "small.jsonl"
    small.write_text("\n".join(f"s{i}" for i in range(10)) + "\n", encoding="utf-8")

    large = tmp_path / "large.jsonl"
    large.write_text("\n".join(f"l{i}" for i in range(MAX_LINES + 100)) + "\n", encoding="utf-8")

    count = rotate_all_transcripts(tmp_path)
    assert count == 1


def test_rotate_skips_archive_files(tmp_path: Path) -> None:
    archive = tmp_path / "chat.archive.jsonl"
    archive.write_text("\n".join(f"a{i}" for i in range(MAX_LINES + 100)) + "\n", encoding="utf-8")

    count = rotate_all_transcripts(tmp_path)
    assert count == 0


def test_rotate_missing_file(tmp_path: Path) -> None:
    assert rotate_transcript(tmp_path / "nonexistent.jsonl") is False
