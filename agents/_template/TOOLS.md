# Tools Available

All standard tools are available: `web_search`, `web_fetch`, `read_file`, `write_file`, `list_dir`, `disk_usage`, `list_processes`, `run_command`, `create_agent`, `bind_channel`, `list_imessage_chats`.

`run_command` is gated behind YES/NO approval unless the command matches an entry in `agent.json::safe_commands`.

`create_agent` and `bind_channel` mutate runtime state (create files, write secrets to the OS keyring, hot-reload the router). Use them only when the user explicitly asks to spawn a new agent or bind a new channel.
