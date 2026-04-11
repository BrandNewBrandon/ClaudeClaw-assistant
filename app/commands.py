from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .agent_config import AgentConfig, load_agent_config
from .runtime_state import RuntimeState

if TYPE_CHECKING:
    from .briefing import BriefingThread
    from .memory import MemoryStore
    from .model_runner import ModelRunner
    from .plugins import PluginRegistry
    from .scheduler import Scheduler


class CommandHandler:
    def __init__(
        self,
        agents_dir: Path,
        default_model: str | None = None,
        default_effort: str | None = None,
        default_provider: str = "claude-code",
        scheduler: Scheduler | None = None,
        memory_store: MemoryStore | None = None,
        model_runner: ModelRunner | None = None,
        plugin_registry: PluginRegistry | None = None,
        briefing_thread: BriefingThread | None = None,
    ) -> None:
        self._agents_dir = agents_dir
        self._default_model = default_model
        self._default_effort = default_effort
        self._default_provider = default_provider
        self._scheduler = scheduler
        self._memory_store = memory_store
        self._model_runner = model_runner
        self._plugin_registry = plugin_registry
        self._briefing_thread = briefing_thread

    def _persist_quiet_hours(self, start: str | None, end: str | None) -> None:
        """Write quiet hours to config.json so they survive restarts."""
        try:
            from .app_paths import get_config_file
            from .config_manager import update_config_values
            update_config_values(get_config_file(), {
                "quiet_hours_start": start,
                "quiet_hours_end": end,
            })
        except Exception:
            pass  # non-fatal — in-memory change already applied

    def _persist_briefing(self, enabled: bool, times: list[int]) -> None:
        """Write briefing settings to config.json so they survive restarts."""
        try:
            from .app_paths import get_config_file
            from .config_manager import update_config_values
            update_config_values(get_config_file(), {
                "briefing_enabled": enabled,
                "briefing_times": times,
            })
        except Exception:
            pass  # non-fatal — in-memory change already applied

    def is_command(self, text: str) -> bool:
        return text.strip().startswith("/")

    def list_agents(self) -> list[str]:
        if not self._agents_dir.exists():
            return []
        return sorted(path.name for path in self._agents_dir.iterdir() if path.is_dir())

    def get_agent_config(self, agent_name: str) -> AgentConfig:
        return load_agent_config(self._agents_dir / agent_name)

    def _effective_provider(self, agent_name: str, agent_config: AgentConfig | None = None) -> str:
        config = agent_config or self.get_agent_config(agent_name)
        return config.provider or self._default_provider

    def _effective_model(self, agent_name: str, agent_config: AgentConfig | None = None) -> str | None:
        config = agent_config or self.get_agent_config(agent_name)
        return config.model or self._default_model

    def _effective_effort(self, agent_name: str, agent_config: AgentConfig | None = None) -> str | None:
        config = agent_config or self.get_agent_config(agent_name)
        return config.effort or self._default_effort

    def handle(
        self,
        text: str,
        *,
        active_agent: str,
        default_agent: str,
        runtime_state: RuntimeState,
        current_agent_config: AgentConfig | None = None,
        account_id: str | None = None,
        routing_source: str | None = None,
        pinned_agent: str | None = None,
        memory_preview: list[str] | None = None,
        chat_id: str | None = None,
        surface: str = "telegram",
        working_directory: Path | None = None,
    ) -> tuple[str, str | None, bool, str | None]:
        """Handle a slash command.

        Returns ``(reply, switch_agent_to, reset_chat, remember_text)``.
        """
        stripped = text.strip()

        # ── /status ──────────────────────────────────────────────────────────
        if stripped == "/status":
            available_agents = self.list_agents()
            current_config = current_agent_config or self.get_agent_config(active_agent)
            effective_model = self._effective_model(active_agent, current_config)
            effective_effort = self._effective_effort(active_agent, current_config)
            return (
                "\n".join(
                    [
                        "Runtime status: up",
                        f"Process ID: {runtime_state.process_id or '(unknown)'}",
                        f"Started at: {runtime_state.started_at or '(unknown)'}",
                        f"Last message at: {runtime_state.last_message_at or '(none yet)'}",
                        f"Account: {account_id or runtime_state.account_id or 'primary'}",
                        f"Active agent: {active_agent}",
                        f"Active agent display name: {current_config.display_name or active_agent}",
                        f"Active agent description: {current_config.description or 'No description'}",
                        f"Default agent: {default_agent}",
                        f"Routing source: {routing_source or runtime_state.routing_source or '(unknown)'}",
                        f"Available agents: {', '.join(available_agents) if available_agents else '(none)'}",
                        f"Config path: {runtime_state.config_path or '(unknown)'}",
                        f"Lock path: {runtime_state.lock_path or '(unknown)'}",
                        f"Transcript path: {runtime_state.transcript_path or '(unknown)'}",
                        f"Provider: {self._effective_provider(active_agent, current_config)}",
                        f"Model: {effective_model or '(default)'}",
                        f"Effort: {effective_effort or '(default)'}",
                        f"Current/last message ID: {runtime_state.current_message_id or '(unknown)'}",
                        f"Typing started at: {runtime_state.typing_started_at or '(not started)'}",
                        f"Model started at: {runtime_state.model_started_at or '(not started)'}",
                        f"Model finished at: {runtime_state.model_finished_at or '(not finished)'}",
                        f"Last reply at: {runtime_state.last_reply_at or '(none yet)'}",
                        f"Last model duration ms: {runtime_state.last_model_duration_ms if runtime_state.last_model_duration_ms is not None else '(unknown)'}",
                        f"Last message duration ms: {runtime_state.last_message_duration_ms if runtime_state.last_message_duration_ms is not None else '(unknown)'}",
                        f"Last error: {runtime_state.last_error or '(none)'}",
                    ]
                ),
                None,
                False,
                None,
            )

        # ── /new, /reset, /session reset ─────────────────────────────────────
        if stripped in ("/new", "/reset", "/session reset"):
            return ("Session reset. Starting fresh.", None, True, None)

        # ── /compact ─────────────────────────────────────────────────────────
        if stripped == "/compact":
            return ("Compacting conversation history…", None, False, "__COMPACT__")

        # ── /hooks ───────────────────────────────────────────────────────────
        if stripped == "/hooks":
            return ("__HOOKS__", None, False, None)

        # ── /agents ──────────────────────────────────────────────────────────
        if stripped == "/agents":
            agents = self.list_agents()
            if not agents:
                return ("No agents available.", None, False, None)
            lines = ["Available agents:"]
            for agent_name in agents:
                config = self.get_agent_config(agent_name)
                lines.append(
                    f"- {agent_name}"
                    f" — {config.display_name or agent_name}"
                    f" | model: {self._effective_model(agent_name, config) or '(default)'}"
                    f" | effort: {self._effective_effort(agent_name, config) or '(default)'}"
                    f" | {config.description or 'No description'}"
                )
            return ("\n".join(lines), None, False, None)

        # ── /agent ───────────────────────────────────────────────────────────
        if stripped == "/agent":
            config = current_agent_config or self.get_agent_config(active_agent)
            return (
                "\n".join(
                    [
                        f"Active agent: {active_agent}",
                        f"Display name: {config.display_name or active_agent}",
                        f"Description: {config.description or 'No description'}",
                        f"Account: {account_id or runtime_state.account_id or 'primary'}",
                        f"Provider: {self._effective_provider(active_agent, config)}",
                        f"Model: {self._effective_model(active_agent, config) or '(default)'}",
                        f"Effort: {self._effective_effort(active_agent, config) or '(default)'}",
                        f"Routing: {routing_source or runtime_state.routing_source or '(unknown)'}",
                        "Use /agents to list options, /agent info <name> for details, or /agent switch <name> to change.",
                    ]
                ),
                None,
                False,
                None,
            )

        if stripped.startswith("/agent info "):
            requested = stripped.removeprefix("/agent info ").strip()
            if not requested:
                return ("Usage: /agent info <name>", None, False, None)
            if not (self._agents_dir / requested).exists():
                return (f"Unknown agent: {requested}", None, False, None)
            config = self.get_agent_config(requested)
            return (
                "\n".join(
                    [
                        f"Agent: {requested}",
                        f"Display name: {config.display_name or requested}",
                        f"Description: {config.description or 'No description'}",
                        f"Provider: {self._effective_provider(requested, config)}",
                        f"Model: {self._effective_model(requested, config) or '(default)'}",
                        f"Effort: {self._effective_effort(requested, config) or '(default)'}",
                    ]
                ),
                None,
                False,
                None,
            )

        if stripped.startswith("/agent switch "):
            if pinned_agent:
                return (
                    f"This chat is pinned to {pinned_agent} by config, so manual switching is disabled here.",
                    None,
                    False,
                    None,
                )
            requested = stripped.removeprefix("/agent switch ").strip()
            if not requested:
                return ("Usage: /agent switch <name>", None, False, None)
            if not (self._agents_dir / requested).exists():
                return (f"Unknown agent: {requested}", None, False, None)
            return (
                f"Switched active agent to {requested}. Your next non-command message will go to that agent.",
                requested,
                False,
                None,
            )

        # ── /model [new_model] ───────────────────────────────────────────────
        if stripped == "/model" or stripped.startswith("/model "):
            parts = stripped.split(maxsplit=1)
            current_config = current_agent_config or self.get_agent_config(active_agent)
            current = self._effective_model(active_agent, current_config) or "(default)"
            if len(parts) == 1:
                return (f"Current model: {current}\nUsage: /model <model-name> to change for this session.", None, False, None)
            new_model = parts[1].strip()
            if not new_model:
                return (f"Current model: {current}", None, False, None)
            return (f"Model override set to: {new_model}\n(Note: session-level model override requires runtime support — feature in progress.)", None, False, None)

        # ── /effort [level] ──────────────────────────────────────────────────
        if stripped == "/effort" or stripped.startswith("/effort "):
            parts = stripped.split(maxsplit=1)
            current_config = current_agent_config or self.get_agent_config(active_agent)
            current = self._effective_effort(active_agent, current_config) or "(default)"
            if len(parts) == 1:
                return (f"Current effort: {current}\nUsage: /effort <low|medium|high>", None, False, None)
            new_effort = parts[1].strip()
            if not new_effort:
                return (f"Current effort: {current}", None, False, None)
            return (f"Effort override set to: {new_effort}\n(Note: session-level effort override requires runtime support — feature in progress.)", None, False, None)

        # ── /tools ───────────────────────────────────────────────────────────
        if stripped == "/tools":
            from .tools import build_default_registry
            registry = build_default_registry()
            lines = ["Available tools:"]
            for spec in registry.list_specs():
                args = ", ".join(f"{k}: {v}" for k, v in spec.arguments.items())
                lines.append(f"- {spec.name} — {spec.description}\n  Args: {args}")
            return ("\n".join(lines), None, False, None)

        # ── /transcript [n] ──────────────────────────────────────────────────
        if stripped == "/transcript" or stripped.startswith("/transcript "):
            parts = stripped.split(maxsplit=1)
            limit = 6
            if len(parts) > 1:
                try:
                    limit = int(parts[1].strip())
                except ValueError:
                    return ("Usage: /transcript [number]", None, False, None)
            if self._memory_store is None or chat_id is None:
                return ("Transcript unavailable.", None, False, None)
            entries = self._memory_store.read_recent_transcript(
                surface, chat_id, limit=limit, account_id=account_id or "primary",
                agent_name=active_agent,
            )
            if not entries:
                return ("No transcript entries found.", None, False, None)
            lines = [f"Last {len(entries)} transcript entries:"]
            for entry in entries:
                direction = "You" if entry.direction == "in" else "Assistant"
                lines.append(f"[{entry.timestamp[:16]}] {direction}: {entry.message_text[:200]}")
            return ("\n".join(lines), None, False, None)

        # ── /search <query> ──────────────────────────────────────────────────
        if stripped.startswith("/search "):
            query = stripped.removeprefix("/search ").strip()
            if not query:
                return ("Usage: /search <query>", None, False, None)
            from .tools import _web_search
            try:
                result = _web_search({"query": query})
            except Exception as exc:
                result = f"Search failed: {exc}"
            return (result, None, False, None)

        # ── /remind <time> <message> ─────────────────────────────────────────
        if stripped.startswith("/remind "):
            rest = stripped.removeprefix("/remind ").strip()
            if not rest:
                return ("Usage: /remind <time> <message>\nExamples: /remind 10m meeting\n  /remind 2h check oven", None, False, None)
            parts = rest.split(maxsplit=1)
            if len(parts) < 2:
                return ("Usage: /remind <time> <message>", None, False, None)
            time_spec, message = parts[0], parts[1]
            if self._scheduler is None or chat_id is None:
                return ("Scheduler not available.", None, False, None)
            from .scheduler import SchedulerError, parse_fire_at
            try:
                fire_at = parse_fire_at(time_spec)
            except SchedulerError as exc:
                return (str(exc), None, False, None)
            task_id = self._scheduler.add_reminder(
                chat_id=chat_id,
                account_id=account_id or "primary",
                surface=surface,
                fire_at=fire_at,
                message=message,
            )
            local_time = fire_at.astimezone().strftime("%Y-%m-%d %H:%M %Z")
            return (f"Reminder set for {local_time}\nID: {task_id}", None, False, None)

        # ── /tasks ───────────────────────────────────────────────────────────
        if stripped == "/tasks":
            if self._scheduler is None or chat_id is None:
                return ("Scheduler not available.", None, False, None)
            tasks = self._scheduler.list_tasks(chat_id)
            if not tasks:
                return ("No pending tasks.", None, False, None)
            lines = [f"Pending tasks ({len(tasks)}):"]
            for task in tasks:
                local_time = task.fire_at.astimezone().strftime("%Y-%m-%d %H:%M %Z")
                label = task.payload.get("message", task.task_type)
                lines.append(f"- [{task.id}] {local_time} — {label}")
            return ("\n".join(lines), None, False, None)

        # ── /cancel <id> ─────────────────────────────────────────────────────
        if stripped.startswith("/cancel "):
            task_id = stripped.removeprefix("/cancel ").strip()
            if not task_id:
                return ("Usage: /cancel <task-id>", None, False, None)
            if self._scheduler is None:
                return ("Scheduler not available.", None, False, None)
            cancelled = self._scheduler.cancel_task(task_id)
            if cancelled:
                return (f"Task {task_id} cancelled.", None, False, None)
            return (f"No pending task found with ID {task_id!r}.", None, False, None)

        # ── /quiet ───────────────────────────────────────────────────────────
        if stripped == "/quiet" or stripped.startswith("/quiet "):
            if self._scheduler is None:
                return ("Scheduler not available.", None, False, None)
            parts = stripped.split(maxsplit=2)
            sub = parts[1].lower() if len(parts) > 1 else None
            qs, qe = self._scheduler.get_quiet_hours()

            if sub is None:
                # Show current status
                if qs and qe:
                    return (f"Quiet hours: enabled ({qs} – {qe})\nMessages will be deferred during this window.", None, False, None)
                return ("Quiet hours: disabled.\nUse /quiet set HH:MM HH:MM to configure, or /quiet on to enable.", None, False, None)

            if sub == "off":
                self._scheduler.set_quiet_hours(None, None)
                self._persist_quiet_hours(None, None)
                return ("Quiet hours disabled.", None, False, None)

            if sub == "on":
                if not qs or not qe:
                    return ("No quiet hours configured yet.\nUse /quiet set HH:MM HH:MM to set start and end times.", None, False, None)
                # Already have times — re-enable (times already stored)
                return (f"Quiet hours already enabled ({qs} – {qe}).", None, False, None)

            if sub == "set":
                if len(parts) < 4:
                    return ("Usage: /quiet set HH:MM HH:MM\nExample: /quiet set 22:00 08:00", None, False, None)
                new_start, new_end = parts[2], parts[3]
                # Validate both values
                import re as _re
                time_pattern = _re.compile(r"^\d{1,2}:\d{2}$")
                if not time_pattern.match(new_start) or not time_pattern.match(new_end):
                    return ("Invalid time format. Use HH:MM (24-hour), e.g. /quiet set 22:00 08:00", None, False, None)
                self._scheduler.set_quiet_hours(new_start, new_end)
                self._persist_quiet_hours(new_start, new_end)
                return (f"Quiet hours set: {new_start} – {new_end}\nMessages will be deferred during this window.", None, False, None)

            return ("Usage: /quiet  |  /quiet on  |  /quiet off  |  /quiet set HH:MM HH:MM", None, False, None)

        # ── /briefing ────────────────────────────────────────────────────────
        if stripped == "/briefing" or stripped.startswith("/briefing "):
            bt = self._briefing_thread
            if bt is None:
                return ("Briefing not available.", None, False, None)

            parts = stripped.split(maxsplit=2)
            sub = parts[1].lower() if len(parts) > 1 else None

            if sub is None:
                enabled = bt.get_enabled()
                times = bt.get_times()
                times_str = ", ".join(f"{h:02d}:00" for h in sorted(times)) if times else "none"
                status = "enabled" if enabled else "disabled"
                return (
                    f"Briefing: {status}\nScheduled times: {times_str}\n"
                    "Commands: /briefing now · /briefing on · /briefing off · "
                    "/briefing set <HH> [HH …] · /briefing add <HH> · /briefing remove <HH>",
                    None, False, None,
                )

            if sub == "now":
                text = bt.generate_briefing_text(active_agent, chat_id or "")
                return (text, None, False, None)

            if sub == "on":
                bt.set_enabled(True)
                self._persist_briefing(True, bt.get_times())
                times_str = ", ".join(f"{h:02d}:00" for h in sorted(bt.get_times())) or "none"
                return (f"Briefing enabled. Scheduled times: {times_str}", None, False, None)

            if sub == "off":
                bt.set_enabled(False)
                self._persist_briefing(False, bt.get_times())
                return ("Briefing disabled.", None, False, None)

            if sub == "set":
                if len(parts) < 3:
                    return ("Usage: /briefing set <HH> [HH …]\nExample: /briefing set 9 18", None, False, None)
                raw_hours = parts[2].split()
                try:
                    new_times = [int(h) for h in raw_hours]
                except ValueError:
                    return ("Invalid hour(s). Use integers 0–23, e.g. /briefing set 9 18", None, False, None)
                if not all(0 <= h <= 23 for h in new_times):
                    return ("Hours must be between 0 and 23.", None, False, None)
                bt.set_times(new_times)
                self._persist_briefing(bt.get_enabled(), new_times)
                times_str = ", ".join(f"{h:02d}:00" for h in sorted(new_times))
                return (f"Briefing times set: {times_str}", None, False, None)

            if sub == "add":
                if len(parts) < 3:
                    return ("Usage: /briefing add <HH>", None, False, None)
                try:
                    h = int(parts[2].strip())
                except ValueError:
                    return ("Invalid hour. Use an integer 0–23.", None, False, None)
                if not 0 <= h <= 23:
                    return ("Hour must be between 0 and 23.", None, False, None)
                current = bt.get_times()
                if h not in current:
                    current.append(h)
                    bt.set_times(current)
                    self._persist_briefing(bt.get_enabled(), current)
                times_str = ", ".join(f"{x:02d}:00" for x in sorted(bt.get_times()))
                return (f"Briefing times: {times_str}", None, False, None)

            if sub == "remove":
                if len(parts) < 3:
                    return ("Usage: /briefing remove <HH>", None, False, None)
                try:
                    h = int(parts[2].strip())
                except ValueError:
                    return ("Invalid hour. Use an integer 0–23.", None, False, None)
                current = [x for x in bt.get_times() if x != h]
                bt.set_times(current)
                self._persist_briefing(bt.get_enabled(), current)
                times_str = ", ".join(f"{x:02d}:00" for x in sorted(current)) or "none"
                return (f"Briefing times: {times_str}", None, False, None)

            return (
                "Usage: /briefing  |  /briefing now  |  /briefing on  |  /briefing off  |  "
                "/briefing set <HH> [HH …]  |  /briefing add <HH>  |  /briefing remove <HH>",
                None, False, None,
            )

        # ── /consolidate ─────────────────────────────────────────────────────
        if stripped == "/consolidate" or stripped.startswith("/consolidate "):
            if self._memory_store is None or self._model_runner is None:
                return ("Memory consolidation not available.", None, False, None)
            parts = stripped.split(maxsplit=1)
            keep_days = 3
            if len(parts) > 1:
                try:
                    keep_days = int(parts[1].strip())
                except ValueError:
                    return ("Usage: /consolidate [keep_days]", None, False, None)
            wdir = working_directory or Path(".")
            result = self._memory_store.consolidate_agent_notes(
                active_agent,
                self._model_runner,
                wdir,
                keep_days=keep_days,
            )
            return (result, None, False, None)

        # ── /remember ────────────────────────────────────────────────────────
        if stripped.startswith("/remember "):
            memory_text = stripped.removeprefix("/remember ").strip()
            if not memory_text:
                return ("Usage: /remember <text>", None, False, None)
            return (
                f"I'll remember that for {active_agent}: {memory_text}",
                None,
                False,
                memory_text,
            )

        # /note is an alias for /remember
        if stripped.startswith("/note "):
            memory_text = stripped.removeprefix("/note ").strip()
            if not memory_text:
                return ("Usage: /note <text>", None, False, None)
            return (
                f"Noted for {active_agent}: {memory_text}",
                None,
                False,
                memory_text,
            )

        # ── /memory ──────────────────────────────────────────────────────────
        if stripped == "/memory":
            preview_lines = memory_preview or []
            if not preview_lines:
                return ("No relevant memory found right now.", None, False, None)
            return (
                "\n".join(["Relevant memory:", *[f"- {line}" for line in preview_lines]]),
                None,
                False,
                None,
            )

        # ── /skills ───────────────────────────────────────────────────────────
        if stripped == "/skills":
            if self._plugin_registry is None:
                return ("Plugin registry not available.", None, False, None)
            lines = self._plugin_registry.status_lines()
            if not lines:
                return ("No skills registered.", None, False, None)
            return (
                "Installed skills (✓ available, ✗ unavailable):\n" + "\n".join(lines),
                None,
                False,
                None,
            )

        # ── /forward <target> <message> ──────────────────────────────────────
        if stripped.startswith("/forward "):
            rest = stripped.removeprefix("/forward ").strip()
            if not rest:
                return ("Usage: /forward <target> <message>\nTarget: chat_id (same surface) or surface:account:chat_id\nExample: /forward 99999 Hello", None, False, None)
            parts = rest.split(maxsplit=1)
            if len(parts) < 2:
                return ("Usage: /forward <target> <message>\nTarget: chat_id (same surface) or surface:account:chat_id", None, False, None)
            target, message = parts[0], parts[1]
            if self._scheduler is None:
                return ("Scheduler not available.", None, False, None)

            # Parse target: full format "surface:account_id:chat_id" or short "chat_id"
            if target.count(":") >= 2:
                target_parts = target.split(":", 2)
                surface_key = f"{target_parts[0]}:{target_parts[1]}"
                target_chat_id = target_parts[2]
            else:
                surface_key = surface
                target_chat_id = target

            from .scheduler import SchedulerError
            try:
                self._scheduler.send_to(surface_key, target_chat_id, message)
                return (f"Forwarded to {target_chat_id}.", None, False, None)
            except SchedulerError as exc:
                return (f"Forward failed: {exc}", None, False, None)
            except Exception as exc:
                return (f"Forward failed: {exc}", None, False, None)

        # ── /search-chat <query> ─────────────────────────────────────────────
        if stripped == "/search-chat" or stripped.startswith("/search-chat "):
            parts = stripped.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                return ("Usage: /search-chat <query>", None, False, None)
            query = parts[1].strip()
            if self._memory_store is None or chat_id is None:
                return ("Transcript unavailable.", None, False, None)
            results = self._memory_store.search_transcript(
                surface, chat_id, query,
                account_id=account_id or "primary",
                agent_name=active_agent,
                limit=10,
            )
            if not results:
                return (f"No matches for \"{query}\".", None, False, None)
            lines = [f"Search results for \"{query}\" ({len(results)} match{'es' if len(results) != 1 else ''}):"]
            for entry in results:
                direction = "You" if entry.direction == "in" else "Assistant"
                lines.append(f"[{entry.timestamp[:16]}] {direction}: {entry.message_text[:200]}")
            return ("\n".join(lines), None, False, None)

        # ── /export ──────────────────────────────────────────────────────────
        if stripped == "/export":
            if self._memory_store is None or chat_id is None:
                return ("Transcript unavailable.", None, False, None)
            entries = self._memory_store.read_recent_transcript(
                surface, chat_id, limit=200,
                account_id=account_id or "primary",
                agent_name=active_agent,
            )
            if not entries:
                return ("No transcript entries to export.", None, False, None)
            lines = [f"Transcript export ({len(entries)} entries):"]
            for entry in entries:
                direction = "You" if entry.direction == "in" else "Assistant"
                lines.append(f"[{entry.timestamp[:16]}] {direction}: {entry.message_text}")
            return ("\n".join(lines), None, False, None)

        # ── /help ─────────────────────────────────────────────────────────────
        if stripped == "/help":
            skill_commands: list[str] = []
            if self._plugin_registry:
                for skill in self._plugin_registry.available_skills:
                    for prefix in skill.commands():
                        skill_commands.append(f"{prefix} — {skill.description} (skill)")
            return (
                "\n".join([
                    "Available commands:",
                    "/status — runtime status",
                    "/agents — list available agents",
                    "/agent — current agent info",
                    "/agent info <name> — agent details",
                    "/agent switch <name> — switch active agent",
                    "/model [name] — show or change model",
                    "/effort [level] — show or change effort (low/medium/high)",
                    "/tools — list available tools",
                    "/skills — list installed skills",
                    "/transcript [n] — show last n transcript entries",
                    "/search-chat <query> — search conversation history",
                    "/export — export transcript as text",
                    "/search <query> — web search",
                    "/remind <time> <message> — set a reminder (e.g. /remind 10m check oven)",
                    "/tasks — list pending tasks",
                    "/cancel <id> — cancel a task",
                    "/forward <target> <message> — forward message to another chat",
                    "/quiet — show quiet hours status",
                    "/quiet set HH:MM HH:MM — set quiet hours (e.g. /quiet set 22:00 08:00)",
                    "/quiet on / off — enable or disable quiet hours",
                    "/briefing — show briefing status and times",
                    "/briefing now — send a briefing immediately",
                    "/briefing on / off — enable or disable scheduled briefings",
                    "/briefing set <HH> [HH …] — set briefing times (e.g. /briefing set 9 18)",
                    "/briefing add <HH> / remove <HH> — add or remove a briefing time",
                    "/consolidate [days] — consolidate daily notes into long-term memory",
                    "/remember <text> — save to daily notes",
                    "/note <text> — alias for /remember",
                    "/memory — show relevant memory snippets",
                    "/new — start a fresh conversation (resets session)",
                    "/reset — alias for /new",
                    "/compact — summarize older messages to free up context",
                    "/hooks — show registered event hooks",
                    "/session reset — reset chat session state",
                    *skill_commands,
                ]),
                None,
                False,
                None,
            )

        # ── skill command dispatch ────────────────────────────────────────────
        if self._plugin_registry is not None:
            skill_reply = self._plugin_registry.handle_command(stripped)
            if skill_reply is not None:
                return (skill_reply, None, False, None)

        return ("Unknown command. Try /help for a list of commands.", None, False, None)
