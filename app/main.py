from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from .router import AssistantRouter

LOGGER = logging.getLogger(__name__)


def _start_embedded_dashboard() -> None:
    """Launch the web dashboard in a background thread alongside the runtime.

    Silent best-effort — never crashes the runtime. Set CLAUDECLAW_NO_DASHBOARD=1
    to skip entirely (e.g. when running `assistant ui` in a separate process).
    """
    if os.environ.get("CLAUDECLAW_NO_DASHBOARD") == "1":
        return
    try:
        from .web.server import WebDashboard

        dashboard = WebDashboard()
        dashboard.start(blocking=False)
        LOGGER.info("Embedded dashboard started at http://localhost:18790")
    except OSError as exc:
        # Most commonly: port already in use (another dashboard instance running).
        LOGGER.warning("Embedded dashboard not started: %s", exc)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Embedded dashboard failed to start: %s", exc)


def main() -> None:
    config_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    _start_embedded_dashboard()
    router = AssistantRouter(config_path=config_path)
    router.run()


if __name__ == "__main__":
    main()
