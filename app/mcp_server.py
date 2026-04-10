"""MCP stdio server for assistant-runtime.

Implements a subset of the Model Context Protocol (MCP) over stdin/stdout
using JSON-RPC 2.0 (newline-delimited).  Claude Code and other MCP clients
can connect to this server to invoke agents and read memory.

Protocol
--------
Supported JSON-RPC methods:
  initialize              MCP handshake
  tools/list              list available tools
  tools/call              invoke a tool
  resources/list          list available resources
  resources/read          read a resource

Tools exposed
-------------
  invoke_agent(agent_name, message, chat_id?)   run an agent, get reply
  list_agents()                                  list configured agents
  search_memory(agent_name, query)               keyword-search agent memory
  append_note(agent_name, content)               append text to agent MEMORY.md

Resources
---------
  memory://{agent_name}               agent MEMORY.md content
  transcript://{agent_name}/{chat_id} recent transcript messages

Usage
-----
  assistant mcp          # launch MCP server on stdio
  or pipe from Claude Code:
  claude --mcp-server 'python -m app.mcp_server'
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

MCP_VERSION = "2024-11-05"
SERVER_NAME = "assistant-runtime"
SERVER_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_paths() -> tuple[Path, Path]:
    """Return (agents_dir, shared_dir) from config or sensible defaults."""
    try:
        from .app_paths import get_config_file
        from .config_manager import load_raw_config

        cfg = load_raw_config(get_config_file())
        project_root = Path(cfg.get("project_root", ".")).expanduser()
        agents_dir = Path(cfg.get("agents_dir", str(project_root / "agents"))).expanduser()
        shared_dir = Path(cfg.get("shared_dir", str(project_root / "shared"))).expanduser()
        return agents_dir, shared_dir
    except Exception:
        cwd = Path.cwd()
        return cwd / "agents", cwd / "shared"


def _list_agent_names(agents_dir: Path) -> list[str]:
    if not agents_dir.exists():
        return []
    return sorted(d.name for d in agents_dir.iterdir() if d.is_dir())


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _tool_list_agents(agents_dir: Path, _args: dict[str, Any]) -> str:
    names = _list_agent_names(agents_dir)
    if not names:
        return "No agents configured."
    return "Available agents:\n" + "\n".join(f"  - {n}" for n in names)


def _tool_invoke_agent(agents_dir: Path, args: dict[str, Any]) -> str:
    agent_name = str(args.get("agent_name", "")).strip()
    message = str(args.get("message", "")).strip()
    chat_id = str(args.get("chat_id", "mcp")).strip() or "mcp"

    if not agent_name:
        return "agent_name is required."
    if not message:
        return "message is required."
    if not (agents_dir / agent_name).exists():
        return f"Agent not found: {agent_name}"

    try:
        from .claude_runner import ClaudeCodeRunner
        from .context_builder import ContextBuilder
        from .memory import MemoryStore
        from .app_paths import get_config_file
        from .config_manager import load_raw_config
        from .tools import ToolLoop, build_default_registry

        cfg = load_raw_config(get_config_file())
        project_root = Path(cfg.get("project_root", ".")).expanduser()
        shared_dir = Path(cfg.get("shared_dir", str(project_root / "shared"))).expanduser()
        semantic = cfg.get("semantic_search_enabled", True)

        runner = ClaudeCodeRunner(
            timeout_seconds=int(cfg.get("claude_timeout_seconds", 120)),
            model=cfg.get("claude_model"),
            effort=cfg.get("claude_effort"),
        )
        memory_store = MemoryStore(shared_dir=shared_dir, agents_dir=agents_dir)
        context_builder = ContextBuilder(agents_dir=agents_dir)
        tool_registry = build_default_registry(project_root)
        tool_loop = ToolLoop(tool_registry)

        context = context_builder.load_agent_context(agent_name)
        relevant_memory = memory_store.find_relevant_memory(agent_name, message, semantic=semantic)
        recent_transcript = memory_store.read_recent_transcript("mcp", chat_id)

        prompt = context_builder.build_prompt(
            context,
            message,
            recent_transcript=recent_transcript,
            relevant_memory=relevant_memory,
            tool_instructions=tool_loop.tool_instructions(),
        )

        result = runner.run_prompt(prompt, project_root)
        reply = result.stdout.strip() or "(no response)"

        memory_store.append_transcript(
            surface="mcp", chat_id=chat_id, direction="in",
            agent=agent_name, message_text=message,
        )
        memory_store.append_transcript(
            surface="mcp", chat_id=chat_id, direction="out",
            agent=agent_name, message_text=reply,
        )
        return reply

    except Exception as exc:
        LOGGER.exception("invoke_agent error")
        return f"Error invoking agent: {exc}"


def _tool_search_memory(agents_dir: Path, shared_dir: Path, args: dict[str, Any]) -> str:
    agent_name = str(args.get("agent_name", "")).strip()
    query = str(args.get("query", "")).strip()
    if not agent_name:
        return "agent_name is required."
    if not query:
        return "query is required."

    try:
        from .memory import MemoryStore
        from .app_paths import get_config_file
        from .config_manager import load_raw_config
        cfg = load_raw_config(get_config_file())
        semantic = cfg.get("semantic_search_enabled", True)
        store = MemoryStore(shared_dir=shared_dir, agents_dir=agents_dir)
        snippets = store.find_relevant_memory(agent_name, query, limit=8, semantic=semantic)
        if not snippets:
            return f"No relevant memory found for query: {query}"
        return "\n\n".join(f"- {s}" for s in snippets)
    except Exception as exc:
        return f"Error searching memory: {exc}"


def _tool_append_note(agents_dir: Path, args: dict[str, Any]) -> str:
    agent_name = str(args.get("agent_name", "")).strip()
    content = str(args.get("content", "")).strip()
    if not agent_name:
        return "agent_name is required."
    if not content:
        return "content is required."

    memory_path = agents_dir / agent_name / "MEMORY.md"
    if not (agents_dir / agent_name).exists():
        return f"Agent not found: {agent_name}"
    try:
        existing_size = memory_path.stat().st_size if memory_path.exists() else 0
        with memory_path.open("a", encoding="utf-8") as fh:
            if existing_size > 0:
                fh.write("\n\n")
            fh.write(content)
        return f"Appended {len(content)} chars to {agent_name}/MEMORY.md"
    except OSError as exc:
        return f"Error appending note: {exc}"


# ---------------------------------------------------------------------------
# Resource implementations
# ---------------------------------------------------------------------------

def _resource_memory(agents_dir: Path, agent_name: str) -> str:
    path = agents_dir / agent_name / "MEMORY.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _resource_transcript(shared_dir: Path, agent_name: str, chat_id: str) -> str:
    transcript_dir = shared_dir / "transcripts"
    # Find the most relevant transcript file for this agent/chat
    pattern = f"*-*-{chat_id}.jsonl"
    candidates = list(transcript_dir.glob(pattern)) if transcript_dir.exists() else []
    if not candidates:
        return ""
    path = candidates[0]
    lines = path.read_text(encoding="utf-8").splitlines()
    entries = []
    for line in lines[-50:]:
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            speaker = "User" if e.get("direction") == "in" else "Assistant"
            entries.append(f"[{e.get('timestamp', '')}] {speaker}: {e.get('message_text', '')}")
        except ValueError:
            pass
    return "\n".join(entries)


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 helpers
# ---------------------------------------------------------------------------

def _ok(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# ---------------------------------------------------------------------------
# Tool + resource schemas
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "name": "invoke_agent",
        "description": "Send a message to an assistant agent and get a reply.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Name of the agent to invoke"},
                "message": {"type": "string", "description": "The message to send"},
                "chat_id": {"type": "string", "description": "Optional chat session ID"},
            },
            "required": ["agent_name", "message"],
        },
    },
    {
        "name": "list_agents",
        "description": "List all configured assistant agents.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "search_memory",
        "description": "Keyword-search the long-term memory of an agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Agent whose memory to search"},
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["agent_name", "query"],
        },
    },
    {
        "name": "append_note",
        "description": "Append a note to an agent's long-term memory (MEMORY.md).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Target agent"},
                "content": {"type": "string", "description": "Text to append"},
            },
            "required": ["agent_name", "content"],
        },
    },
]


# ---------------------------------------------------------------------------
# Request dispatcher
# ---------------------------------------------------------------------------

class MCPServer:
    def __init__(self) -> None:
        self._agents_dir, self._shared_dir = _load_paths()

    def handle(self, req: dict[str, Any]) -> dict[str, Any] | None:
        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params") or {}

        if method == "initialize":
            return _ok(req_id, {
                "protocolVersion": MCP_VERSION,
                "capabilities": {"tools": {}, "resources": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            })

        if method == "notifications/initialized":
            return None  # no response needed

        if method == "tools/list":
            return _ok(req_id, {"tools": _TOOLS})

        if method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments") or {}
            result_text = self._call_tool(tool_name, arguments)
            return _ok(req_id, {
                "content": [{"type": "text", "text": result_text}],
                "isError": False,
            })

        if method == "resources/list":
            resources = self._build_resource_list()
            return _ok(req_id, {"resources": resources})

        if method == "resources/read":
            uri = params.get("uri", "")
            content = self._read_resource(uri)
            return _ok(req_id, {
                "contents": [{"uri": uri, "mimeType": "text/plain", "text": content}]
            })

        if method == "ping":
            return _ok(req_id, {})

        return _err(req_id, -32601, f"Method not found: {method}")

    def _call_tool(self, name: str, args: dict[str, Any]) -> str:
        if name == "list_agents":
            return _tool_list_agents(self._agents_dir, args)
        if name == "invoke_agent":
            return _tool_invoke_agent(self._agents_dir, args)
        if name == "search_memory":
            return _tool_search_memory(self._agents_dir, self._shared_dir, args)
        if name == "append_note":
            return _tool_append_note(self._agents_dir, args)
        return f"Unknown tool: {name}"

    def _build_resource_list(self) -> list[dict[str, Any]]:
        resources = []
        for agent_name in _list_agent_names(self._agents_dir):
            resources.append({
                "uri": f"memory://{agent_name}",
                "name": f"{agent_name} memory",
                "description": f"Long-term memory for agent {agent_name}",
                "mimeType": "text/markdown",
            })
            # List transcript files for this agent
            transcript_dir = self._shared_dir / "transcripts"
            if transcript_dir.exists():
                for tf in transcript_dir.glob("*.jsonl"):
                    # Extract chat_id from filename format: {surface}-{account_id}-{chat_id}.jsonl
                    parts = tf.stem.split("-")
                    chat_id = parts[-1] if len(parts) >= 3 else tf.stem
                    resources.append({
                        "uri": f"transcript://{agent_name}/{chat_id}",
                        "name": f"{agent_name} transcript ({chat_id})",
                        "description": f"Recent transcript for agent {agent_name}, chat {chat_id}",
                        "mimeType": "text/plain",
                    })
        return resources

    def _read_resource(self, uri: str) -> str:
        if uri.startswith("memory://"):
            agent_name = uri[len("memory://"):]
            return _resource_memory(self._agents_dir, agent_name)

        if uri.startswith("transcript://"):
            rest = uri[len("transcript://"):]
            parts = rest.split("/", 1)
            if len(parts) != 2:
                return ""
            agent_name, chat_id = parts
            return _resource_transcript(self._shared_dir, agent_name, chat_id)

        return ""


# ---------------------------------------------------------------------------
# Main stdio loop
# ---------------------------------------------------------------------------

def run_stdio() -> None:
    """Read JSON-RPC requests from stdin, write responses to stdout."""
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    server = MCPServer()

    stdin = sys.stdin
    stdout = sys.stdout

    while True:
        try:
            line = stdin.readline()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError as exc:
            resp = _err(None, -32700, f"Parse error: {exc}")
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()
            continue

        try:
            resp = server.handle(req)
        except Exception as exc:
            LOGGER.exception("MCP handler error")
            resp = _err(req.get("id"), -32603, f"Internal error: {exc}")

        if resp is not None:
            stdout.write(json.dumps(resp) + "\n")
            stdout.flush()


if __name__ == "__main__":
    run_stdio()
