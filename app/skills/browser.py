"""Browser skill — JavaScript-rendered page fetching and screenshots via Playwright.

Configuration
-------------
Requires ``playwright`` Python package and at least one browser installed:
    pip install playwright
    playwright install chromium

Tools (callable by Claude)
--------------------------
``browser_fetch(url)``            fetch rendered HTML as clean text
``browser_screenshot(url)``       take a screenshot, save to temp file, return path
"""
from __future__ import annotations

import os
import tempfile
from typing import Any

from ..plugins.base import SkillBase
from ..tools import ToolSpec


def _check_playwright() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _browser_fetch(args: dict[str, Any]) -> str:
    from playwright.sync_api import sync_playwright

    url = args.get("url", "").strip()
    if not url.startswith(("http://", "https://")):
        return "url must start with http:// or https://"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            # Extract text content without scripts/styles
            text = page.evaluate("""() => {
                const clone = document.documentElement.cloneNode(true);
                for (const el of clone.querySelectorAll('script,style,noscript,nav,footer,header')) {
                    el.remove();
                }
                return clone.innerText || clone.textContent || '';
            }""")
        finally:
            browser.close()

    if not isinstance(text, str):
        text = str(text)

    # Collapse whitespace
    import re
    text = re.sub(r"\r", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text).strip()

    if len(text) > 6000:
        text = text[:6000].rstrip() + "\n...[truncated]"
    return text or "(empty page)"


def _browser_screenshot(args: dict[str, Any]) -> str:
    from playwright.sync_api import sync_playwright

    url = args.get("url", "").strip()
    if not url.startswith(("http://", "https://")):
        return "url must start with http:// or https://"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            fd, path = tempfile.mkstemp(suffix=".png", prefix="screenshot_")
            os.close(fd)
            page.screenshot(path=path, full_page=False)
        finally:
            browser.close()

    return f"Screenshot saved to: {path}"


class BrowserSkill(SkillBase):
    name = "browser"
    version = "1.0"
    description = "Browser — JS-rendered page fetch and screenshots via Playwright"

    def is_available(self) -> bool:
        return _check_playwright()

    def tools(self):
        return [
            (
                ToolSpec(
                    "browser_fetch",
                    "Fetch a web page with full JavaScript rendering and return its readable text.",
                    {"url": "http(s) URL to render"},
                ),
                _browser_fetch,
            ),
            (
                ToolSpec(
                    "browser_screenshot",
                    "Take a screenshot of a web page and return the file path.",
                    {"url": "http(s) URL to screenshot"},
                ),
                _browser_screenshot,
            ),
        ]


SKILL_CLASS = BrowserSkill
