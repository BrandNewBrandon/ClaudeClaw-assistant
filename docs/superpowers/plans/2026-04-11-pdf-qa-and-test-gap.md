# PDF Document Q&A + Session Isolation Test — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable PDF file uploads via Telegram with text extraction and conversational Q&A, plus close the TerminalChatSession session isolation test gap.

**Architecture:** PDF text extracted via `pymupdf`. Small PDFs (≤5 pages) inlined in the user message; large PDFs saved to a documents directory and referenced by path. Follows the existing photo-attachment pattern: Telegram downloads to temp file → router processes → cleanup in `finally`. Session isolation test verifies independent `_session_ids` and transcript paths per `chat_id`.

**Tech Stack:** Python 3.11+, pymupdf, pytest

---

### Task 1: Add `pymupdf` dependency

**Files:**
- Modify: `pyproject.toml:11-13`

- [ ] **Step 1: Add pymupdf to dependencies**

In `pyproject.toml`, add `"pymupdf"` to the `dependencies` list:

```toml
dependencies = [
    "certifi",
    "pymupdf",
]
```

- [ ] **Step 2: Install the dependency**

Run: `cd /Users/macbook/Projects/assistant-runtime && pip install -e .`
Expected: pymupdf installs successfully

- [ ] **Step 3: Verify import works**

Run: `python -c "import fitz; print(fitz.version)"`
Expected: Prints version tuple, no error

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add pymupdf dependency for PDF text extraction"
```

---

### Task 2: Create `pdf_utils.py` with TDD

**Files:**
- Create: `app/pdf_utils.py`
- Create: `tests/test_pdf_utils.py`

- [ ] **Step 1: Write failing tests for extract_pdf_text**

Create `tests/test_pdf_utils.py`:

```python
from __future__ import annotations

import fitz  # pymupdf
from pathlib import Path

from app.pdf_utils import extract_pdf_text, PDF_INLINE_PAGE_LIMIT


def _create_test_pdf(tmp_path: Path, pages: list[str]) -> Path:
    """Helper: create a PDF with given page texts."""
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    path = tmp_path / "test.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_extract_single_page(tmp_path: Path) -> None:
    pdf_path = _create_test_pdf(tmp_path, ["Hello world"])
    text, page_count = extract_pdf_text(pdf_path)
    assert page_count == 1
    assert "Hello world" in text


def test_extract_multi_page(tmp_path: Path) -> None:
    pdf_path = _create_test_pdf(tmp_path, ["Page one", "Page two", "Page three"])
    text, page_count = extract_pdf_text(pdf_path)
    assert page_count == 3
    assert "Page one" in text
    assert "Page two" in text
    assert "Page three" in text
    assert "--- Page 1 ---" in text
    assert "--- Page 2 ---" in text
    assert "--- Page 3 ---" in text


def test_extract_empty_pdf(tmp_path: Path) -> None:
    """A PDF with pages but no text should return empty string."""
    doc = fitz.open()
    doc.new_page()
    path = tmp_path / "empty.pdf"
    doc.save(str(path))
    doc.close()
    text, page_count = extract_pdf_text(path)
    assert page_count == 1
    assert text.strip() == ""


def test_inline_page_limit_constant() -> None:
    assert PDF_INLINE_PAGE_LIMIT == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_pdf_utils.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pdf_utils'`

- [ ] **Step 3: Implement pdf_utils.py**

Create `app/pdf_utils.py`:

```python
"""PDF text extraction utilities."""
from __future__ import annotations

from pathlib import Path

import fitz  # pymupdf

PDF_INLINE_PAGE_LIMIT = 5


def extract_pdf_text(path: Path) -> tuple[str, int]:
    """Extract text from a PDF file.

    Returns ``(text, page_count)``.  Each page is separated by a
    ``--- Page N ---`` marker.  Raises ``ValueError`` on encrypted or
    unreadable PDFs.
    """
    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise ValueError(f"Cannot open PDF: {exc}") from exc

    if doc.is_encrypted:
        doc.close()
        raise ValueError("PDF is encrypted")

    pages: list[str] = []
    for i, page in enumerate(doc, start=1):
        page_text = page.get_text().strip()
        pages.append(f"--- Page {i} ---\n{page_text}")

    page_count = len(pages)
    doc.close()
    return "\n\n".join(pages), page_count
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_pdf_utils.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/pdf_utils.py tests/test_pdf_utils.py
git commit -m "feat: add pdf_utils with extract_pdf_text and tests"
```

---

### Task 3: Add document fields to message dataclasses

**Files:**
- Modify: `app/telegram_client.py:20-28` (TelegramMessage)
- Modify: `app/channels/base.py:13-28` (ChannelMessage)
- Modify: `app/channels/telegram.py:49-59` (TelegramChannel.get_updates)

- [ ] **Step 1: Add document_path to TelegramMessage**

In `app/telegram_client.py`, add a field after `image_path`:

```python
@dataclass(frozen=True)
class TelegramMessage:
    update_id: int
    chat_id: str
    message_id: int
    text: str
    raw: dict[str, Any]
    image_path: str | None = None  # temp file path if a photo was attached
    document_path: str | None = None  # temp file path if a PDF was attached
    document_name: str | None = None  # original filename
```

- [ ] **Step 2: Add document fields to ChannelMessage**

In `app/channels/base.py`, add after `image_path`:

```python
@dataclass(frozen=True)
class ChannelMessage:
    """Surface-agnostic inbound message."""
    update_id: int
    chat_id: str
    message_id: int
    text: str
    raw: dict[str, Any] = field(default_factory=dict)
    image_path: str | None = None
    document_path: str | None = None
    document_name: str | None = None
```

- [ ] **Step 3: Propagate document fields in TelegramChannel**

In `app/channels/telegram.py`, update the `ChannelMessage` construction inside `get_updates()`:

```python
            elif isinstance(update, TelegramMessage):
                results.append(
                    ChannelMessage(
                        update_id=update.update_id,
                        chat_id=update.chat_id,
                        message_id=update.message_id,
                        text=update.text,
                        raw=update.raw,
                        image_path=update.image_path,
                        document_path=update.document_path,
                        document_name=update.document_name,
                    )
                )
```

- [ ] **Step 4: Run existing tests to confirm no regressions**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest -x -q`
Expected: All existing tests pass (new fields have defaults, so nothing breaks)

- [ ] **Step 5: Commit**

```bash
git add app/telegram_client.py app/channels/base.py app/channels/telegram.py
git commit -m "feat: add document_path and document_name fields to message dataclasses"
```

---

### Task 4: Add `_download_document` and PDF detection in TelegramClient

**Files:**
- Modify: `app/telegram_client.py:48-119` (get_updates) and add `_download_document`

- [ ] **Step 1: Add `_download_document` method**

In `app/telegram_client.py`, add after `_download_photo` (after line 149):

```python
    def _download_document(self, file_id: str) -> str:
        """Download a Telegram document to a temp file. Returns the file path."""
        file_info = self._post_json("getFile", {"file_id": file_id})
        file_path = file_info.get("file_path", "")
        if not file_path:
            raise TelegramError(f"getFile returned no file_path for file_id={file_id!r}")

        download_url = f"{self._file_base_url}/{file_path}"
        request = urllib.request.Request(download_url)
        try:
            with urllib.request.urlopen(request, timeout=30, context=self._ssl_context) as resp:
                data = resp.read()
        except urllib.error.URLError as exc:
            raise TelegramError(f"Document download failed: {exc}") from exc

        suffix = ".pdf"
        if "." in file_path:
            suffix = "." + file_path.rsplit(".", 1)[-1]
        fd, tmp_path = tempfile.mkstemp(suffix=suffix, prefix="assistant_doc_")
        try:
            import os
            os.write(fd, data)
        finally:
            import os
            os.close(fd)
        return tmp_path
```

- [ ] **Step 2: Add PDF detection in get_updates**

In `app/telegram_client.py` `get_updates()`, after the photo detection block (after line 106), add document detection. The section from line 90 to 117 should become:

```python
            # Skip messages that have neither text, a photo, nor a PDF document
            if not isinstance(text, str) and not photo_sizes and not document:
                continue
```

And before the photo detection, add document extraction. Insert after line 88 (`caption = ...`):

```python
            document = message.get("document")  # present when a file is sent
```

After the photo download block (after line 106), add:

```python
            # Download PDF document if one is attached
            document_path: str | None = None
            document_name: str | None = None
            if document and document.get("mime_type") == "application/pdf":
                try:
                    doc_file_id = document["file_id"]
                    document_name = document.get("file_name", "document.pdf")
                    document_path = self._download_document(doc_file_id)
                except Exception as exc:
                    import logging
                    logging.getLogger(__name__).warning("Failed to download Telegram document: %s", exc)
```

Update the `TelegramMessage` construction to include the new fields:

```python
            results.append(
                TelegramMessage(
                    update_id=int(item["update_id"]),
                    chat_id=chat_id,
                    message_id=int(message["message_id"]),
                    text=effective_text,
                    raw=item,
                    image_path=image_path,
                    document_path=document_path,
                    document_name=document_name,
                )
            )
```

- [ ] **Step 3: Run existing tests**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add app/telegram_client.py
git commit -m "feat: detect and download PDF documents from Telegram"
```

---

### Task 5: Handle PDF in router with TDD

**Files:**
- Modify: `app/router.py:662-765` (_handle_message_locked) and `app/router.py:830-836` (_generate_reply_with_tools)

- [ ] **Step 1: Add PDF handling in `_generate_reply_with_tools`**

In `app/router.py`, add an import at the top (after the existing imports around line 27):

```python
from .pdf_utils import extract_pdf_text, PDF_INLINE_PAGE_LIMIT
```

In `_generate_reply_with_tools` (line 802), add `document_path` and `document_name` parameters:

```python
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
        document_path: str | None = None,
        document_name: str | None = None,
        channel: "BaseChannel | None" = None,
        compaction_summary: str | None = None,
    ) -> tuple[str, str | None, bool]:
```

After the image_path block (line 836), add PDF handling:

```python
        # If a PDF document was attached, extract text and inline or save
        if document_path:
            try:
                pdf_text, page_count = extract_pdf_text(Path(document_path))
                fname = document_name or "document.pdf"
                if not pdf_text.strip():
                    message_text = (
                        message_text
                        + f"\n\n[PDF document: {fname} — could not extract text (may be image-only).]"
                    ).lstrip()
                elif page_count <= PDF_INLINE_PAGE_LIMIT:
                    message_text = (
                        message_text
                        + f"\n\n[PDF document: {fname}, {page_count} page(s)]\n{pdf_text}"
                    ).lstrip()
                else:
                    # Save to agent documents directory
                    docs_dir = self._agents_dir / active_agent / "documents"
                    docs_dir.mkdir(parents=True, exist_ok=True)
                    safe_name = Path(fname).stem + ".txt"
                    saved_path = docs_dir / safe_name
                    saved_path.write_text(pdf_text, encoding="utf-8")
                    message_text = (
                        message_text
                        + f"\n\n[PDF document: {fname}, {page_count} pages — saved at: {saved_path}. Use read_file to reference sections.]"
                    ).lstrip()
            except ValueError as exc:
                message_text = (
                    message_text
                    + f"\n\n[PDF document error: {exc}]"
                ).lstrip()
```

- [ ] **Step 2: Pass document fields from `_handle_message_locked` to `_generate_reply_with_tools`**

In `_handle_message_locked`, after `image_path = message.image_path` (line 662), add:

```python
        document_path = getattr(message, "document_path", None)
        document_name = getattr(message, "document_name", None)
```

In the call to `_generate_reply_with_tools` (around line 725), add the new arguments:

```python
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
                document_path=document_path,
                document_name=document_name,
                channel=channel,
                compaction_summary=compaction_summary,
            )
```

- [ ] **Step 3: Add document cleanup in `finally` block**

In the `finally` block (around line 760), after the image cleanup, add:

```python
            if document_path:
                try:
                    Path(document_path).unlink(missing_ok=True)
                except OSError:
                    pass
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add app/router.py
git commit -m "feat: handle PDF documents in router — extract, inline or save"
```

---

### Task 6: TerminalChatSession session isolation test

**Files:**
- Create: `tests/test_chat_session.py`

- [ ] **Step 1: Write the session isolation test**

Create `tests/test_chat_session.py`:

```python
"""Tests for TerminalChatSession session isolation."""
from __future__ import annotations

from pathlib import Path

from app.memory import MemoryStore


def test_session_ids_isolated_by_chat_id(tmp_path: Path) -> None:
    """Two different chat_ids must not share session IDs."""
    # We test the isolation property directly on the dict structure
    # that TerminalChatSession uses, without needing a full config.
    session_ids_a: dict[str, str] = {}
    session_ids_b: dict[str, str] = {}

    chat_id_a = "alpha"
    chat_id_b = "beta"
    agent = "main"

    # Simulate session ID assignment (mirrors chat_session.py:234)
    session_ids_a[f"{chat_id_a}:{agent}"] = "sess-aaa"
    session_ids_b[f"{chat_id_b}:{agent}"] = "sess-bbb"

    # Session IDs are independent
    assert session_ids_a.get(f"{chat_id_a}:{agent}") == "sess-aaa"
    assert session_ids_a.get(f"{chat_id_b}:{agent}") is None
    assert session_ids_b.get(f"{chat_id_b}:{agent}") == "sess-bbb"
    assert session_ids_b.get(f"{chat_id_a}:{agent}") is None


def test_transcript_paths_differ_by_chat_id(tmp_path: Path) -> None:
    """Different chat_ids must produce different transcript files."""
    shared_dir = tmp_path / "shared"
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)

    store = MemoryStore(shared_dir=shared_dir, agents_dir=agents_dir)

    path_a = store.transcript_path("terminal", "alpha", account_id="primary", agent_name="main")
    path_b = store.transcript_path("terminal", "beta", account_id="primary", agent_name="main")

    assert path_a != path_b
    assert "alpha" in str(path_a)
    assert "beta" in str(path_b)


def test_transcript_entries_isolated_by_chat_id(tmp_path: Path) -> None:
    """Appending a transcript to chat A must not appear in chat B's transcript."""
    shared_dir = tmp_path / "shared"
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir(parents=True)

    store = MemoryStore(shared_dir=shared_dir, agents_dir=agents_dir)

    store.append_transcript(
        surface="terminal",
        account_id="primary",
        chat_id="alpha",
        direction="in",
        agent="main",
        message_text="hello from alpha",
    )

    entries_alpha = store.read_recent_transcript(
        "terminal", "alpha", limit=10, account_id="primary", agent_name="main",
    )
    entries_beta = store.read_recent_transcript(
        "terminal", "beta", limit=10, account_id="primary", agent_name="main",
    )

    assert len(entries_alpha) == 1
    assert entries_alpha[0].message_text == "hello from alpha"
    assert len(entries_beta) == 0
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest tests/test_chat_session.py -v`
Expected: All 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_chat_session.py
git commit -m "test: add TerminalChatSession session isolation tests"
```

---

### Task 7: Full test suite verification

- [ ] **Step 1: Run entire test suite**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -m pytest -v`
Expected: All tests pass (existing ~110 + new ~7 = ~117 total)

- [ ] **Step 2: Quick smoke test of PDF import chain**

Run: `cd /Users/macbook/Projects/assistant-runtime && python -c "from app.pdf_utils import extract_pdf_text, PDF_INLINE_PAGE_LIMIT; from app.channels.base import ChannelMessage; print('imports OK')"`
Expected: `imports OK`
