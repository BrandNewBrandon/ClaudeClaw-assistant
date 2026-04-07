from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class ModelRunnerError(Exception):
    pass


@dataclass(frozen=True)
class ModelResult:
    stdout: str
    stderr: str
    exit_code: int
    session_id: str | None = None


class ModelRunner(Protocol):
    def ensure_available(self) -> None: ...

    def run_prompt(
        self,
        prompt: str,
        working_directory: str | Path,
        *,
        model: str | None = None,
        effort: str | None = None,
    ) -> ModelResult: ...
