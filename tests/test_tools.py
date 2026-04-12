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
    assert "disk_usage" in names
    assert "list_processes" in names


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


def test_list_processes_returns_process_table() -> None:
    registry = build_default_registry()
    result = registry.execute(ToolCall(name="list_processes", arguments={}))
    assert result.ok is True
    # ps aux always includes at least a few lines on any Unix system
    assert len(result.output.splitlines()) > 2


def test_list_processes_filter_narrows_results() -> None:
    registry = build_default_registry()
    # Filter by "python" — current test process guarantees at least one match
    result = registry.execute(ToolCall(name="list_processes", arguments={"filter": "python"}))
    assert result.ok is True
    assert "python" in result.output.lower()


def test_list_processes_filter_no_match_returns_message() -> None:
    registry = build_default_registry()
    result = registry.execute(ToolCall(
        name="list_processes",
        arguments={"filter": "zzz_definitely_not_running_xyzzy"},
    ))
    assert result.ok is True
    assert "no processes" in result.output.lower()


def test_run_command_truncates_stderr_on_failure() -> None:
    """Failed commands with huge stderr should be truncated to last 30 lines."""
    from unittest.mock import patch, MagicMock
    from app.tools import _run_command

    fake = MagicMock()
    fake.returncode = 1
    fake.stdout = ""
    # 50 lines of compiler noise + the real error at the end
    fake.stderr = "\n".join([f"  Compiling crate-{i} v0.1.0" for i in range(50)]
                            + ["error: linker `link.exe` not found"])

    with patch("app.tools.subprocess.run", return_value=fake):
        output = _run_command({"command": "pip install broken-pkg"})

    assert "earlier output truncated" in output
    assert "linker" in output
    # Should NOT contain the first compiler lines
    assert "crate-0" not in output
    assert "[exit code 1]" in output


def test_run_command_strips_non_ascii() -> None:
    """Garbled emoji bytes from Rust/maturin builds should be stripped."""
    from unittest.mock import patch, MagicMock
    from app.tools import _run_command

    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = "Hello \xf0\x9f\x93\xa6 world"  # raw bytes decoded as latin1
    fake.stderr = ""

    with patch("app.tools.subprocess.run", return_value=fake):
        output = _run_command({"command": "echo test"})

    # Non-ASCII bytes should be stripped, leaving clean text
    assert "Hello" in output
    assert "world" in output
    # No garbled bytes
    assert all(ord(c) < 128 or c in "\n\r\t" for c in output)


def test_run_command_uses_longer_timeout_for_pip() -> None:
    """pip install should get a 300s timeout, not 60s."""
    from unittest.mock import patch, MagicMock, call
    from app.tools import _run_command

    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = "Successfully installed foo"
    fake.stderr = ""

    with patch("app.tools.subprocess.run", return_value=fake) as mock_run:
        _run_command({"command": "pip install some-package"})
        assert mock_run.call_args[1]["timeout"] == 300

    with patch("app.tools.subprocess.run", return_value=fake) as mock_run:
        _run_command({"command": "echo hello"})
        assert mock_run.call_args[1]["timeout"] == 60
