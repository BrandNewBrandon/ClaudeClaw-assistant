from __future__ import annotations

import sys
from pathlib import Path

from .router import AssistantRouter


def main() -> None:
    config_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    router = AssistantRouter(config_path=config_path)
    router.run()


if __name__ == "__main__":
    main()
