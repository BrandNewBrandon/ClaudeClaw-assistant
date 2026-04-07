from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .app_paths import get_config_file
from .agent_manager import AgentManager, AgentManagerError
from .config import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage assistant-runtime agents.")
    parser.add_argument(
        "--config",
        default=str(get_config_file()),
        help="Path to config.json",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-agents", help="List available agents")

    create_parser = subparsers.add_parser("create-agent", help="Create a new agent")
    create_parser.add_argument("name", help="Agent name (lowercase letters, numbers, dashes)")

    show_parser = subparsers.add_parser("show-agent", help="Show a single agent")
    show_parser.add_argument("name", help="Agent name")

    clone_parser = subparsers.add_parser("clone-agent", help="Clone an existing agent")
    clone_parser.add_argument("source", help="Source agent name")
    clone_parser.add_argument("target", help="Target agent name")

    rename_parser = subparsers.add_parser("rename-agent", help="Rename an agent")
    rename_parser.add_argument("source", help="Source agent name")
    rename_parser.add_argument("target", help="Target agent name")
    rename_parser.add_argument(
        "--force-main",
        action="store_true",
        help="Allow renaming the main agent",
    )

    archived_parser = subparsers.add_parser("list-archived-agents", help="List archived agents")

    restore_parser = subparsers.add_parser("restore-agent", help="Restore an archived agent")
    restore_parser.add_argument("archived_name", help="Archived directory name")
    restore_parser.add_argument("--as", dest="restored_name", help="Restore under a new agent name")

    subparsers.add_parser("show-routing", help="Show configured chat-to-agent routing")

    delete_parser = subparsers.add_parser("delete-agent", help="Archive an agent")
    delete_parser.add_argument("name", help="Agent name")
    delete_parser.add_argument("--yes", action="store_true", help="Confirm deletion/archive")
    delete_parser.add_argument(
        "--force-main",
        action="store_true",
        help="Allow deleting the main agent",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config = load_config(args.config)
    manager = AgentManager(project_root=config.project_root, agents_dir=config.agents_dir)

    try:
        if args.command == "list-agents":
            agents = manager.list_agents()
            if not agents:
                print("No agents found.")
                return 0
            for agent in agents:
                print(f"- {agent.name}")
                print(f"  display: {agent.config.display_name or '(none)'}")
                print(f"  description: {agent.config.description or '(none)'}")
                print(f"  provider: {agent.config.provider or config.model_provider}")
                print(f"  model: {agent.config.model or '(global default)'}")
                print(f"  effort: {agent.config.effort or '(global default)'}")
                print(
                    f"  files: AGENT.md={agent.has_agent_md} USER.md={agent.has_user_md} "
                    f"MEMORY.md={agent.has_memory_md} TOOLS.md={agent.has_tools_md}"
                )
            return 0

        if args.command == "create-agent":
            path = manager.create_agent(args.name)
            print(f"Created agent: {path}")
            return 0

        if args.command == "show-agent":
            agent = manager.show_agent(args.name)
            print(f"Name: {agent.name}")
            print(f"Path: {agent.path}")
            print(f"Display name: {agent.config.display_name or '(none)'}")
            print(f"Description: {agent.config.description or '(none)'}")
            print(f"Provider: {agent.config.provider or config.model_provider}")
            print(f"Model: {agent.config.model or '(global default)'}")
            print(f"Effort: {agent.config.effort or '(global default)'}")
            print(f"AGENT.md: {agent.has_agent_md}")
            print(f"USER.md: {agent.has_user_md}")
            print(f"MEMORY.md: {agent.has_memory_md}")
            print(f"TOOLS.md: {agent.has_tools_md}")
            return 0

        if args.command == "clone-agent":
            path = manager.clone_agent(args.source, args.target)
            print(f"Cloned agent to: {path}")
            return 0

        if args.command == "rename-agent":
            path = manager.rename_agent(args.source, args.target, force=args.force_main)
            print(f"Renamed agent to: {path}")
            return 0

        if args.command == "list-archived-agents":
            archived = manager.list_archived_agents()
            if not archived:
                print("No archived agents found.")
                return 0
            for path in archived:
                print(f"- {path.name}")
            return 0

        if args.command == "restore-agent":
            restored = manager.restore_agent(args.archived_name, restored_name=args.restored_name)
            print(f"Restored agent to: {restored}")
            return 0

        if args.command == "show-routing":
            if not config.chat_agent_map:
                print("No chat-agent routing configured.")
                return 0
            print("Configured chat routing:")
            for chat_id, agent_name in sorted(config.chat_agent_map.items()):
                print(f"- {chat_id} -> {agent_name}")
            return 0

        if args.command == "delete-agent":
            if not args.yes:
                print("Refusing to delete/archive without --yes")
                return 2
            archived_to = manager.delete_agent(args.name, force=args.force_main)
            print(f"Archived agent to: {archived_to}")
            return 0

        print(f"Unknown command: {args.command}")
        return 2
    except AgentManagerError as exc:
        print(f"Agent manager error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
