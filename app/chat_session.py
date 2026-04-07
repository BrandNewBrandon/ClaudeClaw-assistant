"""Terminal chat REPL for assistant-runtime.

Lets you chat with any agent directly from the command line without needing
a messaging app.  Reuses the same infrastructure as the router (same model
runner, context builder, memory store, command handler, tool loop).

Usage
-----
  assistant chat                       # default agent from config
  assistant chat --agent builder       # specific agent
  assistant chat --chat-id work        # named session (separate transcript)

Special input
-------------
  /quit  or  /exit   — end the session
  Any other /command — handled by CommandHandler (same as in-chat commands)
  Ctrl-C / Ctrl-D    — clean exit
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

LOGGER = logging.getLogger(__name__)

SURFACE = "terminal"
ACCOUNT_ID = "primary"

# ANSI color helpers (disabled on Windows if not supported)
def _supports_color() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if not _supports_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def _dim(t: str) -> str:  return _c("2", t)
def _bold(t: str) -> str: return _c("1", t)
def _cyan(t: str) -> str: return _c("96", t)
def _yellow(t: str) -> str: return _c("93", t)
def _red(t: str) -> str:  return _c("91", t)


class TerminalChatSession:
    """Interactive REPL that connects a terminal user to a ClaudeClaw agent."""

    def __init__(
        self,
        *,
        agent_name: str | None = None,
        chat_id: str = "terminal",
        config_path: Path | None = None,
    ) -> None:
        self._chat_id = chat_id
        self._session_ids: dict[str, str] = {}  # chat_id -> last claude session_id

        # ── Load config ───────────────────────────────────────────────────────
        from .app_paths import get_config_file
        from .config_manager import load_raw_config
        from .config import load_config

        cfg_path = config_path or get_config_file()
        if not cfg_path.exists():
            raise RuntimeError(
                f"Config not found at {cfg_path}. Run 'assistant init' first."
            )

        self._app_config = load_config(cfg_path)
        raw = load_raw_config(cfg_path)

        project_root = self._app_config.project_root
        agents_dir = self._app_config.agents_dir
        shared_dir = self._app_config.shared_dir

        self._agent_name = agent_name or self._app_config.default_agent
        self._agents_dir = agents_dir
        self._working_dir = agents_dir / self._agent_name

        # ── Core infrastructure ───────────────────────────────────────────────
        from .claude_runner import ClaudeCodeRunner
        from .context_builder import ContextBuilder
        from .memory import MemoryStore
        from .runtime_state import RuntimeState
        from .agent_config import load_agent_config
        from .commands import CommandHandler

        self._runner = ClaudeCodeRunner(
            timeout_seconds=self._app_config.claude_timeout_seconds,
            model=self._app_config.claude_model,
            effort=self._app_config.claude_effort,
        )
        self._context_builder = ContextBuilder(agents_dir=agents_dir)
        self._memory = MemoryStore(shared_dir=shared_dir, agents_dir=agents_dir)
        self._runtime_state = RuntimeState()
        self._runtime_state.set_active_agent(self._agent_name, account_id=ACCOUNT_ID)

        from .cache import ResponseCache, CooldownTracker
        self._response_cache = ResponseCache(ttl_seconds=self._app_config.cache_ttl_seconds)
        self._cooldown = CooldownTracker(cooldown_seconds=self._app_config.cooldown_seconds_per_chat)
        self._cache_enabled = self._app_config.cache_enabled
        self._max_prompt_chars = self._app_config.max_prompt_chars

        self._commands = CommandHandler(
            agents_dir=agents_dir,
            default_model=self._app_config.claude_model,
            default_effort=self._app_config.claude_effort,
            model_runner=self._runner,
            memory_store=self._memory,
        )

    # ── Readline setup ────────────────────────────────────────────────────────

    def _setup_readline(self) -> None:
        try:
            import readline  # noqa: F401 — side-effect: enables arrow keys + history
        except ImportError:
            pass  # Windows without pyreadline — plain input() still works

    # ── Tool loop (mirrors router._generate_reply_with_tools) ────────────────

    def _run_tool_loop(self, user_message: str) -> str:
        from .tools import ToolLoop, ToolError, build_default_registry, is_obvious_web_request
        from .tools import ToolSpec, execute_shell_command
        from .model_runner import ModelRunnerError

        # ── Cooldown gate ────────────────────────────────────────────────────────
        if not self._cooldown.is_ready(self._chat_id):
            wait = self._cooldown.seconds_remaining(self._chat_id)
            return f"Please wait {wait:.0f} more second(s) before sending another message."

        # ── Response cache ───────────────────────────────────────────────────────
        if self._cache_enabled:
            cached = self._response_cache.get(self._chat_id, user_message)
            if cached is not None:
                return cached

        tool_registry = build_default_registry(self._working_dir)

        # Inline approval gate for run_command
        _cwd = str(self._working_dir)

        def _terminal_run_command(args: dict) -> str:
            cmd = str(args.get("command", "")).strip()
            if not cmd:
                return "command is required."
            print()
            print(_yellow("⚠️  Approval required:"))
            print(f"   {cmd}")
            try:
                answer = input(_yellow("   Run this command? [y/N]: ")).strip().lower()
            except (EOFError, KeyboardInterrupt):
                return "Command cancelled (no input)."
            if answer in ("y", "yes"):
                print(_dim("   Running…"))
                try:
                    return execute_shell_command(cmd, cwd=_cwd)
                except Exception as exc:
                    return f"Command failed: {exc}"
            return "Command cancelled."

        tool_registry.register(
            ToolSpec("run_command", "Run a shell command and return its output.", {"command": "shell command string"}),
            _terminal_run_command,
        )

        tool_loop = ToolLoop(tool_registry, max_tool_calls=3)

        recent_transcript = self._memory.read_recent_transcript(
            SURFACE, self._chat_id, limit=6, account_id=ACCOUNT_ID
        )
        relevant_memory = self._memory.find_relevant_memory(
            self._agent_name, user_message, limit=4
        )
        agent_context = self._context_builder.load_agent_context(self._agent_name)
        prior_session_id = self._session_ids.get(self._chat_id)

        require_tool = is_obvious_web_request(user_message)
        tool_results: list[str] = []
        last_output = ""
        last_session_id: str | None = None

        for iteration in range(tool_loop.max_tool_calls + 1):
            prompt = self._context_builder.build_prompt(
                agent_context,
                user_message,
                recent_transcript=recent_transcript,
                relevant_memory=relevant_memory,
                tool_instructions=tool_loop.tool_instructions(
                    require_tool=require_tool and not tool_results
                ),
                tool_results=tool_results or None,
            )

            if self._max_prompt_chars and len(prompt) > self._max_prompt_chars:
                prompt = prompt[:self._max_prompt_chars]

            try:
                result = self._runner.run_prompt(
                    prompt=prompt,
                    working_directory=self._working_dir,
                    session_id=prior_session_id if iteration == 0 else None,
                )
            except ModelRunnerError as exc:
                return f"Error: {exc}"

            if result.session_id:
                last_session_id = result.session_id

            last_output = result.stdout.strip()
            if not last_output:
                return "(no response)"

            try:
                tool_call = tool_loop.parse_tool_call(last_output)
            except ToolError as exc:
                return f"Tool protocol error: {exc}"

            if tool_call is None:
                break

            # Execute tool
            print(_dim(f"   [tool: {tool_call.name}]"))
            tool_result = tool_loop.execute(tool_call)
            formatted = tool_loop.format_tool_result(tool_result)
            tool_results.append(formatted)

        if last_session_id:
            self._session_ids[self._chat_id] = last_session_id

        final = last_output or "(no response)"
        self._cooldown.record(self._chat_id)
        if self._cache_enabled and final != "(no response)":
            self._response_cache.set(self._chat_id, user_message, final)
        return final

    # ── Main REPL ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        self._setup_readline()

        # Verify agent exists
        if not (self._agents_dir / self._agent_name).exists():
            print(_red(f"Agent '{self._agent_name}' not found in {self._agents_dir}"))
            print("Run 'assistant manage list-agents' to see available agents.")
            return

        model_label = self._app_config.claude_model or "default model"
        print()
        print(_bold(f"  assistant-runtime  ·  {self._agent_name}"))
        print(_dim(f"  Model: {model_label}  |  Chat: {self._chat_id}  |  /help for commands  |  /exit to quit"))
        print()

        while True:
            # Build prompt string showing active agent
            prompt_str = _cyan(f"[{self._agent_name}] ") + "> "
            try:
                user_input = input(prompt_str).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                print(_dim("  Goodbye."))
                break

            if not user_input:
                continue

            # Exit commands
            if user_input.lower() in ("/quit", "/exit", "quit", "exit"):
                print(_dim("  Goodbye."))
                break

            # Log incoming message
            self._memory.append_transcript(
                surface=SURFACE,
                account_id=ACCOUNT_ID,
                chat_id=self._chat_id,
                direction="in",
                agent=self._agent_name,
                message_text=user_input,
                metadata={"kind": "terminal"},
            )

            # ── Slash command handling ─────────────────────────────────────
            if self._commands.is_command(user_input):
                from .agent_config import load_agent_config
                try:
                    agent_config = load_agent_config(self._agents_dir / self._agent_name)
                except Exception:
                    agent_config = None

                memory_preview = self._memory.find_relevant_memory(
                    self._agent_name, user_input, limit=4
                )
                reply, switch_to, reset_chat, remember_text = self._commands.handle(
                    user_input,
                    active_agent=self._agent_name,
                    default_agent=self._app_config.default_agent,
                    runtime_state=self._runtime_state,
                    current_agent_config=agent_config,
                    account_id=ACCOUNT_ID,
                    memory_preview=memory_preview,
                    chat_id=self._chat_id,
                    surface=SURFACE,
                    working_directory=self._working_dir,
                )

                if switch_to:
                    self._agent_name = switch_to
                    self._working_dir = self._agents_dir / switch_to
                    self._runtime_state.set_active_agent(switch_to, account_id=ACCOUNT_ID)
                    print(_dim(f"  Switched to agent: {switch_to}"))

                if reset_chat:
                    self._session_ids.pop(self._chat_id, None)
                    print(_dim("  Session reset."))

                if remember_text:
                    self._memory.append_daily_note(self._agent_name, f"Remembered: {remember_text}")

                if reply:
                    print()
                    print(reply)
                    print()
                    self._memory.append_transcript(
                        surface=SURFACE,
                        account_id=ACCOUNT_ID,
                        chat_id=self._chat_id,
                        direction="out",
                        agent=self._agent_name,
                        message_text=reply,
                        metadata={"kind": "command_reply"},
                    )
                continue

            # ── Send to Claude ─────────────────────────────────────────────
            print(_dim("  [thinking…]"), end="\r")
            reply = self._run_tool_loop(user_input)
            # Clear the thinking line
            print(" " * 20, end="\r")

            print()
            print(reply)
            print()

            # Save transcript + daily note
            self._memory.append_transcript(
                surface=SURFACE,
                account_id=ACCOUNT_ID,
                chat_id=self._chat_id,
                direction="out",
                agent=self._agent_name,
                message_text=reply,
                metadata={"kind": "assistant_reply"},
            )
            self._memory.append_daily_note(
                self._agent_name,
                f"User: {user_input}\n\nAssistant: {reply}",
            )
