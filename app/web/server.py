"""Web dashboard server for assistant-runtime.

Serves a Bootstrap 5 dashboard at http://localhost:18790.
Uses only stdlib — no external web framework required.

Endpoints
---------
GET  /                               HTML dashboard
GET  /api/status                     Runtime status JSON
GET  /api/agents                     Agent list JSON
GET  /api/tasks                      Scheduled tasks JSON
GET  /api/transcripts                Recent transcripts JSON
GET  /api/skills                     Installed skills JSON
POST /api/chat                       Start a chat job → {job_id}
GET  /api/chat/poll/<job_id>         Poll for chat job result
GET  /api/gap-check/state            Last-checked upstream repo state
POST /api/gap-check                  Start a gap-check job → {job_id}
GET  /api/gap-check/poll/<job_id>    Poll for gap-check result
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..app_paths import get_config_file, get_runtime_pid_file, get_state_dir
from ..config_manager import load_raw_config

LOGGER = logging.getLogger(__name__)

# Path to the gap-check script (project_root/scripts/check_upstream.py)
_UPSTREAM_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "check_upstream.py"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18790

# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>assistant-runtime</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css">
  <style>
    body { background: #0d1117; color: #e6edf3; }
    .card { background: #161b22; border: 1px solid #30363d; }
    .card-header { background: #21262d; border-bottom: 1px solid #30363d; }
    .badge-online { background: #238636; }
    .badge-offline { background: #6e7681; }
    pre { color: #c9d1d9; font-size: 0.8rem; white-space: pre-wrap; word-break: break-word; }
    .table { color: #e6edf3; }
    .table thead th { border-color: #30363d; color: #c9d1d9; font-size: 0.8rem; text-transform: uppercase; }
    .table tbody td { border-color: #21262d; color: #e6edf3; }
    .nav-link { color: #c9d1d9; }
    .nav-link.active { color: #58a6ff !important; }
    .nav-link:hover { color: #ffffff; }
    /* Bootstrap muted/secondary classes default too dark on this background */
    .text-muted, .text-secondary { color: #c9d1d9 !important; }
    small, .small { color: #c9d1d9; }
    label, .form-label { color: #e6edf3; }
    .form-control, .form-select { color: #e6edf3; background-color: #161b22; border-color: #30363d; }
    .form-control::placeholder { color: #8b949e; }
    .card-header { color: #e6edf3; }
    a { color: #58a6ff; }
    a:hover { color: #79c0ff; }
    #status-dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
    /* Chat */
    .chat-wrap { height: 420px; overflow-y: auto; background: #0d1117; border: 1px solid #30363d; border-radius: .375rem; padding: 1rem; }
    .bubble { max-width: 75%; margin-bottom: .75rem; }
    .bubble-user { margin-left: auto; text-align: right; }
    .bubble-user .bubble-inner { background: #1f6feb; color: #fff; border-radius: 1rem 1rem 0 1rem; }
    .bubble-assistant .bubble-inner { background: #21262d; color: #e6edf3; border-radius: 1rem 1rem 1rem 0; }
    .bubble-inner { padding: .5rem .85rem; display: inline-block; font-size: .9rem; white-space: pre-wrap; word-break: break-word; }
    .bubble-name { font-size: .75rem; color: #c9d1d9; margin-bottom: .15rem; }
    .thinking-dots { letter-spacing: 3px; }
    .chat-input-ctrl { background: #161b22 !important; color: #e6edf3 !important; border-color: #30363d !important; }
    .chat-input-ctrl::placeholder { color: #6e7681; }
  </style>
</head>
<body>
<nav class="navbar navbar-dark px-3 py-2" style="background:#161b22;border-bottom:1px solid #30363d">
  <span class="navbar-brand fw-bold">&#x1F916; assistant-runtime</span>
  <span class="ms-auto">
    <span id="status-dot" class="bg-secondary me-1"></span>
    <span id="status-label" class="text-muted small">checking…</span>
  </span>
</nav>

<div class="container-fluid py-3">
  <ul class="nav nav-tabs mb-3" id="tabs">
    <li class="nav-item"><a class="nav-link active" data-tab="overview" href="#">Overview</a></li>
    <li class="nav-item"><a class="nav-link" data-tab="agents" href="#">Agents</a></li>
    <li class="nav-item"><a class="nav-link" data-tab="tasks" href="#">Tasks</a></li>
    <li class="nav-item"><a class="nav-link" data-tab="transcripts" href="#">Transcripts</a></li>
    <li class="nav-item"><a class="nav-link" data-tab="skills" href="#">Skills</a></li>
    <li class="nav-item"><a class="nav-link" data-tab="chat" href="#">&#x1F4AC; Chat</a></li>
    <li class="nav-item"><a class="nav-link" data-tab="gapcheck" href="#">&#x1F50D; Gap Check</a></li>
  </ul>

  <!-- Overview -->
  <div id="tab-overview">
    <div class="row g-3">
      <div class="col-md-6">
        <div class="card">
          <div class="card-header fw-bold">Runtime Status</div>
          <div class="card-body"><pre id="status-json">loading…</pre></div>
        </div>
      </div>
      <div class="col-md-6">
        <div class="card">
          <div class="card-header fw-bold">Quick Stats</div>
          <div class="card-body" id="quick-stats">loading…</div>
        </div>
      </div>
    </div>
  </div>

  <!-- Agents -->
  <div id="tab-agents" style="display:none">
    <div id="agents-list" class="row g-3">loading…</div>
  </div>

  <!-- Tasks -->
  <div id="tab-tasks" style="display:none">
    <div class="card">
      <div class="card-header fw-bold d-flex align-items-center">
        Scheduled Tasks
        <button class="btn btn-sm btn-outline-secondary ms-auto" onclick="loadTasks()">Refresh</button>
      </div>
      <div class="card-body p-0">
        <table class="table table-sm mb-0">
          <thead><tr>
            <th>ID</th><th>Type</th><th>Agent / Chat</th><th>Fire At</th><th>Status</th><th>Payload</th>
          </tr></thead>
          <tbody id="tasks-body"><tr><td colspan="6" class="text-center text-muted py-3">loading…</td></tr></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Transcripts -->
  <div id="tab-transcripts" style="display:none">
    <div class="row mb-2">
      <div class="col-md-4">
        <select class="form-select form-select-sm" id="transcript-select" style="background:#161b22;color:#e6edf3;border-color:#30363d">
          <option value="">Select a transcript…</option>
        </select>
      </div>
      <div class="col-auto">
        <button class="btn btn-sm btn-outline-secondary" onclick="loadTranscriptMessages()">Load</button>
      </div>
    </div>
    <div id="transcript-messages"></div>
  </div>

  <!-- Skills -->
  <div id="tab-skills" style="display:none">
    <div id="skills-list" class="row g-3">loading…</div>
  </div>

  <!-- Gap Check -->
  <div id="tab-gapcheck" style="display:none">
    <div class="card">
      <div class="card-header fw-bold d-flex align-items-center">
        &#x1F50D; Gap Check
        <span class="ms-2 small text-muted fw-normal">Fetch upstream GitHub changes and compare against this project</span>
      </div>
      <div class="card-body">
        <div class="d-flex gap-2 mb-2">
          <input id="gap-url" class="form-control form-control-sm"
                 style="background:#0d1117;color:#e6edf3;border-color:#30363d;font-family:monospace"
                 placeholder="https://github.com/owner/repo">
          <button id="gap-run-btn" class="btn btn-sm btn-primary px-3" onclick="runGapCheck()">Run</button>
        </div>
        <div id="gap-status" class="small text-muted mb-2">&nbsp;</div>
        <pre id="gap-output" style="min-height:200px;max-height:520px;overflow-y:auto;background:#0d1117;border:1px solid #30363d;border-radius:.375rem;padding:1rem;color:#c9d1d9">Run Gap Check to see results here.</pre>
        <div class="small text-muted mt-2">&#x2139;&#xFE0F; Once done, copy the output and paste it into Chat for gap analysis.</div>
      </div>
    </div>
  </div>

  <!-- Chat -->
  <div id="tab-chat" style="display:none">
    <div class="row mb-2 align-items-center g-2">
      <div class="col-auto">
        <label class="col-form-label col-form-label-sm text-muted">Agent</label>
      </div>
      <div class="col-md-2">
        <select id="chat-agent" class="form-select form-select-sm chat-input-ctrl"></select>
      </div>
      <div class="col-auto">
        <label class="col-form-label col-form-label-sm text-muted">Session</label>
      </div>
      <div class="col-md-2">
        <input id="chat-session-id" class="form-control form-control-sm chat-input-ctrl" value="web"
               title="Change this to start a separate conversation thread">
      </div>
      <div class="col-auto">
        <button class="btn btn-sm btn-outline-danger" onclick="clearChat()" title="Clear message display (does not erase transcript)">Clear</button>
      </div>
    </div>
    <div id="chat-wrap" class="chat-wrap mb-2"></div>
    <div class="d-flex gap-2">
      <textarea id="chat-input" rows="2" placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
                class="form-control form-control-sm chat-input-ctrl" style="resize:none"></textarea>
      <button id="chat-send-btn" class="btn btn-primary btn-sm px-3" onclick="sendChatMessage()">Send</button>
    </div>
    <div id="chat-status" class="small text-muted mt-1">&nbsp;</div>
  </div>
</div>

<script>
const API = '';

const authHeaders = typeof DASHBOARD_TOKEN !== 'undefined' && DASHBOARD_TOKEN
  ? {'Authorization': 'Bearer ' + DASHBOARD_TOKEN} : {};

async function apiFetch(path) {
  const r = await fetch(API + path, {headers: authHeaders});
  return r.json();
}

// --- Tab switching ---
document.querySelectorAll('[data-tab]').forEach(el => {
  el.addEventListener('click', e => {
    e.preventDefault();
    document.querySelectorAll('[data-tab]').forEach(x => x.classList.remove('active'));
    el.classList.add('active');
    document.querySelectorAll('[id^="tab-"]').forEach(x => x.style.display = 'none');
    document.getElementById('tab-' + el.dataset.tab).style.display = '';
    if (el.dataset.tab === 'tasks') loadTasks();
    if (el.dataset.tab === 'agents') loadAgents();
    if (el.dataset.tab === 'transcripts') loadTranscriptList();
    if (el.dataset.tab === 'skills') loadSkills();
    if (el.dataset.tab === 'chat') loadChat();
    if (el.dataset.tab === 'gapcheck') loadGapCheck();
  });
});

// --- Overview ---
async function loadOverview() {
  const status = await apiFetch('/api/status');
  document.getElementById('status-json').textContent = JSON.stringify(status, null, 2);
  const dot = document.getElementById('status-dot');
  const lbl = document.getElementById('status-label');
  if (status.running) {
    dot.style.background = '#238636'; lbl.textContent = 'running (PID ' + status.pid + ')';
  } else {
    dot.style.background = '#6e7681'; lbl.textContent = 'stopped';
  }

  const [agents, tasks, skills] = await Promise.all([
    apiFetch('/api/agents'), apiFetch('/api/tasks'), apiFetch('/api/skills')
  ]);
  const activeTasks = (tasks.tasks || []).filter(t => t.status === 'pending').length;
  document.getElementById('quick-stats').innerHTML = `
    <div class="d-flex flex-column gap-2">
      <div>&#x1F464; <strong>${(agents.agents || []).length}</strong> agents configured</div>
      <div>&#x23F0; <strong>${activeTasks}</strong> pending tasks</div>
      <div>&#x1F527; <strong>${(skills.skills || []).length}</strong> skills loaded</div>
    </div>`;
}

// --- Agents ---
async function loadAgents() {
  const data = await apiFetch('/api/agents');
  const el = document.getElementById('agents-list');
  if (!data.agents || !data.agents.length) { el.innerHTML = '<div class="text-muted">No agents found.</div>'; return; }
  el.innerHTML = data.agents.map(a => `
    <div class="col-md-6">
      <div class="card h-100">
        <div class="card-header fw-bold">${esc(a.name)}</div>
        <div class="card-body">
          <div class="text-muted small mb-2">${esc(a.description || '')}</div>
          <pre>${esc((a.agent_md || '').slice(0, 600))}${a.agent_md && a.agent_md.length > 600 ? '\\n…' : ''}</pre>
        </div>
      </div>
    </div>`).join('');
}

// --- Tasks ---
async function loadTasks() {
  const data = await apiFetch('/api/tasks');
  const tbody = document.getElementById('tasks-body');
  if (!data.tasks || !data.tasks.length) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted py-3">No tasks found.</td></tr>'; return;
  }
  tbody.innerHTML = data.tasks.map(t => `
    <tr>
      <td><code class="small">${esc(t.id.slice(0,8))}</code></td>
      <td>${esc(t.task_type)}</td>
      <td>${esc(t.account_id)}/${esc(t.chat_id)}</td>
      <td class="small">${esc(t.fire_at)}</td>
      <td><span class="badge ${t.status === 'pending' ? 'bg-warning text-dark' : t.status === 'done' ? 'bg-success' : 'bg-secondary'}">${esc(t.status)}</span></td>
      <td><pre class="mb-0" style="font-size:0.75rem">${esc(JSON.stringify(t.payload))}</pre></td>
    </tr>`).join('');
}

// --- Transcripts ---
async function loadTranscriptList() {
  const data = await apiFetch('/api/transcripts');
  const sel = document.getElementById('transcript-select');
  sel.innerHTML = '<option value="">Select a transcript…</option>';
  (data.files || []).forEach(f => {
    const opt = document.createElement('option');
    opt.value = f; opt.textContent = f;
    sel.appendChild(opt);
  });
}

async function loadTranscriptMessages() {
  const file = document.getElementById('transcript-select').value;
  if (!file) return;
  const data = await apiFetch('/api/transcripts?file=' + encodeURIComponent(file));
  const el = document.getElementById('transcript-messages');
  if (!data.entries || !data.entries.length) { el.innerHTML = '<div class="text-muted">No messages.</div>'; return; }
  el.innerHTML = data.entries.map(e => `
    <div class="mb-2">
      <div class="small text-muted">${esc(e.timestamp)} &mdash; <strong>${e.direction === 'in' ? '&#x1F464; User' : '&#x1F916; ' + esc(e.agent)}</strong></div>
      <div class="card"><div class="card-body py-2 px-3" style="font-size:0.9rem">${esc(e.message_text)}</div></div>
    </div>`).join('');
}

// --- Skills ---
async function loadSkills() {
  const data = await apiFetch('/api/skills');
  const el = document.getElementById('skills-list');
  if (!data.skills || !data.skills.length) { el.innerHTML = '<div class="text-muted">No skills loaded.</div>'; return; }
  el.innerHTML = data.skills.map(s => `
    <div class="col-md-4">
      <div class="card h-100">
        <div class="card-header d-flex align-items-center">
          <span class="fw-bold">${esc(s.name)}</span>
          <span class="badge ms-2 ${s.available ? 'bg-success' : 'bg-secondary'}">${s.available ? 'available' : 'unavailable'}</span>
          <span class="badge bg-dark ms-1">v${esc(s.version)}</span>
        </div>
        <div class="card-body">
          <div class="small text-muted mb-2">${esc(s.description)}</div>
          ${s.tools.length ? '<div class="small"><strong>Tools:</strong> ' + s.tools.map(t => '<code>' + esc(t) + '</code>').join(' ') + '</div>' : ''}
          ${s.commands.length ? '<div class="small mt-1"><strong>Commands:</strong> ' + s.commands.map(c => '<code>' + esc(c) + '</code>').join(' ') + '</div>' : ''}
        </div>
      </div>
    </div>`).join('');
}

// --- Chat ---
let _chatPolling = null;

async function loadChat() {
  const data = await apiFetch('/api/agents');
  const sel = document.getElementById('chat-agent');
  const prev = sel.value;
  sel.innerHTML = '';
  (data.agents || []).forEach(a => {
    const opt = document.createElement('option');
    opt.value = a.name; opt.textContent = a.name;
    if (a.name === prev) opt.selected = true;
    sel.appendChild(opt);
  });
}

function chatAppendMsg(role, content, {id, raw} = {}) {
  const wrap = document.getElementById('chat-wrap');
  const div = document.createElement('div');
  div.className = 'bubble bubble-' + role;
  if (id) div.id = id;
  const agentName = document.getElementById('chat-agent').value || 'assistant';
  const name = role === 'user' ? '&#x1F464; You' : '&#x1F916; ' + esc(agentName);
  const body = raw ? content : esc(content);
  div.innerHTML = '<div class="bubble-name">' + name + '</div><div class="bubble-inner">' + body + '</div>';
  wrap.appendChild(div);
  wrap.scrollTop = wrap.scrollHeight;
}

function clearChat() {
  document.getElementById('chat-wrap').innerHTML = '';
}

async function sendChatMessage() {
  const inputEl = document.getElementById('chat-input');
  const msg = inputEl.value.trim();
  if (!msg || _chatPolling) return;

  const agentName = document.getElementById('chat-agent').value;
  const chatId = (document.getElementById('chat-session-id').value || 'web').trim();
  const sendBtn = document.getElementById('chat-send-btn');
  const statusEl = document.getElementById('chat-status');

  inputEl.value = '';
  chatAppendMsg('user', msg);

  const thinkingId = 'thinking-' + Date.now();
  chatAppendMsg('assistant', '<span class="thinking-dots">&#x25CF; &#x25CF; &#x25CF;</span>', {id: thinkingId, raw: true});

  sendBtn.disabled = true;
  statusEl.textContent = 'Waiting for reply\u2026';

  let jobId = null;
  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: {...authHeaders, 'Content-Type': 'application/json'},
      body: JSON.stringify({agent_name: agentName, chat_id: chatId, message: msg})
    });
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    jobId = data.job_id;
  } catch(e) {
    document.getElementById(thinkingId)?.remove();
    sendBtn.disabled = false;
    statusEl.textContent = 'Error: ' + e.message;
    return;
  }

  let elapsed = 0;
  _chatPolling = setInterval(async () => {
    elapsed += 1;
    statusEl.textContent = 'Waiting for reply\u2026 (' + elapsed + 's)';
    try {
      const poll = await apiFetch('/api/chat/poll/' + jobId);
      if (poll.status === 'done' || poll.status === 'error') {
        clearInterval(_chatPolling); _chatPolling = null;
        sendBtn.disabled = false;
        statusEl.textContent = '\u00a0';
        const bubble = document.getElementById(thinkingId);
        if (bubble) {
          const inner = bubble.querySelector('.bubble-inner');
          if (inner) {
            inner.textContent = poll.reply || '(no response)';
            if (poll.status === 'error') inner.style.color = '#f85149';
          }
        }
        document.getElementById('chat-wrap').scrollTop = document.getElementById('chat-wrap').scrollHeight;
      }
    } catch(e) {
      clearInterval(_chatPolling); _chatPolling = null;
      sendBtn.disabled = false;
      statusEl.textContent = 'Poll error: ' + e.message;
    }
  }, 1000);
}

document.addEventListener('DOMContentLoaded', () => {
  const inputEl = document.getElementById('chat-input');
  if (inputEl) {
    inputEl.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChatMessage(); }
    });
  }
});

// --- Gap Check ---
let _gapPolling = null;

async function loadGapCheck() {
  try {
    const data = await apiFetch('/api/gap-check/state');
    const repos = data.repos || {};
    const keys = Object.keys(repos);
    if (keys.length > 0) {
      const last = keys[keys.length - 1];
      document.getElementById('gap-url').value = 'https://github.com/' + last;
      const lastChecked = (repos[last].last_checked || '').slice(0, 10);
      document.getElementById('gap-status').textContent =
        'Last checked: ' + last + (lastChecked ? ' on ' + lastChecked : '');
    }
  } catch(e) {}
}

async function runGapCheck() {
  const url = document.getElementById('gap-url').value.trim();
  if (!url || _gapPolling) return;

  const btn = document.getElementById('gap-run-btn');
  const statusEl = document.getElementById('gap-status');
  const outputEl = document.getElementById('gap-output');

  btn.disabled = true;
  outputEl.textContent = 'Fetching from GitHub\u2026';
  outputEl.style.color = '#c9d1d9';
  statusEl.textContent = 'Running\u2026';

  let jobId = null;
  try {
    const resp = await fetch('/api/gap-check', {
      method: 'POST',
      headers: {...authHeaders, 'Content-Type': 'application/json'},
      body: JSON.stringify({url})
    });
    const data = await resp.json();
    if (data.error) throw new Error(data.error);
    jobId = data.job_id;
  } catch(e) {
    btn.disabled = false;
    statusEl.textContent = 'Error: ' + e.message;
    return;
  }

  let elapsed = 0;
  _gapPolling = setInterval(async () => {
    elapsed += 1;
    statusEl.textContent = 'Fetching from GitHub\u2026 (' + elapsed + 's)';
    try {
      const poll = await apiFetch('/api/gap-check/poll/' + jobId);
      if (poll.status === 'done' || poll.status === 'error') {
        clearInterval(_gapPolling); _gapPolling = null;
        btn.disabled = false;
        outputEl.textContent = poll.output || '(no output)';
        if (poll.status === 'error') {
          outputEl.style.color = '#f85149';
          statusEl.textContent = '\u26a0\ufe0f Error — see output above';
        } else {
          outputEl.style.color = '#e6edf3';
          statusEl.textContent = '\u2705 Done — copy the output and paste it into Chat for gap analysis';
          loadGapCheck();
        }
      }
    } catch(e) {
      clearInterval(_gapPolling); _gapPolling = null;
      btn.disabled = false;
      statusEl.textContent = 'Poll error: ' + e.message;
    }
  }, 1000);
}

function esc(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

loadOverview();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _read_pid(pid_path: Path) -> int | None:
    if not pid_path.exists():
        return None
    try:
        raw = pid_path.read_text(encoding="utf-8").strip()
        return int(raw) if raw else None
    except (OSError, ValueError):
        return None


def _process_running(pid: int) -> bool:
    try:
        import os
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _load_config() -> dict[str, Any]:
    try:
        return load_raw_config(get_config_file())
    except Exception:
        return {}


def _api_status() -> dict[str, Any]:
    pid_path = get_runtime_pid_file()
    pid = _read_pid(pid_path)
    running = pid is not None and _process_running(pid)
    cfg = _load_config()
    return {
        "running": running,
        "pid": pid,
        "model_provider": cfg.get("model_provider", "claude-code"),
        "claude_model": cfg.get("claude_model"),
        "claude_effort": cfg.get("claude_effort"),
        "default_agent": cfg.get("default_agent"),
    }


def _api_agents(agents_dir: Path) -> dict[str, Any]:
    agents: list[dict[str, Any]] = []
    if agents_dir.exists():
        from ..agent_provisioning import is_real_agent_dir
        for agent_dir in sorted(agents_dir.iterdir()):
            if not is_real_agent_dir(agent_dir):
                continue
            agent_md_path = agent_dir / "AGENT.md"
            agent_md = agent_md_path.read_text(encoding="utf-8").strip() if agent_md_path.exists() else ""
            description = next((ln.strip().lstrip("#").strip() for ln in agent_md.splitlines() if ln.strip()), "")
            agents.append({
                "name": agent_dir.name,
                "description": description,
                "agent_md": agent_md,
                "has_memory": (agent_dir / "MEMORY.md").exists(),
                "has_user": (agent_dir / "USER.md").exists(),
            })
    return {"agents": agents}


def _api_tasks(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"tasks": []}
    try:
        conn = sqlite3.connect(str(db_path), timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT id, task_type, chat_id, account_id, surface, fire_at, payload, status, created_at "
                "FROM tasks ORDER BY fire_at ASC LIMIT 200"
            ).fetchall()
            tasks = []
            for row in rows:
                try:
                    payload = json.loads(row["payload"])
                except (ValueError, TypeError):
                    payload = {}
                tasks.append({
                    "id": row["id"],
                    "task_type": row["task_type"],
                    "chat_id": row["chat_id"],
                    "account_id": row["account_id"],
                    "surface": row["surface"],
                    "fire_at": row["fire_at"],
                    "payload": payload,
                    "status": row["status"],
                    "created_at": row["created_at"],
                })
            return {"tasks": tasks}
        finally:
            conn.close()
    except Exception as exc:
        LOGGER.warning("Failed to read tasks DB: %s", exc)
        return {"tasks": [], "error": str(exc)}


def _api_transcripts(shared_dir: Path, file: str | None = None) -> dict[str, Any]:
    transcript_dir = shared_dir / "transcripts"
    if file:
        path = transcript_dir / file
        if not path.exists() or path.suffix != ".jsonl":
            return {"entries": [], "error": "Not found"}
        entries: list[dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except ValueError:
                        pass
            return {"entries": entries[-100:]}
        except OSError:
            return {"entries": []}
    else:
        files = []
        if transcript_dir.exists():
            files = sorted(p.name for p in transcript_dir.glob("*.jsonl"))
        return {"files": files}


def _api_skills() -> dict[str, Any]:
    try:
        from ..plugins.loader import build_plugin_registry
        registry = build_plugin_registry()
        skills = []
        for skill in registry.all_skills:
            tool_handlers = skill.tools()
            cmd_map = skill.commands()
            skills.append({
                "name": skill.name,
                "version": skill.version,
                "description": skill.description,
                "available": skill.is_available(),
                "tools": [spec.name for spec, _ in tool_handlers],
                "commands": list(cmd_map.keys()),
            })
        return {"skills": skills}
    except Exception as exc:
        LOGGER.warning("Failed to load skills: %s", exc)
        return {"skills": [], "error": str(exc)}


def _api_chat_post(
    body: dict[str, Any],
    chat_sessions: dict[str, Any],
    chat_jobs: dict[str, Any],
    chat_lock: threading.Lock,
    config_path: Path,
) -> dict[str, Any]:
    """Start a chat job in a background thread. Returns {job_id}."""
    agent_name = str(body.get("agent_name", "")).strip() or "main"
    chat_id = str(body.get("chat_id", "")).strip() or "web"
    message = str(body.get("message", "")).strip()

    if not message:
        return {"error": "message is required"}

    with chat_lock:
        existing = chat_sessions.get(chat_id)
        # Create a new session if first time or agent has changed
        if existing is None or getattr(existing, "_web_agent_name", None) != agent_name:
            try:
                from ..chat_session import TerminalChatSession
                session = TerminalChatSession(
                    agent_name=agent_name,
                    chat_id=chat_id,
                    config_path=config_path,
                )
                session._web_agent_name = agent_name  # type: ignore[attr-defined]
                chat_sessions[chat_id] = session
            except Exception as exc:
                LOGGER.exception("Failed to create chat session for agent=%s chat_id=%s", agent_name, chat_id)
                return {"error": f"Failed to initialise session: {exc}"}
        else:
            session = existing

        job_id = uuid.uuid4().hex
        chat_jobs[job_id] = {"status": "pending", "created_at": time.monotonic()}

    def _run_job() -> None:
        try:
            reply = session._run_tool_loop(message)
            with chat_lock:
                chat_jobs[job_id] = {"status": "done", "reply": reply, "created_at": time.monotonic()}
        except Exception as exc:
            LOGGER.exception("Chat job failed job_id=%s", job_id)
            with chat_lock:
                chat_jobs[job_id] = {"status": "error", "reply": str(exc), "created_at": time.monotonic()}

    t = threading.Thread(target=_run_job, daemon=True, name=f"web-chat-{job_id[:8]}")
    t.start()
    return {"job_id": job_id}


def _api_chat_poll(
    job_id: str,
    chat_jobs: dict[str, Any],
    chat_lock: threading.Lock,
) -> dict[str, Any]:
    """Return current job status. Removes completed jobs after returning them."""
    with chat_lock:
        job = chat_jobs.get(job_id)
        if job is None:
            return {"status": "not_found"}

        # Lazy eviction: remove completed jobs older than 5 minutes
        now = time.monotonic()
        stale = [
            jid for jid, j in chat_jobs.items()
            if j["status"] != "pending" and now - j.get("created_at", now) > 300
        ]
        for jid in stale:
            del chat_jobs[jid]

        if job["status"] == "pending":
            return {"status": "pending"}

        # Remove the completed job so repeated polls return not_found
        chat_jobs.pop(job_id, None)
        return {"status": job["status"], "reply": job.get("reply", "")}


# ---------------------------------------------------------------------------
# Gap Check API
# ---------------------------------------------------------------------------

def _api_gap_check_state() -> dict[str, Any]:
    """Return the last-checked upstream repo state from upstream_state.json."""
    state_file = get_state_dir() / "upstream_state.json"
    if not state_file.exists():
        return {"repos": {}}
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
        return {"repos": data.get("repos", {})}
    except Exception:
        return {"repos": {}}


def _api_gap_check_post(
    body: dict[str, Any],
    gap_jobs: dict[str, Any],
    gap_lock: threading.Lock,
) -> dict[str, Any]:
    """Start a gap-check job in a background thread. Returns {job_id}."""
    import subprocess
    import sys

    url = str(body.get("url", "")).strip()
    if not url:
        return {"error": "url is required"}

    if not _UPSTREAM_SCRIPT.exists():
        return {"error": f"Gap check script not found at {_UPSTREAM_SCRIPT}"}

    job_id = uuid.uuid4().hex
    with gap_lock:
        gap_jobs[job_id] = {"status": "pending", "created_at": time.monotonic()}

    def _run() -> None:
        try:
            result = subprocess.run(
                [sys.executable, str(_UPSTREAM_SCRIPT), url],
                capture_output=True,
                text=True,
                timeout=90,
            )
            output = result.stdout.strip()
            if result.returncode != 0 and result.stderr.strip():
                output = (output + "\n\nSTDERR:\n" + result.stderr.strip()).strip()
            with gap_lock:
                gap_jobs[job_id] = {
                    "status": "done" if result.returncode == 0 else "error",
                    "output": output,
                    "created_at": time.monotonic(),
                }
        except Exception as exc:
            LOGGER.exception("Gap check job failed job_id=%s", job_id)
            with gap_lock:
                gap_jobs[job_id] = {
                    "status": "error",
                    "output": str(exc),
                    "created_at": time.monotonic(),
                }

    t = threading.Thread(target=_run, daemon=True, name=f"gap-check-{job_id[:8]}")
    t.start()
    return {"job_id": job_id}


def _api_gap_check_poll(
    job_id: str,
    gap_jobs: dict[str, Any],
    gap_lock: threading.Lock,
) -> dict[str, Any]:
    with gap_lock:
        job = gap_jobs.get(job_id)
        if job is None:
            return {"status": "not_found"}

        # Lazy eviction of completed jobs older than 5 minutes
        now = time.monotonic()
        stale = [
            jid for jid, j in gap_jobs.items()
            if j["status"] != "pending" and now - j.get("created_at", now) > 300
        ]
        for jid in stale:
            del gap_jobs[jid]

        if job["status"] == "pending":
            return {"status": "pending"}

        gap_jobs.pop(job_id, None)
        return {"status": job["status"], "output": job.get("output", "")}


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    _agents_dir: Path
    _shared_dir: Path
    _db_path: Path
    _jobs_db_path: Path
    _config_path: Path
    _dashboard_token: str
    _chat_sessions: dict[str, Any]
    _chat_jobs: dict[str, Any]
    _chat_lock: threading.Lock
    _gap_jobs: dict[str, Any]
    _gap_lock: threading.Lock

    def log_message(self, fmt: str, *args: object) -> None:
        LOGGER.debug("web: " + fmt, *args)

    def _check_auth(self) -> bool:
        """Verify Bearer token for API routes. Returns True if authorized."""
        token = self._dashboard_token
        if not token:
            return True  # no token configured — auth disabled
        auth_header = self.headers.get("Authorization", "")
        if auth_header == f"Bearer {token}":
            return True
        # Also accept ?token= query param (for browser convenience)
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if qs.get("token", [None])[0] == token:
            return True
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"error": "Unauthorized"}')
        return False

    def _send_json(self, data: Any, status: int = 200) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)

        if path == "/":
            # Inject the dashboard token into HTML so JS can authenticate
            html = _HTML.replace(
                "const API = '';",
                f"const API = '';\nconst DASHBOARD_TOKEN = '{self._dashboard_token}';",
            )
            self._send_html(html)
            return

        # All /api/* routes require auth
        if path.startswith("/api/") and not self._check_auth():
            return

        if path == "/api/status":
            self._send_json(_api_status())
            return

        if path == "/api/agents":
            self._send_json(_api_agents(self._agents_dir))
            return

        if path == "/api/tasks":
            self._send_json(_api_tasks(self._db_path))
            return

        if path == "/api/transcripts":
            file_param = qs.get("file", [None])[0]
            self._send_json(_api_transcripts(self._shared_dir, file_param))
            return

        if path == "/api/skills":
            self._send_json(_api_skills())
            return

        if path.startswith("/api/chat/poll/"):
            job_id = path[len("/api/chat/poll/"):]
            self._send_json(_api_chat_poll(job_id, self._chat_jobs, self._chat_lock))
            return

        if path == "/api/gap-check/state":
            self._send_json(_api_gap_check_state())
            return

        if path.startswith("/api/gap-check/poll/"):
            job_id = path[len("/api/gap-check/poll/"):]
            self._send_json(_api_gap_check_poll(job_id, self._gap_jobs, self._gap_lock))
            return

        self._send_json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path.startswith("/api/") and not self._check_auth():
            return

        if path == "/api/chat":
            length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(body_bytes.decode("utf-8"))
            except ValueError:
                self._send_json({"error": "Invalid JSON"}, 400)
                return
            result = _api_chat_post(
                body,
                self._chat_sessions,
                self._chat_jobs,
                self._chat_lock,
                self._config_path,
            )
            self._send_json(result)
            return

        if path == "/api/gap-check":
            length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(body_bytes.decode("utf-8"))
            except ValueError:
                self._send_json({"error": "Invalid JSON"}, 400)
                return
            self._send_json(_api_gap_check_post(body, self._gap_jobs, self._gap_lock))
            return

        if path == "/api/webhook":
            length = int(self.headers.get("Content-Length", 0))
            body_bytes = self.rfile.read(length) if length > 0 else b"{}"
            try:
                body = json.loads(body_bytes.decode("utf-8"))
            except ValueError:
                self._send_json({"error": "Invalid JSON"}, 400)
                return
            self._handle_webhook(body)
            return

        self._send_json({"error": "Not found"}, 404)

    def _handle_webhook(self, body: dict) -> None:
        text = str(body.get("text", "")).strip()
        if not text:
            self._send_json({"error": "text is required"}, 400)
            return

        chat_id = str(body.get("chat_id", "webhook")).strip() or "webhook"
        agent = str(body.get("agent", "main")).strip() or "main"
        surface = str(body.get("surface", "")).strip()
        account_id = str(body.get("account_id", "primary")).strip()

        # Create a background job via JobStore
        from ..job_store import JobStore
        store = JobStore(self._jobs_db_path)
        job_id = store.create_job(
            chat_id=chat_id,
            account_id=account_id,
            surface=surface,
            agent=agent,
            prompt=text,
        )

        self._send_json({
            "ok": True,
            "job_id": job_id,
            "message": f"Job created. Result will be delivered to chat_id={chat_id}.",
        })


# ---------------------------------------------------------------------------
# Public server class
# ---------------------------------------------------------------------------

class WebDashboard:
    """Threaded HTTP dashboard. Call start() to launch in background."""

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        agents_dir: Path | None = None,
        shared_dir: Path | None = None,
    ) -> None:
        self._host = host
        self._port = port

        cfg = _load_config()
        project_root = Path(cfg.get("project_root", ".")).expanduser()

        self._agents_dir = agents_dir or Path(cfg.get("agents_dir", str(project_root / "agents"))).expanduser()
        self._shared_dir = shared_dir or Path(cfg.get("shared_dir", str(project_root / "shared"))).expanduser()
        self._db_path = get_state_dir() / "tasks.db"
        self._jobs_db_path = get_state_dir() / "jobs.db"
        self._config_path = get_config_file()
        self._dashboard_token: str = str(cfg.get("dashboard_token", ""))
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

        # Chat state — shared across all handler threads via class attributes
        self._chat_sessions: dict[str, Any] = {}   # chat_id → TerminalChatSession
        self._chat_jobs: dict[str, Any] = {}        # job_id  → {status, reply, created_at}
        self._chat_lock = threading.Lock()

        # Gap Check state
        self._gap_jobs: dict[str, Any] = {}         # job_id  → {status, output, created_at}
        self._gap_lock = threading.Lock()

    def start(self, *, blocking: bool = True) -> None:
        agents_dir = self._agents_dir
        shared_dir = self._shared_dir
        db_path = self._db_path
        jobs_db_path = self._jobs_db_path
        config_path = self._config_path
        chat_sessions = self._chat_sessions
        chat_jobs = self._chat_jobs
        chat_lock = self._chat_lock
        gap_jobs = self._gap_jobs
        gap_lock = self._gap_lock

        class BoundHandler(_Handler):
            pass

        BoundHandler._agents_dir = agents_dir
        BoundHandler._shared_dir = shared_dir
        BoundHandler._db_path = db_path
        BoundHandler._jobs_db_path = jobs_db_path
        BoundHandler._config_path = config_path
        BoundHandler._dashboard_token = self._dashboard_token
        BoundHandler._chat_sessions = chat_sessions
        BoundHandler._chat_jobs = chat_jobs
        BoundHandler._chat_lock = chat_lock
        BoundHandler._gap_jobs = gap_jobs
        BoundHandler._gap_lock = gap_lock

        self._server = ThreadingHTTPServer((self._host, self._port), BoundHandler)
        url = f"http://{self._host}:{self._port}"
        print(f"Dashboard running at {url}")
        LOGGER.info("Web dashboard started at %s", url)

        if blocking:
            try:
                self._server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                self._server.server_close()
        else:
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                name="web-dashboard",
                daemon=True,
            )
            self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
