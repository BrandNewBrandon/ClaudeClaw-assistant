# Phase 3C — Local System Tools Design

**Date:** 2026-04-10  
**Status:** Approved  
**Scope:** Add `disk_usage` and `list_processes` tools to the default tool registry in `app/tools.py`.

---

## Problem

Phase 3C of the roadmap covers local system tools: process introspection, filesystem inspection, service checks, and local diagnostics. Most of this is already possible via `run_command`, but two common queries — disk usage and process listing — are read-only operations that should not require an approval gate. Neither `df` nor `ps` appears in any safe_commands list, so every query currently prompts the user for YES/NO.

Dedicated tools fix this by making these queries first-class, approval-free capabilities available to all agents.

---

## Goal

Two new tools registered in `build_default_registry()`:

1. **`disk_usage(path)`** — disk space (total/used/free/percent) for the filesystem at `path`
2. **`list_processes(filter?)`** — running processes (PID, name, CPU%, memory%), optionally filtered by name substring

No new dependencies. Service checks and raw system info are left to `run_command` — they're appropriate to gate behind approval.

---

## Design

### `disk_usage`

**Spec:**
```python
ToolSpec(
    name="disk_usage",
    description="Return disk usage for the filesystem at the given path.",
    arguments={"path": "filesystem path to check (e.g. '/' or '~/Projects')"},
)
```

**Implementation** — uses `shutil.disk_usage()` and `Path.expanduser()`:

```python
def _disk_usage(args: dict[str, Any]) -> str:
    raw = _require_string(args, "path")
    path = Path(raw).expanduser()
    if not path.exists():
        return f"Path not found: {raw}"
    usage = shutil.disk_usage(path)
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
```

**Error handling:** missing path returns a human-readable message; any `OSError` is caught and returned as an error string.

---

### `list_processes`

**Spec:**
```python
ToolSpec(
    name="list_processes",
    description="List running processes. Optional filter narrows by process name substring.",
    arguments={"filter": "optional name substring to filter by (e.g. 'python', 'node')"},
)
```

**Implementation** — calls `ps aux` via subprocess (macOS/Linux), parses output, applies filter:

```python
def _list_processes(args: dict[str, Any]) -> str:
    name_filter = str(args.get("filter", "")).strip().lower()
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return f"Error listing processes: {exc}"

    lines = result.stdout.splitlines()
    if not lines:
        return "No processes found."

    header = lines[0]
    rows = lines[1:]

    if name_filter:
        rows = [r for r in rows if name_filter in r.lower()]

    if not rows:
        return f"No processes matching {name_filter!r}."

    # Trim to PID, %CPU, %MEM, COMMAND columns for readability
    out_lines = [header]
    for row in rows[:50]:  # cap at 50 rows
        parts = row.split(None, 10)
        if len(parts) >= 11:
            out_lines.append(f"{parts[1]:>6}  {parts[2]:>5}  {parts[3]:>5}  {parts[10][:60]}")
        else:
            out_lines.append(row[:80])

    truncated = len(rows) > 50
    result_text = "\n".join(["  PID   %CPU   %MEM  COMMAND"] + out_lines[1:])
    if truncated:
        result_text += f"\n\n(showing 50 of {len(rows)} processes)"
    return result_text
```

**Error handling:** `TimeoutExpired` and `FileNotFoundError` (ps not available) return error strings.

---

### Registration

Both tools added to `build_default_registry()` in `app/tools.py`:

```python
registry.register(
    ToolSpec("disk_usage", "Return disk usage for the filesystem at the given path.", {"path": "filesystem path to check"}),
    _disk_usage,
)
registry.register(
    ToolSpec("list_processes", "List running processes. Optional filter narrows by name substring.", {"filter": "optional name substring to filter by"}),
    _list_processes,
)
```

---

## What Is Not Changing

- `service_status` — not added; `run_command` handles `launchctl list`, `systemctl status` etc. (gated appropriately)
- `system_info` — not added; `run_command` with `uname -a`, `hostname` etc. is sufficient
- No new dependencies — `shutil` and `subprocess` are stdlib
- Approval flow — not changed; these tools bypass the approval gate because they are registered as direct tool handlers (not via `run_command`)

---

## Testing

| Test | File |
|------|-------|
| `disk_usage` returns total/used/free for a real path | `tests/test_tools.py` |
| `disk_usage` handles missing path gracefully | `tests/test_tools.py` |
| `disk_usage` expands `~` in path | `tests/test_tools.py` |
| `list_processes` returns process output with header | `tests/test_tools.py` |
| `list_processes` filters by name substring | `tests/test_tools.py` |
| `list_processes` returns message when no match | `tests/test_tools.py` |
| Both tools appear in default registry tool list | `tests/test_tools.py` |

---

## Files Touched

| File | Change |
|------|--------|
| `app/tools.py` | Add `_disk_usage`, `_list_processes` handlers; add `shutil`, `subprocess` imports; register both in `build_default_registry()` |
| `tests/test_tools.py` | 7 new tests |
