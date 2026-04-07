"""GitHub skill — search repos, list issues/PRs, create comments.

Configuration
-------------
Set the ``GITHUB_TOKEN`` environment variable to a personal access token or
fine-grained token with ``repo`` scope.  Without it the skill is unavailable.

Slash commands
--------------
``/gh issues <owner/repo>``       list open issues
``/gh prs <owner/repo>``          list open pull requests
``/gh search <query>``            search repositories

Tools (callable by Claude)
--------------------------
``github_list_issues(repo)``
``github_list_prs(repo)``
``github_search_repos(query)``
``github_create_comment(repo, issue_number, body)``
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from ..plugins.base import SkillBase
from ..tools import ToolSpec


_API = "https://api.github.com"


def _gh_get(path: str, token: str) -> Any:
    req = urllib.request.Request(
        f"{_API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "assistant-runtime/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _gh_post(path: str, token: str, payload: dict[str, Any]) -> Any:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{_API}{path}",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "assistant-runtime/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def _list_issues(args: dict[str, Any], token: str) -> str:
    repo = args.get("repo", "").strip()
    if not repo or "/" not in repo:
        return "repo must be in owner/repo format"
    items = _gh_get(f"/repos/{repo}/issues?state=open&per_page=20", token)
    if not items:
        return "No open issues."
    lines = [f"Open issues in {repo}:"]
    for issue in items[:20]:
        lines.append(f"  #{issue['number']} {issue['title']}")
    return "\n".join(lines)


def _list_prs(args: dict[str, Any], token: str) -> str:
    repo = args.get("repo", "").strip()
    if not repo or "/" not in repo:
        return "repo must be in owner/repo format"
    items = _gh_get(f"/repos/{repo}/pulls?state=open&per_page=20", token)
    if not items:
        return "No open pull requests."
    lines = [f"Open PRs in {repo}:"]
    for pr in items[:20]:
        lines.append(f"  #{pr['number']} {pr['title']} (@{pr['user']['login']})")
    return "\n".join(lines)


def _search_repos(args: dict[str, Any], token: str) -> str:
    query = args.get("query", "").strip()
    if not query:
        return "query is required"
    data = _gh_get(f"/search/repositories?q={urllib.parse.quote(query)}&per_page=10", token)
    items = data.get("items", [])
    if not items:
        return "No repositories found."
    lines = [f"GitHub repos matching '{query}':"]
    for repo in items:
        stars = repo.get("stargazers_count", 0)
        lines.append(f"  {repo['full_name']} ★{stars} — {repo.get('description') or ''}")
    return "\n".join(lines)


def _create_comment(args: dict[str, Any], token: str) -> str:
    repo = args.get("repo", "").strip()
    issue_number = args.get("issue_number")
    body = args.get("body", "").strip()
    if not repo or "/" not in repo:
        return "repo must be in owner/repo format"
    if not issue_number:
        return "issue_number is required"
    if not body:
        return "body is required"
    result = _gh_post(f"/repos/{repo}/issues/{issue_number}/comments", token, {"body": body})
    return f"Comment posted: {result.get('html_url', '(unknown URL)')}"


import urllib.parse  # noqa: E402  (needed by _search_repos above)


class GitHubSkill(SkillBase):
    name = "github"
    version = "1.0"
    description = "GitHub — search repos, list issues/PRs, create comments"

    def _token(self) -> str:
        return os.environ.get("GITHUB_TOKEN", "")

    def is_available(self) -> bool:
        return bool(self._token())

    def tools(self):
        token = self._token()
        return [
            (
                ToolSpec("github_list_issues", "List open issues for a GitHub repo.", {"repo": "owner/repo string"}),
                lambda args: _list_issues(args, token),
            ),
            (
                ToolSpec("github_list_prs", "List open pull requests for a GitHub repo.", {"repo": "owner/repo string"}),
                lambda args: _list_prs(args, token),
            ),
            (
                ToolSpec("github_search_repos", "Search GitHub repositories.", {"query": "search query string"}),
                lambda args: _search_repos(args, token),
            ),
            (
                ToolSpec(
                    "github_create_comment",
                    "Create a comment on a GitHub issue or PR.",
                    {"repo": "owner/repo", "issue_number": "integer issue/PR number", "body": "comment text"},
                ),
                lambda args: _create_comment(args, token),
            ),
        ]

    def commands(self):
        token = self._token()

        def _handle(text: str) -> str:
            parts = text.strip().split(maxsplit=2)
            if len(parts) < 2:
                return "Usage: /gh issues <repo> | /gh prs <repo> | /gh search <query>"
            sub = parts[1].lower()
            arg = parts[2].strip() if len(parts) > 2 else ""
            if sub == "issues":
                return _list_issues({"repo": arg}, token)
            if sub == "prs":
                return _list_prs({"repo": arg}, token)
            if sub == "search":
                return _search_repos({"query": arg}, token)
            return f"Unknown subcommand: {sub}. Try: issues, prs, search"

        return {"/gh": _handle}


SKILL_CLASS = GitHubSkill
