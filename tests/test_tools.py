from __future__ import annotations

from app.tools import ToolCall, ToolLoop, ToolRegistry, ToolSpec, build_default_registry, is_obvious_web_request


def test_tool_loop_parses_tool_call() -> None:
    registry = ToolRegistry()
    loop = ToolLoop(registry)

    call = loop.parse_tool_call('TOOL {"name": "web_search", "arguments": {"query": "openclaw"}}')

    assert call == ToolCall(name="web_search", arguments={"query": "openclaw"})


def test_tool_loop_formats_tool_result() -> None:
    registry = ToolRegistry()
    loop = ToolLoop(registry)

    result = loop.format_tool_result(registry.execute(ToolCall(name="missing", arguments={})))

    assert '"name": "missing"' in result
    assert '"status": "error"' in result


def test_default_registry_lists_expected_tools() -> None:
    registry = build_default_registry()
    names = [spec.name for spec in registry.list_specs()]

    assert "web_fetch" in names
    assert "web_search" in names
    assert "read_file" in names
    assert "write_file" in names
    assert "list_dir" in names
    assert "run_command" in names


def test_registry_executes_registered_tool() -> None:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="echo", description="Echo input", arguments={"text": "string"}),
        lambda arguments: str(arguments["text"]),
    )

    result = registry.execute(ToolCall(name="echo", arguments={"text": "hello"}))

    assert result.ok is True
    assert result.output == "hello"


def test_web_request_heuristic_detects_obvious_requests() -> None:
    assert is_obvious_web_request("search the web for OpenClaw docs") is True
    assert is_obvious_web_request("fetch https://docs.openclaw.ai") is True
    assert is_obvious_web_request("what's our current routing config?") is False


def test_disk_usage_returns_usage_for_real_path(tmp_path) -> None:
    registry = build_default_registry(tmp_path)
    result = registry.execute(ToolCall(name="disk_usage", arguments={"path": str(tmp_path)}))
    assert result.ok is True
    assert "Total:" in result.output
    assert "Used:" in result.output
    assert "Free:" in result.output


def test_disk_usage_expands_tilde() -> None:
    registry = build_default_registry()
    result = registry.execute(ToolCall(name="disk_usage", arguments={"path": "~"}))
    assert result.ok is True
    assert "Total:" in result.output


def test_disk_usage_handles_missing_path() -> None:
    registry = build_default_registry()
    result = registry.execute(ToolCall(name="disk_usage", arguments={"path": "/nonexistent/path/xyz"}))
    assert result.ok is True
    assert "not found" in result.output.lower()
