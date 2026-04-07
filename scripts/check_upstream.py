#!/usr/bin/env python3
"""check_upstream.py — Compare a GitHub repo against the last-checked state.

Usage:
    python scripts/check_upstream.py https://github.com/owner/repo

On first run: prints the full file tree and last 30 commits, then saves state.
On subsequent runs: prints only commits and changed files since the last check.

Output is designed to be pasted directly to your assistant for gap analysis.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# State file path
# ---------------------------------------------------------------------------

def _get_state_file() -> Path:
    """Return the path to the upstream state file, creating parent dirs."""
    # Try to import from the project's app_paths module if available.
    # Fall back to a sensible platform default if the project isn't on sys.path.
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from app.app_paths import get_state_dir  # type: ignore
        state_dir = get_state_dir()
    except ImportError:
        import os
        if sys.platform == "darwin":
            state_dir = Path.home() / "Library" / "Application Support" / "assistant" / "state"
        elif os.name == "nt":
            local = os.environ.get("LOCALAPPDATA", "")
            state_dir = Path(local) / "assistant" / "state" if local else Path.home() / "AppData" / "Local" / "assistant" / "state"
        else:
            state_dir = Path.home() / ".local" / "state" / "assistant"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "upstream_state.json"


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _load_state(state_file: Path) -> dict:
    if state_file.exists():
        try:
            return json.loads(state_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"repos": {}}


def _save_state(state_file: Path, state: dict) -> None:
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

GITHUB_API = "https://api.github.com"
HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "assistant-runtime/check_upstream",
}


def _gh_get(url: str) -> object:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise SystemExit(f"Error: repo not found or not public — {url}") from exc
        if exc.code == 403:
            raise SystemExit(
                "Error: GitHub API rate limit exceeded. Wait a few minutes and try again.\n"
                f"URL: {url}"
            ) from exc
        raise SystemExit(f"GitHub API error {exc.code}: {url}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Network error: {exc.reason}") from exc


def _fetch_commits(slug: str, *, since_iso: str | None = None, per_page: int = 30) -> list[dict]:
    url = f"{GITHUB_API}/repos/{slug}/commits?per_page={per_page}"
    if since_iso:
        url += f"&since={since_iso}"
    data = _gh_get(url)
    if not isinstance(data, list):
        return []
    return data  # type: ignore[return-value]


def _fetch_file_tree(slug: str) -> list[dict]:
    url = f"{GITHUB_API}/repos/{slug}/git/trees/HEAD?recursive=1"
    data = _gh_get(url)
    if not isinstance(data, dict):
        return []
    return data.get("tree", [])  # type: ignore[return-value]


def _fetch_changed_files(slug: str, since_sha: str) -> list[str]:
    """Return a sorted, deduplicated list of files changed after since_sha."""
    # Compare base SHA to HEAD
    url = f"{GITHUB_API}/repos/{slug}/compare/{since_sha}...HEAD"
    try:
        data = _gh_get(url)
    except SystemExit:
        return []
    if not isinstance(data, dict):
        return []
    files = data.get("files", []) or []
    return sorted({f["filename"] for f in files if isinstance(f, dict) and "filename" in f})


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_tree(tree_items: list[dict]) -> str:
    """Summarise the file tree by top-level directory."""
    blob_paths = [item["path"] for item in tree_items if item.get("type") == "blob"]
    total = len(blob_paths)

    # Count files per top-level directory
    dir_counts: dict[str, int] = {}
    root_files = 0
    for path in blob_paths:
        parts = path.split("/")
        if len(parts) == 1:
            root_files += 1
        else:
            top = parts[0]
            dir_counts[top] = dir_counts.get(top, 0) + 1

    lines: list[str] = [f"File tree — {total} files across {len(dir_counts)} top-level directories:"]
    for top, count in sorted(dir_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {top}/  {count} files")
    if root_files:
        lines.append(f"  (root)  {root_files} files")
    return "\n".join(lines)


def _format_commits(commits: list[dict]) -> str:
    lines: list[str] = []
    for commit in commits:
        sha = commit.get("sha", "")[:7]
        info = commit.get("commit", {})
        message = info.get("message", "").splitlines()[0]
        date_raw = (info.get("author") or {}).get("date", "")
        date = date_raw[:10] if date_raw else "????"
        lines.append(f"  {sha}  {date}  {message}")
    return "\n".join(lines) if lines else "  (none)"


def _format_changed_files(files: list[str]) -> str:
    if not files:
        return "  (no file changes detected)"
    lines: list[str] = []
    # Group by top-level directory
    dir_files: dict[str, list[str]] = {}
    root_files: list[str] = []
    for f in files:
        parts = f.split("/")
        if len(parts) == 1:
            root_files.append(f)
        else:
            dir_files.setdefault(parts[0], []).append(f)
    for top in sorted(dir_files):
        lines.append(f"  {top}/")
        for f in dir_files[top]:
            lines.append(f"    {f}")
    for f in root_files:
        lines.append(f"  {f}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parse URL
# ---------------------------------------------------------------------------

def _parse_slug(url: str) -> str:
    """Extract 'owner/repo' from a GitHub URL or a bare slug."""
    url = url.rstrip("/")
    if url.startswith("http"):
        # https://github.com/owner/repo  →  owner/repo
        parts = url.split("github.com/", 1)
        if len(parts) != 2 or "/" not in parts[1]:
            raise SystemExit(f"Cannot parse GitHub URL: {url!r}")
        slug = "/".join(parts[1].split("/")[:2])
    elif "/" in url:
        slug = url
    else:
        raise SystemExit(f"Expected a GitHub URL or 'owner/repo' slug, got: {url!r}")
    return slug.removesuffix(".git")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)

    slug = _parse_slug(sys.argv[1])
    state_file = _get_state_file()
    state = _load_state(state_file)
    repos = state.setdefault("repos", {})

    now_iso = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    now_human = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    repo_state: dict = repos.get(slug, {})
    last_sha: str | None = repo_state.get("last_sha")
    last_checked: str | None = repo_state.get("last_checked")

    print(f"=== Upstream check: {slug} ===")
    print(f"Checked: {now_human}")

    if last_sha is None:
        # ---- First run: full snapshot ----------------------------------------
        print("Last checked: never (first run — showing full snapshot)\n")

        print("Fetching file tree…")
        tree = _fetch_file_tree(slug)
        print(_format_tree(tree))

        print()
        print("Fetching recent commits (up to 30)…")
        commits = _fetch_commits(slug, per_page=30)
        print(f"Recent commits ({len(commits)}):")
        print(_format_commits(commits))

        head_sha = commits[0]["sha"] if commits else None

    else:
        # ---- Subsequent run: changes since last SHA --------------------------
        since_human = last_checked[:10] if last_checked else "unknown date"
        print(f"Last checked: {since_human} (SHA: {last_sha[:7]})\n")

        # Fetch commits since last check date
        since_iso = last_checked  # ISO 8601 — GitHub API accepts this
        print("Fetching new commits…")
        new_commits = _fetch_commits(slug, since_iso=since_iso, per_page=100)

        # Filter out the last_sha commit itself (GitHub includes it)
        new_commits = [c for c in new_commits if c.get("sha") != last_sha]

        if not new_commits:
            print("No new commits since last check.")
            print("\n---")
            print(f"State file: {state_file}")
            return

        print(f"New commits ({len(new_commits)}) since last check:")
        print(_format_commits(new_commits))

        # Fetch changed files
        print()
        print("Fetching changed files…")
        changed = _fetch_changed_files(slug, last_sha)
        print(f"Changed/added files ({len(changed)}):")
        print(_format_changed_files(changed))

        head_sha = new_commits[0]["sha"] if new_commits else last_sha

    # ---- Save state ----------------------------------------------------------
    if head_sha:
        repos[slug] = {
            "last_sha": head_sha,
            "last_checked": now_iso,
        }
        state["repos"] = repos
        _save_state(state_file, state)

    print("\n---")
    print(f"State saved to: {state_file}")
    print("Paste this output to your assistant for gap analysis.")


if __name__ == "__main__":
    main()
