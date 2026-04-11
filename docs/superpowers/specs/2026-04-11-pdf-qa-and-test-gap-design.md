# PDF Document Q&A + TerminalChatSession Test Gap

**Date:** 2026-04-11  
**Status:** Approved  
**Scope:** (1) Accept PDF documents via Telegram, extract text, enable conversational Q&A. (2) Add dedicated test for TerminalChatSession session isolation.

---

## Feature 1: PDF Document Q&A

### Problem

Users cannot send PDFs to the assistant via Telegram. Photos are supported (download → temp file → Claude reads via `read_file`), but documents are not handled.

### Goal

Drop a PDF into Telegram chat, ask questions about it. Supports both one-shot extraction ("summarize this") and multi-turn Q&A ("what does section 3 say about X?").

### Design

#### PDF text extraction utility

New file: `app/pdf_utils.py`

```python
def extract_pdf_text(path: Path) -> tuple[str, int]:
    """Extract text from PDF. Returns (text, page_count)."""
```

- Uses `pymupdf` (imported as `fitz`)
- Extracts text page-by-page, joins with page markers: `--- Page N ---`
- Returns `(full_text, page_count)`
- Raises `ValueError` on unreadable/encrypted PDFs

#### Telegram document download

In `telegram_client.py`, add `_download_document(file_id: str, file_name: str) -> str`:

- Mirrors existing `_download_photo` pattern
- Calls Telegram `getFile` API → download bytes → save to `tempfile.mkstemp(suffix=".pdf")`
- Returns temp file path

#### Message detection

In `telegram_client.py` `get_updates()`:

- Check for `document` field in Telegram message payload
- Filter by `mime_type == "application/pdf"`
- Extract `file_id` and `file_name` from document object
- Download via `_download_document`
- Propagate path and filename via `TelegramMessage` (add `document_path: str | None` field)

#### ChannelMessage propagation

In `app/channels/telegram.py`:

- Map `TelegramMessage.document_path` → `ChannelMessage.document_path`
- Add `document_path: str | None = None` and `document_name: str | None = None` to `ChannelMessage`

#### Router handling

In `router.py` `_handle_message_locked()`, after existing image handling:

- If `message.document_path` is set:
  - Call `extract_pdf_text(document_path)`
  - **≤5 pages**: inline text in user message: `[PDF document: {filename}, {page_count} pages]\n{text}`
  - **>5 pages**: save extracted text to `{agent_dir}/documents/{filename}.txt`, message becomes: `[PDF document: {filename}, {page_count} pages — saved at: {path}. Use read_file to reference sections.]`
  - Clean up temp PDF in `finally` block (same pattern as image cleanup)

#### Constants

```python
PDF_INLINE_PAGE_LIMIT = 5  # pages; beyond this, save to file
```

Defined in `pdf_utils.py`. No config entry needed.

#### Documents directory

For large PDFs, text saved to `{agent_dir}/documents/`. Directory created on first use via `mkdir(parents=True, exist_ok=True)`. Files persist across turns for multi-turn Q&A. Not auto-cleaned — user or agent can delete when done.

### What Is Not Changing

- `ContextBuilder` — unchanged
- `ToolRegistry` — no new tools needed (Claude already has `read_file`)
- `AppConfig` — no new config fields
- Photo handling — unchanged, parallel path
- `ClaudeCodeRunner` — unchanged

### Error Handling

- Encrypted/unreadable PDF → reply to user: "Could not extract text from this PDF (may be encrypted or image-only)."
- Empty extraction (0 chars) → same error message
- Download failure → existing Telegram error handling applies

### Dependencies

Add `pymupdf` to `pyproject.toml` dependencies.

### Testing

| Test | File |
|------|------|
| `extract_pdf_text` returns correct text and page count | `tests/test_pdf_utils.py` |
| `extract_pdf_text` raises on encrypted PDF | `tests/test_pdf_utils.py` |
| `extract_pdf_text` returns empty-string error on image-only PDF | `tests/test_pdf_utils.py` |
| Inline threshold: ≤5 pages inlined, >5 pages saved to file | `tests/test_pdf_utils.py` |
| Document download mirrors photo download pattern | `tests/test_telegram_client.py` (or mock) |

### Files Touched

| File | Change |
|------|--------|
| `app/pdf_utils.py` | New — `extract_pdf_text()`, `PDF_INLINE_PAGE_LIMIT` |
| `app/telegram_client.py` | Add `_download_document()`, detect PDF in `get_updates()` |
| `app/channels/telegram.py` | Add `document_path`/`document_name` to message dataclass |
| `app/router.py` | Handle `document_path` in `_handle_message_locked()` |
| `pyproject.toml` | Add `pymupdf` dependency |
| `tests/test_pdf_utils.py` | New — extraction tests |

---

## Feature 2: TerminalChatSession Session Isolation Test

### Problem

`TerminalChatSession` supports per-`chat_id` session isolation (separate `_session_ids` entries, separate transcript files), but no dedicated test verifies this.

### Goal

Add a focused test proving two `TerminalChatSession` instances with different `chat_id` values maintain independent state.

### Design

New test in `tests/test_chat_session.py`:

1. Create two `TerminalChatSession` instances with `chat_id="alpha"` and `chat_id="beta"`, same `agents_dir`
2. Verify `_session_ids` dicts are independent (set a session ID on one, confirm absent on other)
3. Verify transcript paths differ (via `_memory.transcript_path()`)
4. Verify appending a transcript entry to one does not appear in the other's transcript

### Files Touched

| File | Change |
|------|--------|
| `tests/test_chat_session.py` | New — session isolation tests |
