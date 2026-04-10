# Dev/Coding Agent Design

**Date:** 2026-04-10  
**Status:** Approved  
**Scope:** Turn the `builder-bot` account into a purpose-built dev agent — execution-biased persona, command approval whitelist, and per-agent working directory.

---

## Problem

The `builder-bot` account and `builder` agent directory exist from Phase 2, but the agent is a generic assistant with no dev-specific behavior. The differentiating value of ClaudeClaw over OpenClaw is local machine access — the builder should exploit this by defaulting to execution, running safe commands without friction, and working in real project repos.

Three gaps today:

1. **Persona** — no execution bias, no dev identity, no guidance on tool use style
2. **Approval friction** — every `run_command` call (including `git status`, `pytest`) requires a YES/NO prompt, making iterative dev work tedious
3. **Working directory** — `run_command` runs from the agent directory, not a project repo

---

## Goal

A builder bot that:
- Ships rather than advises — starts doing the work in the same turn
- Runs read-only and safe commands (git inspection, test runners, builds) without approval prompts
- Can be pointed at any local project repo via `agent.json`
- Still asks before destructive operations (`git push`, `rm`, installs)

---

## Design

### 1. Builder agent files

**`agents/builder/agent.json`**

```json
{
  "display_name": "Builder",
  "description": "Execution-biased dev assistant for local coding work",
  "model": "opus",
  "effort": "high",
  "working_dir": "~/Projects",
  "safe_commands": [
    "git status",
    "git log",
    "git diff",
    "git branch",
    "git show",
    "git stash list",
    "git remote",
    "pytest",
    "python -m pytest",
    "npm test",
    "npm run",
    "npx",
    "make",
    "cargo test",
    "cargo check",
    "cargo build",
    "ls",
    "cat",
    "grep",
    "find",
    "head",
    "tail",
    "wc",
    "echo"
  ]
}
```

**`agents/builder/AGENT.md`**

Dev-focused execution-biased persona. Key behaviors:
- Start doing the work in the same reply — never respond with only a plan
- Use tools freely; don't narrate routine calls (`git status`, `pytest`, etc.)
- State tradeoffs in one sentence, pick one, proceed
- Keep responses tight: code + one line of context, not essays
- Ask before destructive actions (`git push`, dropping data, irreversible changes)
- Work in the user's project repos, not the agent directory

**`agents/builder/TOOLS.md`**

Documents the local environment:
- Safe commands run without approval (listed above)
- Destructive commands always ask: `git push`, `git reset --hard`, `rm`, package installs
- How to reference project paths
- Working directory set to `~/Projects` — use `cd <repo> && <cmd>` for project-specific work

### 2. `AgentConfig` — two new fields

**File:** `app/agent_config.py`

Add to `AgentConfig` dataclass:
```python
safe_commands: tuple[str, ...] = ()   # command prefixes that skip approval gate
working_dir: str | None = None        # overrides _resolve_working_directory when set
```

`safe_commands` is stored as a tuple (frozen dataclass compatible). Loaded from `agent.json` as a list, converted to tuple on load.

`working_dir` is a raw string (may contain `~`), expanded to an absolute path at use time via `Path(working_dir).expanduser()`.

Update `load_agent_config` to read both fields:
```python
safe_commands=tuple(_optional_string_list(raw, "safe_commands")),
working_dir=_optional_string(raw, "working_dir"),
```

Add `_optional_string_list` helper (returns `list[str]`, empty list if missing/null).

### 3. Working directory override

**File:** `app/router.py`

In `_resolve_working_directory(agent_name)`, add a check before the existing mode logic:

```python
agent_config = self._load_agent_config(agent_name)
if agent_config.working_dir:
    path = Path(agent_config.working_dir).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path
```

Falls through to existing `claude_working_directory_mode` logic if `working_dir` is not set.

### 4. Command approval whitelist

**File:** `app/router.py`

In `_gated_run_command` (defined inline in `_generate_reply_with_tools`), before calling `_approval_store.request(...)`, check if the command matches any safe prefix:

```python
cmd = str(args.get("command", "")).strip()
agent_cfg = self._load_agent_config(_active_agent)
if any(cmd.startswith(prefix) for prefix in agent_cfg.safe_commands):
    return execute_shell_command(cmd, cwd=str(_working_dir))
```

Matching is prefix-based (`cmd.startswith(prefix)`). This is intentionally conservative — `"git status"` whitelists `git status --short` but not `git stash drop`. The check is case-sensitive.

There are two `_gated_run_command` definitions in `router.py` (streaming path and blocking path). Both need the same whitelist check.

---

## What Is Not Changing

- GitHub skill — already available to any agent when `GITHUB_TOKEN` is set; no changes needed
- Approval flow for non-whitelisted commands — unchanged
- Main bot approval behavior — unaffected (its `agent.json` has no `safe_commands`)
- `chat_session.py` terminal REPL — uses a separate approval flow; not updated (terminal REPL already shows a prompt inline, low friction)

---

## Testing

| Test | Where |
|------|-------|
| `safe_commands` parses from `agent.json` as tuple | `tests/test_agent_config.py` |
| Missing `safe_commands` defaults to empty tuple | `tests/test_agent_config.py` |
| `working_dir` parses from `agent.json` | `tests/test_agent_config.py` |
| Missing `working_dir` defaults to `None` | `tests/test_agent_config.py` |
| Whitelisted command prefix executes without approval | `tests/test_routing.py` |
| Non-whitelisted command hits approval gate | `tests/test_routing.py` |
| Prefix match is exact start (`"git status"` does not whitelist `"git push"`) | `tests/test_routing.py` |
| `working_dir` in agent config overrides `_resolve_working_directory` | `tests/test_routing.py` |

---

## Files Touched

| File | Change |
|------|--------|
| `agents/builder/agent.json` | Add `safe_commands`, `working_dir`, set model/effort |
| `agents/builder/AGENT.md` | Execution-biased dev persona |
| `agents/builder/TOOLS.md` | Local environment notes for builder |
| `app/agent_config.py` | Add `safe_commands`, `working_dir` fields + `_optional_string_list` helper |
| `app/router.py` | Whitelist check in both `_gated_run_command` closures; working dir override |
| `tests/test_agent_config.py` | New tests for both fields |
| `tests/test_routing.py` | New tests for whitelist logic and working dir override |
