from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue

from .agent_config import AgentConfig, load_agent_config
from .channels import BaseChannel, ChannelError, ChannelMessage
from .channels.factory import build_channel
from .plugins import PluginRegistry, build_plugin_registry
from .claude_runner import ClaudeCodeRunner
from .commands import CommandHandler
from .config import AccountConfig, AppConfig, ConfigError, RoutingConfig, load_config
from .context_builder import ContextBuilder
from .instance_lock import InstanceLock, InstanceLockError
from .app_paths import get_config_file, get_runtime_lock_file, get_runtime_pid_file, get_state_dir
from .logging_utils import configure_logging
from .briefing import BriefingThread
from .memory import ConsolidationThread, MemoryStore
from .model_runner import ModelRunner, ModelRunnerError
from .runtime_state import RuntimeState
from .scheduler import Scheduler, TaskStore
from .sessions import SessionStore
from .approvals import ApprovalStore
from .cache import CooldownTracker, ResponseCache
from .tools import ToolCall, ToolError, ToolLoop, ToolSpec, build_default_registry, execute_shell_command, is_obvious_web_request


LOGGER = logging.getLogger(__name__)

# Human-friendly status lines shown while a tool is executing (streaming path).
_TOOL_STATUS: dict[str, str] = {
    "web_search":  "🔍 Searching the web…",
    "web_fetch":   "🌐 Fetching page…",
    "read_file":   "📄 Reading file…",
    "write_file":  "✏️ Writing file…",
    "list_dir":    "📁 Listing directory…",
    "run_command": "⚙️ Running command…",
}
_TOOL_STATUS_DEFAULT = "🔧 Using tool…"


def _extract_tool_name(text: str) -> str:
    """Return the tool name from a 'TOOL {...}' line, or '' on failure."""
    try:
        payload = text.strip().removeprefix("TOOL ").strip()
        return str(json.loads(payload).get("name", ""))
    except Exception:
        return ""


@dataclass
class AccountRuntime:
    account: AccountConfig
    routing: RoutingConfig
    channel: BaseChannel


class AssistantRouter:
    def __init__(self, config_path: str | Path | None = None) -> None:
        self._config_path = Path(config_path) if config_path else get_config_file()
        self._config: AppConfig | None = None
        self._account_runtimes: dict[str, AccountRuntime] = {}
        self._model_runner: ModelRunner | None = None
        self._context_builder: ContextBuilder | None = None
        self._memory: MemoryStore | None = None
        self._sessions: SessionStore | None = None
        self._commands: CommandHandler | None = None
        self._chat_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
        self._last_seen_message_ids: dict[str, int] = {}
        self._instance_lock: InstanceLock | None = None
        self._runtime_state = RuntimeState()
        self._primary_account_id = "primary"
        self._stop_event = threading.Event()
        self._worker_errors: Queue[tuple[str, Exception]] = Queue()
        self._tool_loop = ToolLoop(build_default_registry(), max_tool_calls=3)
        self._scheduler: Scheduler | None = None
        self._consolidation_thread: ConsolidationThread | None = None
        self._briefing_thread: BriefingThread | None = None
        self._session_ids: dict[str, str] = {}  # session_key -> last claude session_id
        self._plugin_registry: PluginRegistry | None = None
        self._approval_store = ApprovalStore()
        self._response_cache = ResponseCache()  # reconfigured after config load
        self._cooldown = CooldownTracker()      # reconfigured after config load

    def run(self) -> None:
        self._config = self._load_config()
        if "primary" not in self._config.accounts:
            self._primary_account_id = next(iter(self._config.accounts.keys()))
        configure_logging(self._config.shared_dir)
        LOGGER.info("Runtime startup: config loaded from %s", self._config_path)

        lock_path = get_runtime_lock_file()
        runtime_pid_path = get_runtime_pid_file()
        LOGGER.info("Runtime startup: lock path=%s pid path=%s", lock_path, runtime_pid_path)
        self._instance_lock = InstanceLock(lock_path)
        try:
            self._instance_lock.acquire()
            LOGGER.info("Runtime startup: lock acquired")
        except InstanceLockError as exc:
            LOGGER.error("Runtime startup: lock acquire failed: %s", exc)
            raise SystemExit(str(exc)) from exc

        runtime_pid_path.write_text(f"{os.getpid()}\n", encoding="utf-8")
        LOGGER.info("Runtime startup: wrote runtime pid %s", os.getpid())

        self._runtime_state.mark_started(
            process_id=os.getpid(),
            config_path=self._config_path,
            lock_path=lock_path,
            claude_model=self._config.claude_model,
            claude_effort=self._config.claude_effort,
        )

        self._initialize_runtime_components()

        LOGGER.info(
            "Assistant runtime started with %s account(s); primary account '%s' default agent '%s'",
            len(self._account_runtimes),
            self._primary_account_id,
            self._config.routing[self._primary_account_id].default_agent,
        )
        print(
            f"Assistant runtime started. Polling {len(self._account_runtimes)} Telegram account(s); "
            f"primary account '{self._primary_account_id}' uses default agent "
            f"'{self._config.routing[self._primary_account_id].default_agent}'."
        )

        if self._scheduler is not None:
            self._scheduler.start()
        if self._consolidation_thread is not None:
            self._consolidation_thread.start()
        if self._briefing_thread is not None:
            self._briefing_thread.start()

        worker_threads = self._start_account_workers()

        try:
            self._monitor_workers(worker_threads)
        except KeyboardInterrupt:
            LOGGER.info("Assistant runtime shutting down")
            print("Shutting down.")
            return
        finally:
            self._stop_event.set()
            if self._scheduler is not None:
                self._scheduler.stop()
            if self._consolidation_thread is not None:
                self._consolidation_thread.stop()
            if self._briefing_thread is not None:
                self._briefing_thread.stop()
            for account_runtime in self._account_runtimes.values():
                account_runtime.channel.stop()
            for thread in worker_threads:
                thread.join(timeout=1)
            try:
                get_runtime_pid_file().unlink(missing_ok=True)
            except OSError:
                pass
            if self._instance_lock is not None:
                self._instance_lock.release()

    def _initialize_runtime_components(self) -> None:
        assert self._config is not None

        self._response_cache = ResponseCache(ttl_seconds=self._config.cache_ttl_seconds)
        self._cooldown = CooldownTracker(cooldown_seconds=self._config.cooldown_seconds_per_chat)

        self._account_runtimes = {
            account_id: AccountRuntime(
                account=account,
                routing=self._config.routing[account_id],
                channel=build_channel(
                    account,
                    poll_timeout_seconds=self._config.telegram_poll_timeout_seconds,
                ),
            )
            for account_id, account in self._config.accounts.items()
        }
        # Start event-driven channels (Discord, Slack) before polling begins
        for account_runtime in self._account_runtimes.values():
            account_runtime.channel.start()
        self._model_runner = self._build_model_runner()
        self._model_runner.ensure_available()
        self._context_builder = ContextBuilder(agents_dir=self._config.agents_dir)
        self._memory = MemoryStore(shared_dir=self._config.shared_dir, agents_dir=self._config.agents_dir)
        self._sessions = SessionStore(shared_dir=self._config.shared_dir)

        if self._config.consolidation_enabled:
            self._consolidation_thread = ConsolidationThread(
                self._memory,
                self._model_runner,
                self._config.agents_dir,
                hour=self._config.consolidation_hour,
                keep_days=self._config.consolidation_keep_days,
                working_directory=self._config.project_root,
            )

        task_store = TaskStore(get_state_dir() / "tasks.db")
        self._scheduler = Scheduler(
            task_store,
            quiet_hours_start=self._config.quiet_hours_start,
            quiet_hours_end=self._config.quiet_hours_end,
        )
        for account_id, account_runtime in self._account_runtimes.items():
            ch = account_runtime.channel
            platform = account_runtime.account.platform
            # capture by value to avoid closure over loop variable
            def _make_sender(channel: BaseChannel) -> object:
                def _send(_surface: str, chat_id: str, text: str) -> None:
                    channel.send_message(chat_id, text)
                return _send
            self._scheduler.register_sender(f"{platform}:{account_id}", _make_sender(ch))
        # Also register primary account under its platform key as a fallback
        primary_runtime = self._account_runtimes.get(self._primary_account_id)
        if primary_runtime is not None:
            primary_platform = primary_runtime.account.platform
            primary_ch = primary_runtime.channel
            def _primary_send(_surface: str, chat_id: str, text: str) -> None:
                primary_ch.send_message(chat_id, text)
            self._scheduler.register_sender(primary_platform, _primary_send)

        self._briefing_thread = BriefingThread(
            task_store=task_store,
            memory_store=self._memory,
            model_runner=self._model_runner,
            agents_dir=self._config.agents_dir,
            default_agent=self._config.default_agent,
            enabled=self._config.briefing_enabled,
            times=self._config.briefing_times,
            working_directory=self._config.project_root,
        )
        for account_id, account_runtime in self._account_runtimes.items():
            ch = account_runtime.channel
            platform = account_runtime.account.platform
            key = f"{platform}:{account_id}"
            self._briefing_thread.register_sender(key, _make_sender(ch))
            for chat_id in account_runtime.account.allowed_chat_ids:
                self._briefing_thread.register_target(key, chat_id)

        user_skills_dir = get_state_dir().parent / "skills"
        self._plugin_registry = build_plugin_registry(user_skills_dir=user_skills_dir)

        self._commands = CommandHandler(
            agents_dir=self._config.agents_dir,
            default_model=self._config.claude_model,
            default_effort=self._config.claude_effort,
            default_provider=self._config.model_provider,
            scheduler=self._scheduler,
            memory_store=self._memory,
            model_runner=self._model_runner,
            plugin_registry=self._plugin_registry,
            briefing_thread=self._briefing_thread,
        )

    def _start_account_workers(self) -> list[threading.Thread]:
        self._stop_event.clear()
        workers: list[threading.Thread] = []
        for account_id, account_runtime in self._account_runtimes.items():
            thread = threading.Thread(
                target=self._account_worker,
                args=(account_id, account_runtime),
                name=f"channel-poll-{account_id}",
                daemon=True,
            )
            thread.start()
            workers.append(thread)
        return workers

    def _monitor_workers(self, worker_threads: list[threading.Thread]) -> None:
        while True:
            try:
                account_id, exc = self._worker_errors.get(timeout=0.5)
            except Empty:
                if self._stop_event.is_set():
                    return
                if any(not thread.is_alive() for thread in worker_threads):
                    dead = [thread.name for thread in worker_threads if not thread.is_alive()]
                    raise SystemExit(f"Account worker stopped unexpectedly: {', '.join(dead)}")
                continue

            self._runtime_state.mark_error(str(exc))
            raise SystemExit(f"Account worker failed for {account_id}: {exc}") from exc

    def _account_worker(self, account_id: str, account_runtime: AccountRuntime) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll_account_once(account_id, account_runtime)
            except Exception as exc:
                self._worker_errors.put((account_id, exc))
                return

    def _poll_account_once(self, account_id: str, account_runtime: AccountRuntime) -> None:
        try:
            messages = account_runtime.channel.get_updates()
            for message in messages:
                self._handle_message(account_id, message)
        except ChannelError as exc:
            self._runtime_state.mark_error(str(exc))
            LOGGER.exception("Channel error for account=%s", account_id)
            print(f"Channel error ({account_id}): {exc}", file=sys.stderr)
            if not self._stop_event.is_set():
                time.sleep(1)

    def _load_config(self) -> AppConfig:
        try:
            return load_config(self._config_path)
        except ConfigError as exc:
            raise SystemExit(f"Configuration error: {exc}") from exc

    def _handle_message(self, account_id: str, message: ChannelMessage) -> None:
        assert self._config is not None
        lock = self._chat_locks[self._chat_lock_key(account_id, message.chat_id)]
        with lock:
            self._handle_message_locked(account_id, message)

    def _handle_message_locked(self, account_id: str, message: ChannelMessage) -> None:
        assert self._config is not None
        assert self._model_runner is not None
        assert self._context_builder is not None
        assert self._memory is not None
        assert self._sessions is not None
        assert self._commands is not None

        account_runtime = self._account_runtimes[account_id]
        account = account_runtime.account
        routing = account_runtime.routing
        channel = account_runtime.channel
        surface = account.platform
        session_key = self._session_key(surface, account_id, message.chat_id)

        LOGGER.info("Received message account=%s chat_id=%s message_id=%s", account_id, message.chat_id, message.message_id)
        self._runtime_state.mark_message(message_id=message.message_id)

        if message.chat_id not in account.allowed_chat_ids:
            LOGGER.warning("Ignoring unauthorized chat_id=%s on account=%s", message.chat_id, account_id)
            print(f"Ignoring unauthorized chat_id={message.chat_id} on account={account_id}")
            return

        last_seen_key = self._chat_lock_key(account_id, message.chat_id)
        last_seen = self._last_seen_message_ids.get(last_seen_key)
        if last_seen is not None and message.message_id <= last_seen:
            LOGGER.info(
                "Skipping duplicate/old message account=%s chat_id=%s message_id=%s last_seen=%s",
                account_id,
                message.chat_id,
                message.message_id,
                last_seen,
            )
            return
        self._last_seen_message_ids[last_seen_key] = message.message_id

        active_agent, routing_source = self._resolve_agent_for_chat(message.chat_id, account_id=account_id)
        agent_config = self._load_agent_config(active_agent)
        self._runtime_state.set_active_agent(
            active_agent,
            account_id=account_id,
            display_name=agent_config.display_name,
            description=agent_config.description,
            routing_source=routing_source,
        )

        self._memory.append_transcript(
            surface=surface,
            account_id=account_id,
            chat_id=message.chat_id,
            direction="in",
            agent=active_agent,
            message_text=message.text,
            metadata={"message_id": message.message_id},
        )

        transcript_path = self._memory.transcript_path(surface, message.chat_id, account_id=account_id)
        self._runtime_state.set_transcript_path(transcript_path)

        # ── Approval gate: handle YES/NO for pending run_command approvals ──────
        if self._approval_store.has_pending(surface, account_id, message.chat_id):
            answer = message.text.strip().lower()
            if answer in ("yes", "y"):
                command = self._approval_store.pop(surface, account_id, message.chat_id)
                LOGGER.info("Command approved account=%s chat_id=%s command=%r", account_id, message.chat_id, command)
                working_dir = self._resolve_working_directory(active_agent)
                try:
                    result_text = execute_shell_command(command, cwd=str(working_dir))
                except Exception as exc:
                    result_text = f"Command failed: {exc}"
                channel.send_message(message.chat_id, result_text)
                self._memory.append_transcript(
                    surface=surface, account_id=account_id, chat_id=message.chat_id,
                    direction="out", agent=active_agent,
                    message_text=result_text, metadata={"kind": "command_approved"},
                )
                return
            elif answer in ("no", "n", "cancel"):
                self._approval_store.pop(surface, account_id, message.chat_id)
                LOGGER.info("Command denied account=%s chat_id=%s", account_id, message.chat_id)
                channel.send_message(message.chat_id, "Command cancelled.")
                self._memory.append_transcript(
                    surface=surface, account_id=account_id, chat_id=message.chat_id,
                    direction="out", agent=active_agent,
                    message_text="Command cancelled.", metadata={"kind": "command_denied"},
                )
                return
            else:
                # Any other message clears the pending approval and falls through normally
                self._approval_store.pop(surface, account_id, message.chat_id)
                LOGGER.info("Pending approval cleared by new message account=%s chat_id=%s", account_id, message.chat_id)

        # ── Cooldown gate ────────────────────────────────────────────────────────
        if not self._commands.is_command(message.text):
            if not self._cooldown.is_ready(message.chat_id):
                wait = self._cooldown.seconds_remaining(message.chat_id)
                reply = f"Please wait {wait:.0f} more second(s) before sending another message."
                channel.send_message(message.chat_id, reply)
                return

        # ── Response cache ───────────────────────────────────────────────────────
        if self._config.cache_enabled and not self._commands.is_command(message.text):
            cached = self._response_cache.get(message.chat_id, message.text)
            if cached is not None:
                LOGGER.info("Cache hit account=%s chat_id=%s", account_id, message.chat_id)
                channel.send_message(message.chat_id, cached)
                self._memory.append_transcript(
                    surface=surface, account_id=account_id, chat_id=message.chat_id,
                    direction="out", agent=active_agent,
                    message_text=cached, metadata={"kind": "cache_hit"},
                )
                return

        if self._commands.is_command(message.text):
            memory_preview = self._memory.find_relevant_memory(
                active_agent,
                message.text,
                limit=4,
            )
            reply, switch_agent_to, reset_chat, remember_text = self._commands.handle(
                message.text,
                active_agent=active_agent,
                default_agent=routing.default_agent,
                runtime_state=self._runtime_state,
                current_agent_config=agent_config,
                account_id=account_id,
                routing_source=routing_source,
                pinned_agent=routing.chat_agent_map.get(message.chat_id),
                memory_preview=memory_preview,
                chat_id=message.chat_id,
                surface=surface,
                working_directory=self._resolve_working_directory(active_agent),
            )
            if switch_agent_to:
                self._sessions.set_active_agent(message.chat_id, switch_agent_to, session_key=session_key)
                active_agent = switch_agent_to
                LOGGER.info("Switched account=%s chat_id=%s to agent=%s", account_id, message.chat_id, switch_agent_to)
            if reset_chat:
                self._sessions.reset_chat(message.chat_id, session_key=session_key)
                active_agent = routing.default_agent
                LOGGER.info("Reset session state for account=%s chat_id=%s", account_id, message.chat_id)
            if remember_text:
                self._memory.append_daily_note(active_agent, f"Remembered: {remember_text}")
                LOGGER.info("Stored explicit memory account=%s chat_id=%s agent=%s", account_id, message.chat_id, active_agent)

            reply_send_started = time.monotonic()
            channel.send_message(message.chat_id, reply)
            self._runtime_state.mark_reply_sent()
            LOGGER.info(
                "Reply timing account=%s chat_id=%s agent=%s kind=command total_ms=%s send_phase_ms=%s",
                account_id,
                message.chat_id,
                active_agent,
                self._runtime_state.last_message_duration_ms,
                int((time.monotonic() - reply_send_started) * 1000),
            )
            self._memory.append_transcript(
                surface=surface,
                account_id=account_id,
                chat_id=message.chat_id,
                direction="out",
                agent=active_agent,
                message_text=reply,
                metadata={"kind": "command_reply"},
            )
            return

        image_path = message.image_path
        already_sent = False
        try:
            agent_context = self._context_builder.load_agent_context(active_agent)
            recent_transcript = self._memory.read_recent_transcript(
                surface,
                message.chat_id,
                limit=6,
                account_id=account_id,
            )
            relevant_memory = self._memory.find_relevant_memory(
                active_agent,
                message.text,
                limit=4,
            )
            working_dir = self._resolve_working_directory(active_agent)
            prior_session_id = self._session_ids.get(session_key)
            reply, new_session_id, already_sent = self._generate_reply_with_tools(
                message_text=message.text,
                active_agent=active_agent,
                agent_context=agent_context,
                recent_transcript=recent_transcript,
                relevant_memory=relevant_memory,
                working_directory=working_dir,
                model=agent_config.model or self._config.claude_model,
                effort=agent_config.effort or self._config.claude_effort,
                session_id=prior_session_id,
                surface=surface,
                account_id=account_id,
                chat_id=message.chat_id,
                image_path=image_path,
                channel=channel,
            )
            if new_session_id:
                self._session_ids[session_key] = new_session_id
            self._cooldown.record(message.chat_id)
            if self._config.cache_enabled:
                self._response_cache.set(message.chat_id, message.text, reply)
        except Exception as exc:
            self._runtime_state.mark_error(str(exc))
            LOGGER.exception("Context or model execution failed for account=%s agent=%s", account_id, active_agent)
            reply = f"Runtime error: {exc}"
            new_session_id = None
        finally:
            # Clean up the temp image file regardless of success or failure
            if image_path:
                try:
                    Path(image_path).unlink(missing_ok=True)
                except OSError:
                    pass

        reply_send_started = time.monotonic()
        if not already_sent:
            channel.send_message(message.chat_id, reply)
        self._runtime_state.mark_reply_sent()
        LOGGER.info(
            "Reply timing account=%s chat_id=%s agent=%s kind=assistant total_ms=%s model_ms=%s send_phase_ms=%s",
            account_id,
            message.chat_id,
            active_agent,
            self._runtime_state.last_message_duration_ms,
            self._runtime_state.last_model_duration_ms,
            int((time.monotonic() - reply_send_started) * 1000),
        )
        self._memory.append_transcript(
            surface=surface,
            account_id=account_id,
            chat_id=message.chat_id,
            direction="out",
            agent=active_agent,
            message_text=reply,
            metadata={"kind": "assistant_reply"},
        )

        note = f"User: {message.text}\n\nAssistant: {reply}"
        self._memory.append_daily_note(active_agent, note)
        LOGGER.info("Replied account=%s chat_id=%s agent=%s", account_id, message.chat_id, active_agent)

    def _generate_reply_with_tools(
        self,
        *,
        message_text: str,
        active_agent: str,
        agent_context: object,
        recent_transcript: list,
        relevant_memory: list[str],
        working_directory: Path,
        model: str | None,
        effort: str | None,
        session_id: str | None = None,
        surface: str = "",
        account_id: str = "",
        chat_id: str = "",
        image_path: str | None = None,
        channel: "BaseChannel | None" = None,
    ) -> tuple[str, str | None, bool]:
        """Run the model + tool loop.

        Returns ``(reply_text, new_session_id, already_sent)`` where
        ``already_sent=True`` means the reply was delivered to the channel
        via live streaming edits and the caller must NOT call
        ``channel.send_message()`` again.
        """
        assert self._context_builder is not None
        assert self._model_runner is not None

        # If a photo was attached, append the file path so Claude can read it
        if image_path:
            message_text = (
                message_text
                + f"\n\n[Photo attached — saved at: {image_path} — use your file tools to read and analyze it.]"
            ).lstrip()

        # Determine whether we can stream to this channel
        can_stream = (
            channel is not None
            and hasattr(self._model_runner, "run_prompt_streaming")
            and hasattr(channel, "send_and_get_message_id")
        )

        # ── Streaming path ───────────────────────────────────────────────────────
        if can_stream:
            assert channel is not None
            streaming_result = self._run_streaming_tool_loop(
                channel=channel,
                chat_id=chat_id,
                message_text=message_text,
                active_agent=active_agent,
                agent_context=agent_context,
                recent_transcript=recent_transcript,
                relevant_memory=relevant_memory,
                working_directory=working_directory,
                model=model,
                effort=effort,
                session_id=session_id,
            )
            if streaming_result is not None:
                reply, new_session_id = streaming_result
                return reply, new_session_id, True  # already_sent=True
            # fall through to blocking path if streaming setup failed

        # ── Blocking (non-streaming) path ────────────────────────────────────────
        if self._plugin_registry is not None:
            tool_registry = self._plugin_registry.build_tool_registry(working_directory)
        else:
            tool_registry = build_default_registry(working_directory)

        # Replace run_command with an approval-gated wrapper
        _approval_store = self._approval_store
        _surface, _account_id, _chat_id = surface, account_id, chat_id
        _cwd = str(working_directory)

        def _gated_run_command(args: dict) -> str:
            cmd = str(args.get("command", "")).strip()
            if not cmd:
                return "command is required."
            return _approval_store.request(_surface, _account_id, _chat_id, cmd)

        tool_registry.register(
            ToolSpec("run_command", "Run a shell command and return its output. Use with care.", {"command": "shell command string to execute"}),
            _gated_run_command,
        )

        tool_loop = ToolLoop(tool_registry, max_tool_calls=3)
        skill_context = self._plugin_registry.get_context_text() if self._plugin_registry else ""
        tool_results: list[str] = []
        last_output = ""
        last_session_id: str | None = None
        require_tool = is_obvious_web_request(message_text)
        if require_tool:
            LOGGER.info("Tool-first heuristic triggered agent=%s message=%r", active_agent, message_text[:200])

        for iteration in range(tool_loop.max_tool_calls + 1):
            prompt = self._context_builder.build_prompt(
                agent_context,
                message_text,
                recent_transcript=recent_transcript,
                relevant_memory=relevant_memory,
                tool_instructions=tool_loop.tool_instructions(require_tool=require_tool and not tool_results),
                tool_results=tool_results,
                skill_context=skill_context or None,
            )

            assert self._config is not None
            max_chars = self._config.max_prompt_chars
            if max_chars and len(prompt) > max_chars:
                LOGGER.warning(
                    "Prompt truncated from %d to %d chars agent=%s chat_id=%s",
                    len(prompt), max_chars, active_agent, chat_id,
                )
                prompt = prompt[:max_chars]

            model_started_monotonic = time.monotonic()
            self._runtime_state.claude_model = model
            self._runtime_state.claude_effort = effort
            self._runtime_state.mark_model_started()
            try:
                result = self._model_runner.run_prompt(
                    prompt=prompt,
                    working_directory=working_directory,
                    model=model,
                    effort=effort,
                    session_id=session_id if iteration == 0 else None,
                )
            except ModelRunnerError as exc:
                self._runtime_state.mark_error(str(exc))
                raise
            self._runtime_state.mark_model_finished()
            self._runtime_state.set_last_model_duration_ms(int((time.monotonic() - model_started_monotonic) * 1000))

            if result.session_id:
                last_session_id = result.session_id

            last_output = result.stdout.strip()
            if not last_output:
                if result.stderr.strip():
                    return f"Claude returned no text. stderr:\n{result.stderr.strip()}", last_session_id, False
                return "(Claude returned an empty response.)", last_session_id, False

            try:
                tool_call = tool_loop.parse_tool_call(last_output)
            except ToolError as exc:
                LOGGER.warning("Tool protocol parse failure agent=%s error=%s output=%r", active_agent, exc, last_output[:200])
                return f"Tool protocol error: {exc}", last_session_id, False

            if tool_call is None:
                if require_tool and not tool_results:
                    LOGGER.info("Model skipped required tool on iteration=%s; forcing web_search fallback", iteration)
                    fallback_result = tool_loop.execute(self._infer_web_tool_call(message_text))
                    tool_results.append(tool_loop.format_tool_result(fallback_result))
                    LOGGER.info("Executed forced tool name=%s ok=%s", fallback_result.name, fallback_result.ok)
                    continue
                LOGGER.info("No tool call emitted agent=%s iteration=%s", active_agent, iteration)
                return last_output, last_session_id, False

            tool_result = tool_loop.execute(tool_call)
            formatted = tool_loop.format_tool_result(tool_result)
            tool_results.append(formatted)
            LOGGER.info("Executed tool name=%s ok=%s", tool_call.name, tool_result.ok)

        return last_output or "(No final response produced after tool loop.)", last_session_id, False

    def _run_streaming_tool_loop(
        self,
        *,
        channel: "BaseChannel",
        chat_id: str,
        message_text: str,
        active_agent: str,
        agent_context: object,
        recent_transcript: list,
        relevant_memory: list[str],
        working_directory: Path,
        model: str | None,
        effort: str | None,
        session_id: str | None,
    ) -> tuple[str, str | None] | None:
        """Streaming version of the tool loop.

        Sends a placeholder message to the channel, then edits it in real-time
        as Claude generates text.  Tool calls swap the message content to a
        friendly status line, then resume streaming for Claude's final reply.

        Returns ``(reply_text, session_id)`` on success, or ``None`` if the
        streaming setup failed (caller should fall back to blocking path).
        """
        assert self._context_builder is not None
        assert self._model_runner is not None

        # Build the tool loop + approval gate (same as blocking path)
        if self._plugin_registry is not None:
            tool_registry = self._plugin_registry.build_tool_registry(working_directory)
        else:
            tool_registry = build_default_registry(working_directory)

        _approval_store = self._approval_store
        _surface = ""  # surface not needed for the approval gating display here
        _chat_id = chat_id

        def _gated_run_command(args: dict) -> str:
            cmd = str(args.get("command", "")).strip()
            if not cmd:
                return "command is required."
            return _approval_store.request(_surface, "", _chat_id, cmd)

        tool_registry.register(
            ToolSpec("run_command", "Run a shell command and return its output.", {"command": "shell command string"}),
            _gated_run_command,
        )

        tool_loop = ToolLoop(tool_registry, max_tool_calls=3)
        skill_context = self._plugin_registry.get_context_text() if self._plugin_registry else ""
        require_tool = is_obvious_web_request(message_text)

        # Send the initial ▌ placeholder and capture its message_id
        try:
            message_id = channel.send_and_get_message_id(chat_id, "▌")
        except Exception as exc:
            LOGGER.warning("Streaming: failed to send placeholder message: %s", exc)
            return None  # fall back to blocking
        if message_id is None:
            return None  # channel doesn't support editing

        last_session_id: str | None = None
        tool_results: list[str] = []
        last_output = ""

        for iteration in range(tool_loop.max_tool_calls + 1):
            prompt = self._context_builder.build_prompt(
                agent_context,
                message_text,
                recent_transcript=recent_transcript,
                relevant_memory=relevant_memory,
                tool_instructions=tool_loop.tool_instructions(require_tool=require_tool and not tool_results),
                tool_results=tool_results,
                skill_context=skill_context or None,
            )

            assert self._config is not None
            max_chars = self._config.max_prompt_chars
            if max_chars and len(prompt) > max_chars:
                prompt = prompt[:max_chars]

            # --- streaming on_chunk callback ---
            buf: list[str] = []
            last_edit_time = [time.monotonic()]
            is_tool_response = [False]

            def _on_chunk(chunk: str, _buf: list = buf, _let: list = last_edit_time,
                          _itr: list = is_tool_response, _mid: int = message_id) -> None:
                _buf.append(chunk)
                accumulated = "".join(_buf)
                # Never show raw TOOL JSON — suppress streaming if tool call detected
                if not _itr[0] and accumulated.lstrip().startswith("TOOL "):
                    _itr[0] = True
                if _itr[0]:
                    return
                # Throttle Telegram edits to max 1 per 300 ms
                now = time.monotonic()
                if now - _let[0] >= 0.3:
                    try:
                        channel.edit_message(chat_id, _mid, accumulated + " ▌")
                        _let[0] = now
                    except Exception:
                        pass  # never abort streaming due to a Telegram error

            self._runtime_state.mark_model_started()
            model_t0 = time.monotonic()
            try:
                result = self._model_runner.run_prompt_streaming(  # type: ignore[attr-defined]
                    prompt=prompt,
                    working_directory=working_directory,
                    model=model,
                    effort=effort,
                    session_id=session_id if iteration == 0 else None,
                    on_chunk=_on_chunk,
                )
            except Exception as exc:
                self._runtime_state.mark_error(str(exc))
                LOGGER.exception("Streaming model call failed agent=%s iteration=%s", active_agent, iteration)
                try:
                    channel.edit_message(chat_id, message_id, f"Error: {exc}")
                except Exception:
                    pass
                return f"Runtime error: {exc}", last_session_id
            finally:
                self._runtime_state.mark_model_finished()
                self._runtime_state.set_last_model_duration_ms(
                    int((time.monotonic() - model_t0) * 1000)
                )

            if result.session_id:
                last_session_id = result.session_id

            # Use the canonical final text from the result event (always complete)
            last_output = result.stdout.strip()

            if not last_output:
                err_msg = f"Claude returned no text. stderr:\n{result.stderr.strip()}" if result.stderr.strip() else "(no response)"
                try:
                    channel.edit_message(chat_id, message_id, err_msg)
                except Exception:
                    pass
                return err_msg, last_session_id

            # Check for tool call
            try:
                tool_call = tool_loop.parse_tool_call(last_output)
            except ToolError as exc:
                err_msg = f"Tool protocol error: {exc}"
                try:
                    channel.edit_message(chat_id, message_id, err_msg)
                except Exception:
                    pass
                return err_msg, last_session_id

            if tool_call is None:
                # Web-search heuristic fallback
                if require_tool and not tool_results:
                    LOGGER.info("Streaming: forcing web_search fallback iteration=%s", iteration)
                    status = _TOOL_STATUS.get("web_search", _TOOL_STATUS_DEFAULT)
                    try:
                        channel.edit_message(chat_id, message_id, status)
                    except Exception:
                        pass
                    fallback_result = tool_loop.execute(self._infer_web_tool_call(message_text))
                    tool_results.append(tool_loop.format_tool_result(fallback_result))
                    # Reset buf for next iteration
                    buf.clear()
                    is_tool_response[0] = False
                    continue
                # Final answer — do a clean last edit (no cursor)
                try:
                    channel.edit_message(chat_id, message_id, last_output)
                except Exception:
                    pass
                LOGGER.info("Streaming: final reply agent=%s iteration=%s", active_agent, iteration)
                return last_output, last_session_id

            # Tool call: show friendly status, execute, continue loop
            tool_name = tool_call.name
            status = _TOOL_STATUS.get(tool_name, _TOOL_STATUS_DEFAULT)
            try:
                channel.edit_message(chat_id, message_id, status)
            except Exception:
                pass

            tool_result = tool_loop.execute(tool_call)
            tool_results.append(tool_loop.format_tool_result(tool_result))
            LOGGER.info("Streaming: executed tool name=%s ok=%s", tool_call.name, tool_result.ok)

            # Reset per-iteration streaming state for next pass
            buf.clear()
            is_tool_response[0] = False

        # Max iterations reached
        final = last_output or "(No final response after tool loop.)"
        try:
            channel.edit_message(chat_id, message_id, final)
        except Exception:
            pass
        return final, last_session_id

    def _infer_web_tool_call(self, message_text: str) -> ToolCall:
        lowered = message_text.lower()
        url_match = None
        for token in message_text.split():
            if token.startswith(("http://", "https://")):
                url_match = token.rstrip(").,]>")
                break
        if url_match or "fetch " in lowered or "open this page" in lowered or "visit " in lowered:
            url = url_match or message_text.strip()
            return ToolCall(name="web_fetch", arguments={"url": url})
        return ToolCall(name="web_search", arguments={"query": message_text.strip()})

    def _build_model_runner(self) -> ModelRunner:
        assert self._config is not None
        if self._config.model_provider == "claude-code":
            return ClaudeCodeRunner(
                timeout_seconds=self._config.claude_timeout_seconds,
                model=self._config.claude_model,
                effort=self._config.claude_effort,
            )
        raise SystemExit(f"Unsupported model provider: {self._config.model_provider}")

    def _resolve_agent_for_chat(self, chat_id: str, *, account_id: str | None = None) -> tuple[str, str]:
        assert self._config is not None
        assert self._sessions is not None

        resolved_account_id = account_id or self._primary_account_id
        routing = self._config.routing[resolved_account_id]
        session_key = self._session_key("telegram", resolved_account_id, chat_id)

        pinned_agent = routing.chat_agent_map.get(chat_id)
        if pinned_agent:
            return pinned_agent, "config"

        session_agent = self._sessions.get_active_agent(chat_id, routing.default_agent, session_key=session_key)
        if session_agent != routing.default_agent:
            return session_agent, "session"

        return routing.default_agent, "default"

    @staticmethod
    def _session_key(surface: str, account_id: str, chat_id: str) -> str:
        return f"{surface}:{account_id}:{chat_id}"

    @staticmethod
    def _chat_lock_key(account_id: str, chat_id: str) -> str:
        return f"{account_id}:{chat_id}"

    def _load_agent_config(self, agent_name: str) -> AgentConfig:
        assert self._config is not None
        agent_dir = self._config.agents_dir / agent_name
        return load_agent_config(agent_dir)

    def _resolve_working_directory(self, agent_name: str) -> Path:
        assert self._config is not None
        if self._config.claude_working_directory_mode == "agent_dir":
            path = self._config.agents_dir / agent_name
        else:
            path = self._config.project_root

        path.mkdir(parents=True, exist_ok=True)
        return path
