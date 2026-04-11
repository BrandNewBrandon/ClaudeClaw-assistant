"""Cross-platform computer use tools — screenshots, mouse, keyboard, browser."""
from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, Callable

LOGGER = logging.getLogger(__name__)


def is_available() -> bool:
    """Return True if pyautogui is importable and a display is likely present."""
    try:
        import pyautogui  # noqa: F401
        return True
    except ImportError:
        return False


def _require_pyautogui():
    """Import and return pyautogui, raising ValueError if unavailable."""
    try:
        import pyautogui
        pyautogui.FAILSAFE = True  # move mouse to corner to abort
        return pyautogui
    except ImportError:
        raise ValueError(
            "pyautogui is not installed. Install with: pip install pyautogui Pillow"
        )


# ── Tool handlers ────────────────────────────────────────────────────────────


def screenshot(arguments: dict[str, Any]) -> str:
    """Capture a screenshot and save to a temp file. Returns the file path."""
    pyautogui = _require_pyautogui()
    try:
        img = pyautogui.screenshot()
    except Exception as exc:
        return f"Screenshot failed: {exc}. Ensure a display is available."
    fd, path = tempfile.mkstemp(suffix=".png", prefix="assistant_screen_")
    os.close(fd)
    img.save(path)
    return f"Screenshot saved to: {path}\nResolution: {img.size[0]}x{img.size[1]}"


def mouse_click(arguments: dict[str, Any]) -> str:
    """Click at screen coordinates."""
    pyautogui = _require_pyautogui()
    x = arguments.get("x")
    y = arguments.get("y")
    if x is None or y is None:
        return "Both x and y coordinates are required."
    try:
        x, y = int(x), int(y)
    except (TypeError, ValueError):
        return "x and y must be integers."
    button = str(arguments.get("button", "left")).lower()
    if button not in ("left", "right", "middle"):
        button = "left"
    clicks = int(arguments.get("clicks", 1))
    try:
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        return f"Clicked {button} at ({x}, {y}), {clicks} click(s)."
    except Exception as exc:
        return f"Click failed: {exc}"


def mouse_move(arguments: dict[str, Any]) -> str:
    """Move the mouse cursor to screen coordinates."""
    pyautogui = _require_pyautogui()
    x = arguments.get("x")
    y = arguments.get("y")
    if x is None or y is None:
        return "Both x and y coordinates are required."
    try:
        x, y = int(x), int(y)
    except (TypeError, ValueError):
        return "x and y must be integers."
    try:
        pyautogui.moveTo(x=x, y=y)
        return f"Mouse moved to ({x}, {y})."
    except Exception as exc:
        return f"Mouse move failed: {exc}"


def keyboard_type(arguments: dict[str, Any]) -> str:
    """Type text using the keyboard."""
    pyautogui = _require_pyautogui()
    text = arguments.get("text", "")
    if not text:
        return "text is required."
    try:
        pyautogui.typewrite(str(text), interval=0.02)
        return f"Typed {len(text)} character(s)."
    except Exception as exc:
        # typewrite only handles ASCII; fall back to write() for unicode
        try:
            pyautogui.write(str(text))
            return f"Typed {len(text)} character(s)."
        except Exception as exc2:
            return f"Type failed: {exc2}"


def keyboard_hotkey(arguments: dict[str, Any]) -> str:
    """Press a keyboard shortcut (e.g., 'ctrl+c', 'cmd+space')."""
    pyautogui = _require_pyautogui()
    keys = arguments.get("keys", "")
    if not keys:
        return "keys is required (e.g., 'ctrl+c', 'cmd+tab')."
    key_list = [k.strip() for k in str(keys).split("+")]
    # Map common aliases
    key_map = {"cmd": "command", "ctrl": "ctrl", "alt": "alt", "win": "win"}
    mapped = [key_map.get(k.lower(), k.lower()) for k in key_list]
    try:
        pyautogui.hotkey(*mapped)
        return f"Pressed hotkey: {' + '.join(mapped)}"
    except Exception as exc:
        return f"Hotkey failed: {exc}"


def scroll_screen(arguments: dict[str, Any]) -> str:
    """Scroll the screen up or down."""
    pyautogui = _require_pyautogui()
    amount = arguments.get("amount", 3)
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        return "amount must be an integer (positive=up, negative=down)."
    try:
        pyautogui.scroll(amount)
        direction = "up" if amount > 0 else "down"
        return f"Scrolled {direction} by {abs(amount)}."
    except Exception as exc:
        return f"Scroll failed: {exc}"


def open_url(arguments: dict[str, Any]) -> str:
    """Open a URL in the default browser."""
    url = str(arguments.get("url", "")).strip()
    if not url:
        return "url is required."
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        webbrowser.open(url)
        return f"Opened {url} in default browser."
    except Exception as exc:
        return f"Failed to open URL: {exc}"


def open_app(arguments: dict[str, Any]) -> str:
    """Open an application by name (cross-platform)."""
    app_name = str(arguments.get("name", "")).strip()
    if not app_name:
        return "name is required."
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", "-a", app_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "Windows":
            subprocess.Popen(["start", "", app_name], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "Linux":
            subprocess.Popen([app_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            return f"Unsupported platform: {system}"
        return f"Opened {app_name}."
    except Exception as exc:
        return f"Failed to open {app_name}: {exc}"


def get_screen_size(arguments: dict[str, Any]) -> str:
    """Get the screen resolution."""
    pyautogui = _require_pyautogui()
    try:
        size = pyautogui.size()
        return f"Screen size: {size.width}x{size.height}"
    except Exception as exc:
        return f"Failed to get screen size: {exc}"


def get_mouse_position(arguments: dict[str, Any]) -> str:
    """Get the current mouse cursor position."""
    pyautogui = _require_pyautogui()
    try:
        pos = pyautogui.position()
        return f"Mouse position: ({pos.x}, {pos.y})"
    except Exception as exc:
        return f"Failed to get mouse position: {exc}"


# ── Tool registration ────────────────────────────────────────────────────────

ApprovalFn = Callable[[str], str]
"""Approval callback: takes action description, returns approval message or empty string if approved."""


def _make_gated_handler(
    handler: Callable[[dict[str, Any]], str],
    action_label: str,
    approval_fn: ApprovalFn | None,
) -> Callable[[dict[str, Any]], str]:
    """Wrap an action handler with an approval gate."""
    if approval_fn is None:
        return handler

    def wrapper(arguments: dict[str, Any]) -> str:
        # Build a human-readable description of the action
        desc = f"[Computer Use] {action_label}"
        if arguments:
            details = ", ".join(f"{k}={v}" for k, v in arguments.items())
            desc = f"{desc}: {details}"
        result = approval_fn(desc)
        if result:
            return result  # Approval pending — return the approval message
        return handler(arguments)

    return wrapper


def register_computer_use_tools(
    registry,
    *,
    approval_fn: ApprovalFn | None = None,
) -> None:
    """Register computer use tools on a ToolRegistry.

    ``approval_fn``: if provided, action tools (mouse, keyboard, scroll,
    open) are gated behind it. The function receives a description string
    and returns an approval-pending message (non-empty) or empty string
    if pre-approved. Read-only tools (screenshot, screen size, mouse
    position) are never gated.
    """
    from .tools import ToolSpec

    # Read-only tools — always safe, no approval needed
    registry.register(
        ToolSpec("screenshot", "Capture a screenshot of the screen. Returns the file path to the image.", {}),
        screenshot,
    )
    registry.register(
        ToolSpec("get_screen_size", "Get the screen resolution.", {}),
        get_screen_size,
    )
    registry.register(
        ToolSpec("get_mouse_position", "Get the current mouse cursor position.", {}),
        get_mouse_position,
    )

    # Action tools — gated behind approval_fn if provided
    registry.register(
        ToolSpec("mouse_click", "Click at screen coordinates. Requires approval.", {
            "x": "integer x coordinate",
            "y": "integer y coordinate",
            "button": "(optional) left, right, or middle (default: left)",
            "clicks": "(optional) number of clicks (default: 1)",
        }),
        _make_gated_handler(mouse_click, "mouse_click", approval_fn),
    )
    registry.register(
        ToolSpec("mouse_move", "Move the mouse cursor to screen coordinates. Requires approval.", {
            "x": "integer x coordinate",
            "y": "integer y coordinate",
        }),
        _make_gated_handler(mouse_move, "mouse_move", approval_fn),
    )
    registry.register(
        ToolSpec("keyboard_type", "Type text using the keyboard. Requires approval.", {
            "text": "text to type",
        }),
        _make_gated_handler(keyboard_type, "keyboard_type", approval_fn),
    )
    registry.register(
        ToolSpec("keyboard_hotkey", "Press a keyboard shortcut. Requires approval.", {
            "keys": "keys joined by + (e.g., 'ctrl+c', 'cmd+space', 'alt+tab')",
        }),
        _make_gated_handler(keyboard_hotkey, "keyboard_hotkey", approval_fn),
    )
    registry.register(
        ToolSpec("scroll", "Scroll the screen up or down. Requires approval.", {
            "amount": "integer (positive=up, negative=down, default=3)",
        }),
        _make_gated_handler(scroll_screen, "scroll", approval_fn),
    )
    registry.register(
        ToolSpec("open_url", "Open a URL in the default browser. Requires approval.", {
            "url": "URL to open",
        }),
        _make_gated_handler(open_url, "open_url", approval_fn),
    )
    registry.register(
        ToolSpec("open_app", "Open an application by name. Requires approval.", {
            "name": "application name",
        }),
        _make_gated_handler(open_app, "open_app", approval_fn),
    )
