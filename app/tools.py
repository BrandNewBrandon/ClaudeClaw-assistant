from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any, Callable


class ToolError(Exception):
    pass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    arguments: dict[str, str]


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    name: str
    ok: bool
    output: str


ToolHandler = Callable[[dict[str, Any]], str]


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def list_specs(self) -> list[ToolSpec]:
        return [self._specs[name] for name in sorted(self._specs)]

    def execute(self, call: ToolCall) -> ToolResult:
        handler = self._handlers.get(call.name)
        if handler is None:
            return ToolResult(name=call.name, ok=False, output=f"Unknown tool: {call.name}")
        try:
            output = handler(call.arguments)
            return ToolResult(name=call.name, ok=True, output=output.strip() or "(empty result)")
        except Exception as exc:
            return ToolResult(name=call.name, ok=False, output=f"{type(exc).__name__}: {exc}")


class ToolLoop:
    def __init__(self, registry: ToolRegistry, *, max_tool_calls: int = 3) -> None:
        self._registry = registry
        self._max_tool_calls = max_tool_calls

    def tool_instructions(self, *, require_tool: bool = False) -> str:
        lines = [
            "You may use tools when needed.",
            "If a tool is needed, reply with exactly one tool request in this format and nothing else:",
            "TOOL {\"name\": \"web_search\", \"arguments\": {\"query\": \"...\"}}",
            "After receiving tool results, you may either request another tool or provide the final user-facing answer.",
        ]
        if require_tool:
            lines.append("This request requires tool use before you answer. Do not answer from memory alone.")
        lines.append("Available tools:")
        for spec in self._registry.list_specs():
            args = ", ".join(f"{key}: {value}" for key, value in spec.arguments.items())
            lines.append(f"- {spec.name} — {spec.description} ({args})")
        return "\n".join(lines)

    def parse_tool_call(self, text: str) -> ToolCall | None:
        stripped = text.strip()
        if not stripped.startswith("TOOL "):
            return None
        payload = stripped.removeprefix("TOOL ").strip()
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ToolError(f"Invalid tool JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise ToolError("Tool payload must be a JSON object.")
        name = raw.get("name")
        arguments = raw.get("arguments", {})
        if not isinstance(name, str) or not name.strip():
            raise ToolError("Tool call missing valid name.")
        if not isinstance(arguments, dict):
            raise ToolError("Tool call arguments must be an object.")
        return ToolCall(name=name.strip(), arguments=arguments)

    def execute(self, call: ToolCall) -> ToolResult:
        return self._registry.execute(call)

    @staticmethod
    def format_tool_result(result: ToolResult) -> str:
        status = "ok" if result.ok else "error"
        return f"TOOL_RESULT {{\"name\": {json.dumps(result.name)}, \"status\": {json.dumps(status)}, \"output\": {json.dumps(result.output)} }}"

    @property
    def max_tool_calls(self) -> int:
        return self._max_tool_calls


def build_default_registry(
    working_directory: str | Path | None = None,
    agents_dir: Path | None = None,
    config_path: Path | None = None,
    router: Any = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="web_search",
            description="Search the web using DuckDuckGo instant HTML results.",
            arguments={"query": "string search query"},
        ),
        _web_search,
    )
    registry.register(
        ToolSpec(
            name="web_fetch",
            description="Fetch a web page and return cleaned readable text.",
            arguments={"url": "http(s) URL to fetch"},
        ),
        _web_fetch,
    )
    registry.register(
        ToolSpec(
            name="read_file",
            description="Read the contents of a local file.",
            arguments={"path": "absolute or relative file path"},
        ),
        _read_file,
    )
    registry.register(
        ToolSpec(
            name="write_file",
            description="Write or overwrite a local file with the given content.",
            arguments={"path": "absolute or relative file path", "content": "text content to write"},
        ),
        _write_file,
    )
    registry.register(
        ToolSpec(
            name="list_dir",
            description="List files and directories at a path.",
            arguments={"path": "absolute or relative directory path"},
        ),
        _list_dir,
    )
    registry.register(
        ToolSpec(
            name="disk_usage",
            description="Return disk usage (total, used, free) for the filesystem at the given path.",
            arguments={"path": "filesystem path to check (e.g. '/' or '~')"},
        ),
        _disk_usage,
    )
    registry.register(
        ToolSpec(
            name="list_processes",
            description="List running processes. Optional filter narrows results by name substring.",
            arguments={"filter": "optional process name substring to filter by (e.g. 'python', 'node')"},
        ),
        _list_processes,
    )
    _cwd = str(working_directory) if working_directory else None
    registry.register(
        ToolSpec(
            name="run_command",
            description="Run a shell command and return its output. Use with care.",
            arguments={"command": "shell command string to execute"},
        ),
        lambda args: _run_command(args, cwd=_cwd),
    )

    if agents_dir is not None:
        from .agent_provisioning import (
            ProvisioningError,
            bind_channel_impl,
            list_imessage_chats_impl,
            scaffold_agent,
        )

        _agents_dir = Path(agents_dir)
        _config_path = Path(config_path) if config_path is not None else None
        _router = router

        def _create_agent(args: dict[str, Any]) -> str:
            try:
                name = str(args.get("name", "")).strip()
                persona = str(args.get("persona", "")).strip()
                if not name or not persona:
                    return "Error: create_agent requires 'name' and 'persona'"
                display_name = str(args.get("display_name") or name.title())
                description = str(args.get("description") or "")
                target = scaffold_agent(
                    _agents_dir, name, display_name, persona, description
                )
                return (
                    f"Agent {name!r} scaffolded at {target}.\n\n"
                    f"Next step: bind a communication channel with\n"
                    f"  bind_channel(agent={name!r}, channel='telegram', token='...')\n"
                    f"Channels available: telegram, discord, slack, imessage."
                )
            except ProvisioningError as exc:
                return f"Error: {exc}"
            except Exception as exc:  # noqa: BLE001
                return f"Error (unexpected): {exc}"

        registry.register(
            ToolSpec(
                name="create_agent",
                description=(
                    "Scaffold a new sibling agent from the template. Creates agents/<name>/ "
                    "with agent.json, AGENT.md, TOOLS.md. After creation, call bind_channel "
                    "to wire up communication."
                ),
                arguments={
                    "name": "lowercase alnum+dash, 1-32 chars (e.g. 'finance')",
                    "persona": "persona paragraph written into the new agent's AGENT.md",
                    "display_name": "optional human-readable name (defaults to Title-cased name)",
                    "description": "optional short description",
                },
            ),
            _create_agent,
        )

        def _bind_channel(args: dict[str, Any]) -> str:
            try:
                if _config_path is None:
                    return "Error: config_path unavailable; bind_channel cannot write config"
                agent = str(args.get("agent", "")).strip()
                channel = str(args.get("channel", "")).strip().lower()
                token = args.get("token")
                app_token = args.get("app_token")
                chat_identifier = args.get("chat_identifier")
                # Pass router.add_account as the commit hook so failure
                # rolls back config and keyring atomically.
                commit_hook = _router.add_account if _router is not None else None
                result = bind_channel_impl(
                    _config_path,
                    agent=agent,
                    channel=channel,
                    token=str(token) if token else None,
                    app_token=str(app_token) if app_token else None,
                    chat_identifier=str(chat_identifier) if chat_identifier else None,
                    commit_hook=commit_hook,
                )
                reload_msg = " Router hot-reloaded — new bot is live." if _router is not None else ""
                return (
                    f"Bound {result['channel']} channel to agent {agent!r} "
                    f"({result['display']}). Account id: {result['account_id']}.{reload_msg}"
                )
            except ProvisioningError as exc:
                return f"Error: {exc}"
            except Exception as exc:  # noqa: BLE001
                return f"Error (unexpected): {exc}"

        registry.register(
            ToolSpec(
                name="bind_channel",
                description=(
                    "Bind a communication channel to an existing agent. Validates the token "
                    "with the platform API, stores it in the OS keyring, updates config.json, "
                    "and hot-reloads the router. Channels: telegram, discord, slack, imessage."
                ),
                arguments={
                    "agent": "target agent name (must already exist)",
                    "channel": "one of: telegram, discord, slack, imessage",
                    "token": "bot token (Telegram/Discord/Slack bot token)",
                    "app_token": "Slack app-level token (xapp-...), required when channel=slack",
                    "chat_identifier": "iMessage chat_identifier from list_imessage_chats",
                },
            ),
            _bind_channel,
        )

        def _list_imessage_chats(args: dict[str, Any]) -> str:
            try:
                limit_raw = args.get("limit", 20)
                limit = int(limit_raw) if str(limit_raw).strip() else 20
                chats = list_imessage_chats_impl(limit=limit)
                if not chats:
                    return "No recent iMessage chats found."
                lines = [
                    f"{i + 1}. {c['display_name'] or '(unnamed)'} — {c['chat_identifier']}"
                    for i, c in enumerate(chats)
                ]
                return "Recent iMessage chats:\n" + "\n".join(lines)
            except ProvisioningError as exc:
                return f"Error: {exc}"

        registry.register(
            ToolSpec(
                name="list_imessage_chats",
                description=(
                    "List recent Messages.app chats with their chat_identifier. Use before "
                    "bind_channel(channel='imessage', chat_identifier=...). macOS only."
                ),
                arguments={"limit": "max chats to return (default 20)"},
            ),
            _list_imessage_chats,
        )

    return registry


def is_obvious_web_request(text: str) -> bool:
    lowered = text.lower()
    indicators = [
        "search the web",
        "search for",
        "look up",
        "google",
        "find online",
        "fetch ",
        "open this page",
        "visit ",
        "http://",
        "https://",
        "www.",
        "website",
        "web page",
        "webpage",
        "docs",
    ]
    return any(indicator in lowered for indicator in indicators)


def _web_search(arguments: dict[str, Any]) -> str:
    query = _require_string(arguments, "query")
    url = "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
    request = urllib.request.Request(url, headers={"User-Agent": "assistant-runtime/0.1"})
    with urllib.request.urlopen(request, timeout=15) as response:
        html = response.read().decode("utf-8", errors="replace")

    matches = re.findall(
        r'<a[^>]*class="result__a"[^>]*href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    results: list[str] = []
    for href, title in matches[:5]:
        clean_title = _clean_html_text(title)
        clean_href = unescape(href)
        results.append(f"- {clean_title} — {clean_href}")
    if not results:
        return "No results found."
    return "\n".join(results)


def _web_fetch(arguments: dict[str, Any]) -> str:
    url = _require_string(arguments, "url")
    if not url.startswith(("http://", "https://")):
        raise ToolError("url must start with http:// or https://")
    request = urllib.request.Request(url, headers={"User-Agent": "assistant-runtime/0.1"})
    with urllib.request.urlopen(request, timeout=20) as response:
        content_type = response.headers.get("Content-Type", "")
        body = response.read().decode("utf-8", errors="replace")

    if "html" in content_type.lower() or "<html" in body.lower():
        text = _extract_readable_text(body)
    else:
        text = body.strip()

    if len(text) > 4000:
        text = text[:4000].rstrip() + "\n...[truncated]"
    return text or "(empty page)"


def _disk_usage(arguments: dict[str, Any]) -> str:
    raw = _require_string(arguments, "path")
    path = Path(raw).expanduser()
    if not path.exists():
        return f"Path not found: {raw}"
    try:
        usage = shutil.disk_usage(path)
    except OSError as exc:
        return f"Error reading disk usage: {exc}"
    total_gb = usage.total / 1e9
    used_gb = usage.used / 1e9
    free_gb = usage.free / 1e9
    pct = usage.used / usage.total * 100
    return (
        f"Disk usage at {path}\n"
        f"  Total: {total_gb:.1f} GB\n"
        f"  Used:  {used_gb:.1f} GB ({pct:.1f}%)\n"
        f"  Free:  {free_gb:.1f} GB"
    )


def _list_processes(arguments: dict[str, Any]) -> str:
    name_filter = str(arguments.get("filter", "")).strip().lower()
    try:
        proc = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return "Error: ps command timed out."
    except FileNotFoundError:
        return "Error: ps command not available on this system."

    if proc.returncode != 0:
        return f"Error: ps exited with code {proc.returncode}."

    lines = proc.stdout.splitlines()
    if not lines:
        return "No process output returned."

    rows = lines[1:]  # skip header

    if name_filter:
        rows = [r for r in rows if name_filter in r.lower()]
        if not rows:
            return f"No processes matching {name_filter!r}."

    total_matching = len(rows)
    rows = rows[:50]
    out_lines = ["  PID   %CPU   %MEM  COMMAND"]
    for row in rows:
        parts = row.split(None, 10)
        if len(parts) >= 11:
            out_lines.append(
                f"{parts[1]:>6}  {parts[2]:>5}  {parts[3]:>5}  {parts[10][:60]}"
            )
        else:
            out_lines.append(row[:80])

    result = "\n".join(out_lines)
    if total_matching > 50:
        result += f"\n\n(showing 50 of {total_matching} processes)"
    return result


def _require_string(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ToolError(f"Missing or invalid argument: {key}")
    return value.strip()


def _clean_html_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _read_file(arguments: dict[str, Any]) -> str:
    path_str = _require_string(arguments, "path")
    path = Path(path_str).expanduser()
    if not path.exists():
        raise ToolError(f"File not found: {path}")
    if not path.is_file():
        raise ToolError(f"Not a file: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > 8000:
        text = text[:8000].rstrip() + "\n...[truncated]"
    return text or "(empty file)"


def _write_file(arguments: dict[str, Any]) -> str:
    path_str = _require_string(arguments, "path")
    content = arguments.get("content", "")
    if not isinstance(content, str):
        raise ToolError("content must be a string")
    path = Path(path_str).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {path}"


def _list_dir(arguments: dict[str, Any]) -> str:
    path_str = _require_string(arguments, "path")
    path = Path(path_str).expanduser()
    if not path.exists():
        raise ToolError(f"Path not found: {path}")
    if not path.is_dir():
        raise ToolError(f"Not a directory: {path}")
    entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    lines: list[str] = []
    for entry in entries:
        prefix = "  " if entry.is_file() else "D "
        lines.append(f"{prefix}{entry.name}")
    return "\n".join(lines) if lines else "(empty directory)"


def execute_shell_command(command: str, *, cwd: str | None = None) -> str:
    """Execute a pre-approved shell command and return its output."""
    return _run_command({"command": command}, cwd=cwd)


def _run_command(arguments: dict[str, Any], *, cwd: str | None = None) -> str:
    command = _require_string(arguments, "command")
    # Allow longer timeout for package install commands
    timeout = 60
    _cmd_lower = command.lower()
    if any(k in _cmd_lower for k in ("pip install", "npm install", "cargo install",
                                      "apt install", "brew install", "choco install")):
        timeout = 300
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            cwd=cwd,
            env={**os.environ},
        )
    except subprocess.TimeoutExpired:
        raise ToolError(f"Command timed out after {timeout} seconds.")
    except OSError as exc:
        raise ToolError(f"Failed to run command: {exc}")

    output_parts: list[str] = []
    if result.stdout.strip():
        output_parts.append(result.stdout.strip())
    if result.stderr.strip():
        stderr = result.stderr.strip()
        # For failed builds, keep only the last portion — the actual error
        # messages. Rust/C++ compilers emit thousands of lines before the
        # real error; shipping all of it confuses the model and can exceed
        # message limits.
        if result.returncode != 0:
            stderr_lines = stderr.splitlines()
            if len(stderr_lines) > 30:
                stderr = "\n".join(
                    ["...[earlier output truncated]"] + stderr_lines[-30:]
                )
        output_parts.append(f"[stderr]\n{stderr}")
    output = "\n".join(output_parts)
    # Strip non-printable / garbled bytes that confuse the model (common in
    # Rust/C++ build output on Windows where emoji bytes get double-decoded).
    output = re.sub(r"[^\x20-\x7E\n\r\t]", "", output)
    if len(output) > 4000:
        output = output[:4000].rstrip() + "\n...[truncated]"
    exit_info = f"\n[exit code {result.returncode}]" if result.returncode != 0 else ""
    return (output or "(no output)") + exit_info


def _extract_readable_text(html: str) -> str:
    html = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<style\b[^>]*>.*?</style>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"</(p|div|section|article|h1|h2|h3|li|br)>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    text = re.sub(r"\r", "", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.strip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    return cleaned.strip()
