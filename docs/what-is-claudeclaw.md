# What is ClaudeClaw?

ClaudeClaw is a personal AI assistant that runs on your own computer and connects to your messaging apps — primarily Telegram, but also Discord and Slack.

You send it a message. It thinks. It replies. It remembers things over time.

That's the simple version. Here's what makes it different.

---

## It runs on your machine

Most AI assistants are cloud services. You send a message to a server somewhere, the server processes it, the server stores your history, and the server sends back a reply.

ClaudeClaw works differently. The assistant runtime — the part that receives your messages, builds context, manages memory, and sends replies — runs as a background process on your Mac or Windows PC. Your conversation history, memory files, notes, and settings are plain files on your own hard drive. No external account, no sync service, no third-party backend.

The only thing that leaves your machine is the message you're sending, which goes to Anthropic's Claude API to generate a reply. That's one known, documented data flow — not an opaque cloud platform.

---

## Claude Code is the brain

ClaudeClaw doesn't call a raw AI API. It runs on top of **Claude Code** — Anthropic's local CLI tool — which means the assistant has genuine access to your machine. It can read and write files, run shell commands, search the web, and interact with your projects directly.

This is the thing other personal assistants can't do. They reason in the cloud, isolated from your computer. ClaudeClaw reasons *on* your computer, which means it can actually do things: review a file, run your tests, look at a git diff, write and save code.

---

## It has memory

ClaudeClaw keeps track of conversations over time through a layered memory system:

- **Daily notes** — a running log of each day's conversations, one file per day
- **Long-term memory** — key facts and preferences extracted nightly from daily notes and saved to `MEMORY.md`
- **Session continuity** — conversations resume where they left off using Claude Code's session system

You can also tell it things directly: `/remember I prefer bullet points` or `/note call the dentist Friday` — and it writes those to memory immediately.

---

## It has agents

An "agent" is a persona — a set of instructions, personality, and context that shapes how the assistant behaves. You can have multiple agents for different purposes:

- A general personal assistant
- A coding-focused builder agent
- A research and writing agent

Each agent has its own memory, its own personality file (`AGENT.md`), and its own context about you (`USER.md`). Switching between them in chat takes one command: `/agent switch builder`.

---

## It's proactive, not just reactive

Beyond responding to messages, ClaudeClaw can reach out to you:

- **Morning briefings** — a daily digest sent at a time you configure, covering pending reminders and recent notes
- **Reminders** — schedule anything with `/remind 2h check the oven` and it will message you at the right time
- **Quiet hours** — configure a window where reminders are held back and delivered when you wake up

---

## It's private by design

| What | Where it lives |
|---|---|
| Your messages and replies | Transcript files on your hard drive |
| Memory and notes | Markdown files in your agents folder |
| Scheduled tasks | SQLite database on your hard drive |
| Config and tokens | JSON file on your hard drive |
| Tool execution | Runs locally on your machine |
| The AI reply itself | Anthropic's API (same as Claude.ai) |

Nothing is stored on a ClaudeClaw server because there is no ClaudeClaw server.

---

## What it's not

- It's not a hosted service — you install and run it yourself
- It's not a mobile app — it connects to Telegram (or Discord/Slack) so you can use those as the interface
- It's not a replacement for Claude.ai — it's a runtime that wraps Claude Code to give you a persistent, memory-aware assistant that lives in your messaging app and on your machine

---

## The one-line version

ClaudeClaw is a self-hosted personal assistant that runs Claude Code on your own computer, connects to Telegram, remembers your conversations, and can actually do things — not just talk about them.
