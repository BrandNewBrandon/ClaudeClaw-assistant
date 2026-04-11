"""Backup and restore assistant data."""
from __future__ import annotations

import json
import logging
import shutil
import tarfile
from datetime import datetime
from pathlib import Path

from .app_paths import get_config_dir, get_state_dir, get_config_file

LOGGER = logging.getLogger(__name__)

BACKUP_MANIFEST = "backup_manifest.json"


def create_backup(output_path: Path | None = None) -> Path:
    """Create a .tar.gz backup of all assistant data.

    Includes: config (config.json, agents/), state (tasks.db, jobs.db,
    transcripts/). Excludes: runtime.lock, runtime.pid, logs.

    Returns path to the created archive.
    """
    config_dir = get_config_dir()
    state_dir = get_state_dir()

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if output_path is None:
        output_path = Path.home() / f"assistant-backup-{timestamp}.tar.gz"

    manifest = {
        "version": "1.0",
        "created_at": datetime.now().astimezone().isoformat(),
        "config_dir": str(config_dir),
        "state_dir": str(state_dir),
        "contents": [],
    }

    skip_names = {"runtime.lock", "runtime.pid", "sessions.json"}

    with tarfile.open(str(output_path), "w:gz") as tar:
        # Add config directory (config.json + agents/)
        if config_dir.exists():
            for item in _walk_files(config_dir):
                if item.name in skip_names:
                    continue
                arcname = f"config/{item.relative_to(config_dir)}"
                tar.add(str(item), arcname=arcname)
                manifest["contents"].append(arcname)

        # Add state directory (tasks.db, jobs.db, transcripts/)
        if state_dir.exists():
            for item in _walk_files(state_dir):
                if item.name in skip_names:
                    continue
                arcname = f"state/{item.relative_to(state_dir)}"
                tar.add(str(item), arcname=arcname)
                manifest["contents"].append(arcname)

        # Write manifest into archive
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest, f, indent=2)
            f.flush()
            tar.add(f.name, arcname=BACKUP_MANIFEST)
        Path(f.name).unlink(missing_ok=True)

    return output_path


def restore_backup(archive_path: Path, *, dry_run: bool = False) -> list[str]:
    """Restore assistant data from a .tar.gz backup.

    Returns list of restored file paths.
    If dry_run=True, lists what would be restored without writing.
    """
    config_dir = get_config_dir()
    state_dir = get_state_dir()

    restored: list[str] = []

    with tarfile.open(str(archive_path), "r:gz") as tar:
        # Verify manifest exists
        try:
            tar.getmember(BACKUP_MANIFEST)
        except KeyError:
            raise ValueError("Not a valid assistant backup (missing manifest).")

        for member in tar.getmembers():
            if member.name == BACKUP_MANIFEST:
                continue
            if not member.isfile():
                continue

            # Determine destination
            if member.name.startswith("config/"):
                rel = member.name[len("config/"):]
                dest = config_dir / rel
            elif member.name.startswith("state/"):
                rel = member.name[len("state/"):]
                dest = state_dir / rel
            else:
                continue

            restored.append(str(dest))

            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                # Extract file
                member_file = tar.extractfile(member)
                if member_file is not None:
                    dest.write_bytes(member_file.read())

    return restored


def list_backup_contents(archive_path: Path) -> dict:
    """Read the manifest from a backup archive."""
    with tarfile.open(str(archive_path), "r:gz") as tar:
        try:
            member = tar.getmember(BACKUP_MANIFEST)
        except KeyError:
            raise ValueError("Not a valid assistant backup (missing manifest).")
        f = tar.extractfile(member)
        if f is None:
            raise ValueError("Cannot read backup manifest.")
        return json.loads(f.read().decode("utf-8"))


def _walk_files(directory: Path) -> list[Path]:
    """Walk a directory and return all file paths (sorted for deterministic output)."""
    files = []
    for item in sorted(directory.rglob("*")):
        if item.is_file():
            files.append(item)
    return files
