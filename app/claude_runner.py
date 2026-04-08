from __future__ import annotations

import json
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable

from .model_runner import ModelResult, ModelRunnerError


class ClaudeCodeRunner:
    def __init__(self, timeout_seconds: int, model: str | None = None, effort: str | None = None) -> None:
        self._timeout_seconds = timeout_seconds
        self._default_model = model
        self._default_effort = effort

    def ensure_available(self) -> None:
        if shutil.which("claude") is None:
            raise ModelRunnerError("`claude` CLI not found in PATH.")

    def _claude_exe(self) -> str:
        """Return the resolved claude executable path (handles .cmd on Windows)."""
        return shutil.which("claude") or "claude"

    def run_prompt(
        self,
        prompt: str,
        working_directory: str | Path,
        *,
        model: str | None = None,
        effort: str | None = None,
        session_id: str | None = None,
    ) -> ModelResult:
        self.ensure_available()
        cwd = Path(working_directory)

        # When resuming a session we need JSON output to capture the new session_id.
        use_json = session_id is not None

        command = [
            self._claude_exe(),
            "--print",
            "--output-format",
            "json" if use_json else "text",
            "--permission-mode",
            "bypassPermissions",
        ]

        effective_model = model if model is not None else self._default_model
        effective_effort = effort if effort is not None else self._default_effort

        if effective_model:
            command.extend(["--model", effective_model])
        if effective_effort:
            command.extend(["--effort", effective_effort])

        if session_id:
            command.extend(["--resume", session_id])

        # Pass prompt via stdin to avoid OS command-line length limits (Windows 8191 char cap)
        command.extend(["-p", "-"])

        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self._timeout_seconds,
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            raise ModelRunnerError(f"Claude timed out after {self._timeout_seconds} seconds.") from exc
        except OSError as exc:
            raise ModelRunnerError(f"Failed to execute Claude CLI: {exc}") from exc

        raw_stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()

        if not raw_stdout and completed.returncode != 0:
            raise ModelRunnerError(
                f"Claude returned no stdout and exit code {completed.returncode}. stderr: {stderr}"
            )

        if use_json:
            stdout, new_session_id = self._parse_json_output(raw_stdout, stderr)
        else:
            stdout = raw_stdout
            new_session_id = None

        return ModelResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=completed.returncode,
            session_id=new_session_id,
        )

    def run_prompt_streaming(
        self,
        prompt: str,
        working_directory: str | Path,
        *,
        model: str | None = None,
        effort: str | None = None,
        session_id: str | None = None,
        on_chunk: Callable[[str], None] | None = None,
    ) -> ModelResult:
        """Run a prompt with real-time streaming output.

        Calls ``on_chunk(text_delta)`` for each partial text chunk as Claude
        generates it.  Returns a complete ``ModelResult`` once the run
        finishes; ``ModelResult.stdout`` always contains the full canonical
        response text (from the ``result`` event), regardless of what chunks
        were delivered to ``on_chunk``.
        """
        self.ensure_available()
        cwd = Path(working_directory)

        command = [
            self._claude_exe(),
            "--print",
            "--verbose",
            "--output-format", "stream-json",
            "--include-partial-messages",
            "--permission-mode", "bypassPermissions",
        ]

        effective_model = model if model is not None else self._default_model
        effective_effort = effort if effort is not None else self._default_effort

        if effective_model:
            command.extend(["--model", effective_model])
        if effective_effort:
            command.extend(["--effort", effective_effort])
        if session_id:
            command.extend(["--resume", session_id])

        # Pass prompt via stdin to avoid OS command-line length limits (Windows 8191 char cap)
        command.extend(["-p", "-"])

        try:
            proc = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            raise ModelRunnerError(f"Failed to execute Claude CLI: {exc}") from exc

        # Write prompt to stdin and close it so Claude starts processing
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except OSError:
            pass

        # Kill the process if it exceeds the timeout
        _killed = threading.Event()

        def _timeout_kill() -> None:
            _killed.set()
            proc.kill()

        timer = threading.Timer(self._timeout_seconds, _timeout_kill)
        timer.start()

        final_text = ""
        new_session_id: str | None = None
        stderr_lines: list[str] = []

        try:
            assert proc.stdout is not None
            for raw_line in proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")

                if event_type == "assistant":
                    # Each partial assistant event carries text chunk(s)
                    msg = event.get("message") or {}
                    for block in msg.get("content") or []:
                        if isinstance(block, dict) and block.get("type") == "text":
                            chunk = block.get("text", "")
                            if chunk and on_chunk is not None:
                                on_chunk(chunk)

                elif event_type == "result":
                    # Final event — authoritative complete text + session id
                    final_text = str(event.get("result") or "").strip()
                    sid = event.get("session_id")
                    if isinstance(sid, str) and sid.strip():
                        new_session_id = sid.strip()
                    break  # nothing useful after result

            # Drain stderr
            assert proc.stderr is not None
            stderr_lines = proc.stderr.readlines()
        finally:
            timer.cancel()
            try:
                proc.stdout and proc.stdout.close()
                proc.stderr and proc.stderr.close()
            except Exception:
                pass

        proc.wait()

        if _killed.is_set():
            raise ModelRunnerError(
                f"Claude timed out after {self._timeout_seconds} seconds."
            )

        stderr = "".join(stderr_lines).strip()

        if not final_text and proc.returncode != 0:
            raise ModelRunnerError(
                f"Claude returned no output and exit code {proc.returncode}. stderr: {stderr}"
            )

        return ModelResult(
            stdout=final_text,
            stderr=stderr,
            exit_code=proc.returncode,
            session_id=new_session_id,
        )

    @staticmethod
    def _parse_json_output(raw: str, stderr: str) -> tuple[str, str | None]:
        """Extract (text, session_id) from claude --output-format json output."""
        if not raw:
            return "", None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Fall back to treating raw output as plain text
            return raw, None

        if isinstance(data, dict):
            text = str(data.get("result") or data.get("content") or "").strip()
            session_id = data.get("session_id") or None
            if isinstance(session_id, str) and session_id.strip():
                return text, session_id.strip()
            return text, None

        return raw, None
