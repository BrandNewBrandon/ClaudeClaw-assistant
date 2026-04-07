from __future__ import annotations

import logging
from pathlib import Path

from .app_paths import ensure_runtime_dirs, get_logs_file


def configure_logging(_shared_dir: Path) -> None:
    ensure_runtime_dirs()
    log_path = get_logs_file()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
