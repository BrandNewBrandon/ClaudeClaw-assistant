# Phase 3C — Local System Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `disk_usage` and `list_processes` tools to the default tool registry so agents can query disk space and running processes without hitting the approval gate.

**Architecture:** Two new handler functions (`_disk_usage`, `_list_processes`) added to `app/tools.py` using stdlib only (`shutil`, `subprocess` — both already imported). Both registered in `build_default_registry()`. Seven new tests in `tests/test_tools.py`.

**Tech Stack:** Python 3.11+, stdlib (`shutil`, `subprocess`, `pathlib`), pytest

---

## File Map

| File | Change |
|------|--------|
| `app/tools.py` | Add `import shutil` at top; add `_disk_usage` and `_list_processes` handler functions; register both in `build_default_registry()` |
| `tests/test_tools.py` | 7 new tests: disk_usage (real path, missing path, tilde expansion), list_processes (output, filter match, filter no-match), registry presence |

Note: `subprocess` is already imported in `app/tools.py` (line 6). Only `shutil` needs to be added.

---

## Task 1: `disk_usage` tool

**Files:**
- Modify: `app/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_tools.py` (after the existing tests):

```python
def test_disk_usage_returns_usage_for_real_path(tmp_path: Path) -> None:
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_tools.py::test_disk_usage_returns_usage_for_real_path \
       tests/test_tools.py::test_disk_usage_expands_tilde \
       tests/test_tools.py::test_disk_usage_handles_missing_path \
       -v
```

Expected: FAIL — `ToolResult(ok=False, ...)` because `disk_usage` is not registered

- [ ] **Step 3: Add `import shutil` and `_disk_usage` to `app/tools.py`**

Add `import shutil` after the existing `import subprocess` line (line 6):

```python
import shutil
```

Add `_disk_usage` handler before `_require_string` at the bottom of `tools.py`:

```python
def _disk_usage(args: dict[str, Any]) -> str:
    raw = _require_string(args, "path")
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
```

Register in `build_default_registry()` after the `list_dir` registration (before `run_command`):

```python
    registry.register(
        ToolSpec(
            name="disk_usage",
            description="Return disk usage (total, used, free) for the filesystem at the given path.",
            arguments={"path": "filesystem path to check (e.g. '/' or '~')"},
        ),
        _disk_usage,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_tools.py::test_disk_usage_returns_usage_for_real_path \
       tests/test_tools.py::test_disk_usage_expands_tilde \
       tests/test_tools.py::test_disk_usage_handles_missing_path \
       -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add app/tools.py tests/test_tools.py
git commit -m "feat: add disk_usage tool to default registry"
```

---

## Task 2: `list_processes` tool

**Files:**
- Modify: `app/tools.py`
- Test: `tests/test_tools.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_tools.py`:

```python
def test_list_processes_returns_process_table() -> None:
    registry = build_default_registry()
    result = registry.execute(ToolCall(name="list_processes", arguments={}))
    assert result.ok is True
    # ps aux always includes at least a few lines on any Unix system
    assert len(result.output.splitlines()) > 2


def test_list_processes_filter_narrows_results() -> None:
    import sys
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_tools.py::test_list_processes_returns_process_table \
       tests/test_tools.py::test_list_processes_filter_narrows_results \
       tests/test_tools.py::test_list_processes_filter_no_match_returns_message \
       -v
```

Expected: FAIL — `ToolResult(ok=False, ...)` because `list_processes` is not registered

- [ ] **Step 3: Add `_list_processes` to `app/tools.py`**

Add after `_disk_usage`:

```python
def _list_processes(args: dict[str, Any]) -> str:
    name_filter = str(args.get("filter", "")).strip().lower()
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

    lines = proc.stdout.splitlines()
    if not lines:
        return "No process output returned."

    rows = lines[1:]  # skip header

    if name_filter:
        rows = [r for r in rows if name_filter in r.lower()]
        if not rows:
            return f"No processes matching {name_filter!r}."

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

    total = len(lines) - 1
    result = "\n".join(out_lines)
    if total > 50:
        result += f"\n\n(showing 50 of {total} processes)"
    return result
```

Register in `build_default_registry()` after `disk_usage`:

```python
    registry.register(
        ToolSpec(
            name="list_processes",
            description="List running processes. Optional filter narrows results by name substring.",
            arguments={"filter": "optional process name substring to filter by (e.g. 'python', 'node')"},
        ),
        _list_processes,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_tools.py::test_list_processes_returns_process_table \
       tests/test_tools.py::test_list_processes_filter_narrows_results \
       tests/test_tools.py::test_list_processes_filter_no_match_returns_message \
       -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add app/tools.py tests/test_tools.py
git commit -m "feat: add list_processes tool to default registry"
```

---

## Task 3: Registry presence test

**Files:**
- Test: `tests/test_tools.py`

- [ ] **Step 1: Add registry test**

The existing `test_default_registry_lists_expected_tools` checks for the original 6 tools. Update it to also assert the two new tools are present:

```python
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
```

- [ ] **Step 2: Run the updated test**

```bash
pytest tests/test_tools.py::test_default_registry_lists_expected_tools -v
```

Expected: PASS (both new tools already registered from Tasks 1 and 2)

- [ ] **Step 3: Run the full suite**

```bash
pytest -v
```

Expected: ALL PASS — 111 total (104 existing + 7 new)

- [ ] **Step 4: Commit**

```bash
git add tests/test_tools.py
git commit -m "test: assert disk_usage and list_processes appear in default registry"
```
