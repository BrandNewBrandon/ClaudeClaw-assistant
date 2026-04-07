"""TTS skill — text-to-speech via the system's native voice engine.

Supported backends (checked in order)
--------------------------------------
- macOS:  ``say`` command
- Linux:  ``espeak-ng`` or ``espeak``
- Windows: ``PowerShell`` speech synthesizer

Tools (callable by Claude)
--------------------------
``speak(text)``          speak text aloud; returns confirmation
``speak(text, voice)``   speak with a named voice (macOS only for now)

Slash commands
--------------
``/speak <text>``       speak text immediately
``/voices``             list available voices (macOS only)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any

from ..plugins.base import SkillBase
from ..tools import ToolSpec


def _backend() -> str | None:
    if sys.platform == "darwin" and shutil.which("say"):
        return "say"
    if shutil.which("espeak-ng"):
        return "espeak-ng"
    if shutil.which("espeak"):
        return "espeak"
    if sys.platform == "win32":
        return "powershell"
    return None


def _speak(args: dict[str, Any]) -> str:
    text = str(args.get("text", "")).strip()
    if not text:
        return "No text provided."
    voice = str(args.get("voice", "")).strip() or None
    backend = _backend()

    if backend == "say":
        cmd = ["say"]
        if voice:
            cmd += ["-v", voice]
        cmd.append(text)
    elif backend in ("espeak-ng", "espeak"):
        cmd = [backend, text]
    elif backend == "powershell":
        escaped = text.replace("'", "''")
        cmd = ["powershell", "-Command",
               f"Add-Type -AssemblyName System.Speech; "
               f"(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{escaped}')"]
    else:
        return "No TTS backend available."

    try:
        subprocess.run(cmd, check=True, timeout=120, capture_output=True)
        return f"Speaking: {text[:80]}{'…' if len(text) > 80 else ''}"
    except subprocess.TimeoutExpired:
        return "TTS timed out."
    except subprocess.CalledProcessError as exc:
        return f"TTS failed: {exc}"


def _list_voices(args: dict[str, Any]) -> str:
    if sys.platform != "darwin" or not shutil.which("say"):
        return "Voice listing is only supported on macOS."
    result = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=5)
    lines = result.stdout.strip().splitlines()[:30]
    return "\n".join(lines) if lines else "No voices found."


class TTSSkill(SkillBase):
    name = "tts"
    version = "1.0"
    description = "TTS — speak text aloud via system voice engine (say/espeak)"

    def is_available(self) -> bool:
        return _backend() is not None

    def tools(self):
        return [
            (
                ToolSpec(
                    "speak",
                    "Convert text to speech and play it aloud on the host machine.",
                    {"text": "text to speak", "voice": "(optional) voice name"},
                ),
                _speak,
            ),
            (
                ToolSpec(
                    "list_voices",
                    "List available TTS voices on the host machine.",
                    {},
                ),
                _list_voices,
            ),
        ]

    def commands(self):
        def _speak_cmd(text: str) -> str:
            rest = text.removeprefix("/speak").strip()
            if not rest:
                return "Usage: /speak <text>"
            return _speak({"text": rest})

        def _voices_cmd(_text: str) -> str:
            return _list_voices({})

        return {"/speak": _speak_cmd, "/voices": _voices_cmd}


SKILL_CLASS = TTSSkill
