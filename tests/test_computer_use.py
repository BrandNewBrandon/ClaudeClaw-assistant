"""Tests for computer use tools."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
from pathlib import Path

from app.computer_use import (
    is_available,
    screenshot,
    mouse_click,
    mouse_move,
    keyboard_type,
    keyboard_hotkey,
    scroll_screen,
    open_url,
    open_app,
    get_screen_size,
    get_mouse_position,
    register_computer_use_tools,
)
from app.tools import ToolRegistry


def test_is_available():
    # pyautogui is installed in this env
    assert is_available() is True


def test_screenshot_returns_path_on_success():
    mock_img = MagicMock()
    mock_img.size = (1920, 1080)
    with patch("app.computer_use._require_pyautogui") as mock_pag:
        mock_pag.return_value.screenshot.return_value = mock_img
        result = screenshot({})
    assert "Screenshot saved to:" in result
    assert "1920x1080" in result


def test_screenshot_handles_failure():
    with patch("app.computer_use._require_pyautogui") as mock_pag:
        mock_pag.return_value.screenshot.side_effect = RuntimeError("no display")
        result = screenshot({})
    assert "failed" in result.lower()


def test_mouse_click_requires_coordinates():
    result = mouse_click({"x": 100})
    assert "required" in result.lower()
    result = mouse_click({"y": 100})
    assert "required" in result.lower()


def test_mouse_click_success():
    with patch("app.computer_use._require_pyautogui") as mock_pag:
        result = mouse_click({"x": 100, "y": 200})
    assert "Clicked" in result
    assert "(100, 200)" in result
    mock_pag.return_value.click.assert_called_once_with(x=100, y=200, button="left", clicks=1)


def test_mouse_click_right_button():
    with patch("app.computer_use._require_pyautogui") as mock_pag:
        result = mouse_click({"x": 50, "y": 50, "button": "right"})
    assert "right" in result
    mock_pag.return_value.click.assert_called_once_with(x=50, y=50, button="right", clicks=1)


def test_mouse_move_success():
    with patch("app.computer_use._require_pyautogui") as mock_pag:
        result = mouse_move({"x": 300, "y": 400})
    assert "moved" in result.lower()
    mock_pag.return_value.moveTo.assert_called_once_with(x=300, y=400)


def test_keyboard_type_success():
    with patch("app.computer_use._require_pyautogui") as mock_pag:
        result = keyboard_type({"text": "hello"})
    assert "5 character" in result
    mock_pag.return_value.typewrite.assert_called_once()


def test_keyboard_type_empty():
    result = keyboard_type({"text": ""})
    assert "required" in result.lower()


def test_keyboard_hotkey_success():
    with patch("app.computer_use._require_pyautogui") as mock_pag:
        result = keyboard_hotkey({"keys": "cmd+c"})
    assert "Pressed" in result
    mock_pag.return_value.hotkey.assert_called_once_with("command", "c")


def test_keyboard_hotkey_empty():
    result = keyboard_hotkey({"keys": ""})
    assert "required" in result.lower()


def test_scroll_success():
    with patch("app.computer_use._require_pyautogui") as mock_pag:
        result = scroll_screen({"amount": -5})
    assert "down" in result.lower()
    mock_pag.return_value.scroll.assert_called_once_with(-5)


def test_open_url_adds_https():
    with patch("app.computer_use.webbrowser") as mock_wb:
        result = open_url({"url": "example.com"})
    assert "Opened" in result
    mock_wb.open.assert_called_once_with("https://example.com")


def test_open_url_preserves_scheme():
    with patch("app.computer_use.webbrowser") as mock_wb:
        result = open_url({"url": "http://example.com"})
    mock_wb.open.assert_called_once_with("http://example.com")


def test_open_url_empty():
    result = open_url({"url": ""})
    assert "required" in result.lower()


def test_open_app_mac():
    with patch("app.computer_use.platform") as mock_plat, \
         patch("app.computer_use.subprocess") as mock_sub:
        mock_plat.system.return_value = "Darwin"
        result = open_app({"name": "Safari"})
    assert "Opened" in result
    mock_sub.Popen.assert_called_once()


def test_open_app_empty():
    result = open_app({"name": ""})
    assert "required" in result.lower()


def test_get_screen_size():
    with patch("app.computer_use._require_pyautogui") as mock_pag:
        mock_pag.return_value.size.return_value = MagicMock(width=1920, height=1080)
        result = get_screen_size({})
    assert "1920x1080" in result


def test_get_mouse_position():
    with patch("app.computer_use._require_pyautogui") as mock_pag:
        mock_pag.return_value.position.return_value = MagicMock(x=500, y=300)
        result = get_mouse_position({})
    assert "(500, 300)" in result


def test_register_computer_use_tools_adds_all():
    registry = ToolRegistry()
    register_computer_use_tools(registry)
    names = [s.name for s in registry.list_specs()]
    expected = [
        "screenshot", "get_screen_size", "get_mouse_position",
        "mouse_click", "mouse_move", "keyboard_type",
        "keyboard_hotkey", "scroll", "open_url", "open_app",
    ]
    for name in expected:
        assert name in names, f"Missing tool: {name}"


def test_approval_gate_blocks_action():
    """Action tools should call approval_fn and return its message when non-empty."""
    registry = ToolRegistry()
    approval_calls: list[str] = []

    def fake_approval(desc: str) -> str:
        approval_calls.append(desc)
        return "Awaiting approval..."

    register_computer_use_tools(registry, approval_fn=fake_approval)
    result = registry.execute(
        __import__("app.tools", fromlist=["ToolCall"]).ToolCall(
            name="mouse_click", arguments={"x": 100, "y": 200}
        )
    )
    assert result.output == "Awaiting approval..."
    assert len(approval_calls) == 1
    assert "mouse_click" in approval_calls[0]


def test_approval_gate_allows_when_empty():
    """Action tools should execute normally when approval_fn returns empty string."""
    registry = ToolRegistry()
    register_computer_use_tools(registry, approval_fn=lambda desc: "")
    with patch("app.computer_use._require_pyautogui") as mock_pag:
        from app.tools import ToolCall
        result = registry.execute(ToolCall(name="mouse_click", arguments={"x": 50, "y": 50}))
    assert "Clicked" in result.output


def test_read_only_tools_bypass_approval():
    """Screenshot and other read-only tools should never go through approval."""
    approval_calls: list[str] = []
    registry = ToolRegistry()
    register_computer_use_tools(
        registry,
        approval_fn=lambda desc: (approval_calls.append(desc) or "blocked"),
    )
    with patch("app.computer_use._require_pyautogui") as mock_pag:
        mock_pag.return_value.size.return_value = MagicMock(width=1920, height=1080)
        from app.tools import ToolCall
        result = registry.execute(ToolCall(name="get_screen_size", arguments={}))
    assert "1920x1080" in result.output
    assert len(approval_calls) == 0  # No approval called for read-only


def test_agent_config_computer_use_flag():
    from app.agent_config import AgentConfig, load_agent_config
    import json

    # Default is False
    config = AgentConfig()
    assert config.computer_use is False


def test_agent_config_loads_computer_use(tmp_path: Path):
    from app.agent_config import load_agent_config
    import json

    agent_dir = tmp_path / "test_agent"
    agent_dir.mkdir()
    (agent_dir / "agent.json").write_text(
        json.dumps({"computer_use": True}), encoding="utf-8",
    )
    config = load_agent_config(agent_dir)
    assert config.computer_use is True
