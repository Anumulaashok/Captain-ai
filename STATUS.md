# Captain AI — Project Status

> Last updated: 2026-06-03  
> Branch: `feature/captain-ai-v1`

---

## The Vision — Jarvis Layer

> "Hey Captain, what's the update?"

Captain responds with a synthesized voice briefing:

- Which agents are active and what they completed overnight
- Important notifications (emails, Slack, alerts) that need attention
- PRs waiting for your review, failed CI runs
- Financial snapshot (spending, budget, anomalies)
- Calendar — what's happening today and any conflicts
- Tasks it needs permission to finish
- New sub-agents it spawned to complete work on your behalf

This is the target. A real-time, proactive command center — not a chatbot you query, but an autonomous system that monitors, acts, and reports back to you.

---

## Layer Map — Foundation → Jarvis

```
LAYER 5 — JARVIS (autonomous proactive AI)
  Morning briefing, spawns sub-agents, requests permissions live,
  financial + PR + calendar + Slack awareness, holographic dashboard UI

LAYER 4 — MULTI-AGENT ORCHESTRATION
  Agents spawn sub-agents, parallel task execution,
  dynamic permission dialogs, cross-agent memory sharing

LAYER 3 — BACKGROUND AGENT RUNNERS
  GitHub watcher, email scanner, calendar poller, financial feed,
  agents run on schedule without user prompt

LAYER 2 — REACTIVE AGENTS (voice-triggered)
  "Hey Captain summarize my emails" — agents execute one task end-to-end,
  real tool implementations (not scaffolds)

LAYER 1 — CORE PIPELINE (WHERE WE ARE NOW)
  Voice pipeline, streaming chat, multi-model routing,
  Neon DB, Pinecone vectors, Tauri desktop shell
```

---

## Current State — Layer 1 Complete

### Backend (captain-core) — Python 3.11 + FastAPI on :8765

| Module | Files | Status |
|--------|-------|--------|
| FastAPI server + config | `main.py`, `config.py` | Done |
| API routes | `chat`, `agents`, `models`, `memory`, `voice`, `settings`, `accounts` | Done |
| WebSocket event bus | `api/websocket.py` | Done |
| Orchestrator | `orchestrator.py`, `intent.py` | Done |
| Agent framework | `base.py`, `registry.py` | Done |
| Agents | Coding, Email, Browser, Calendar, File, Terminal, Research | Scaffolded |
| Memory system | `manager.py`, `episodic.py`, `semantic.py`, `preferences.py` | Done |
| Model manager | Ollama client, MLX client, router, registry | Done |
| Voice pipeline | STT (faster-whisper), TTS (piper), wake word (openwakeword), engine | Done |
| Security | macOS Keychain, AES-256-GCM encryption, agent permissions | Done |
| Database | Neon PostgreSQL (asyncpg + SQLAlchemy 2.0 async) | Done |
| Vector store | Pinecone serverless index `captain-memory` | Done |
| Tests | `test_accounts.py`, `test_agents.py`, `test_memory.py` | Scaffolded |

### Frontend (captain-desktop) — Tauri v2 + React + TypeScript + Tailwind

| Component | File | Status |
|-----------|------|--------|
| Tauri shell + system tray | `src-tauri/src/main.rs`, `tray.rs` | Done |
| Chat page | `src/pages/Chat.tsx` | Done |
| Agents page | `src/pages/Agents.tsx` | Done |
| Models page | `src/pages/Models.tsx` | Done |
| Memory page | `src/pages/Memory.tsx` | Done |
| Settings page | `src/pages/Settings.tsx` | Done |
| Accounts page | `src/pages/Accounts.tsx` | Done |
| HTTP client | `src/lib/api.ts` | Done |
| WebSocket client | `src/lib/ws.ts` | Done |
| Chat state store | `src/store/chat.ts` | Done |

---

## Roadmap to Jarvis

### Layer 2 — Reactive Agents (next sprint)

Goal: "Hey Captain, summarize my emails" works end-to-end with real output.

- [ ] Wire streaming chat tokens end-to-end to Chat UI (token-by-token rendering)
- [ ] Ollama LLM intent classification in orchestrator (real model call, not keyword match)
- [ ] Memory context injection — retrieved Pinecone facts injected into every system prompt
- [ ] **CodingAgent** — code gen + explain via LLM, sandboxed execution with `subprocess`
- [ ] **FileAgent** — read/search/summarize local files, index into Pinecone
- [ ] **TerminalAgent** — safe shell with command allowlist + confirmation dialog
- [ ] **ResearchAgent** — web search (DuckDuckGo API) + LLM summarization loop
- [ ] Agent results displayed in Chat UI with artifact cards (code blocks, file links)
- [ ] SQLite/Alembic migrations for local conversation + task tables
- [ ] Model download + progress bar in Models page

### Layer 3 — Background Agent Runners

Goal: Agents run on a schedule and push updates to you without being asked.

- [ ] **Agent scheduler** — cron-like runner per agent (configurable interval)
- [ ] **GitHubAgent** — poll PRs awaiting review, failed CI, new issues via GitHub API
- [ ] **EmailAgent** — Apple Mail OAuth, scan inbox, extract action items
- [ ] **CalendarAgent** — EventKit: today's schedule, conflicts, upcoming deadlines
- [ ] **SlackAgent** — unread mentions, DMs flagged as urgent
- [ ] **FinanceAgent** — Plaid or bank CSV import, spending anomaly detection, budget state
- [ ] Background agent results stored in Neon + surfaced as notifications
- [ ] Notification center in Tauri tray (badge count + dropdown of pending items)
- [ ] WebSocket push from backend → UI for real-time agent status updates

### Layer 4 — Multi-Agent Orchestration

Goal: Captain breaks big tasks into sub-tasks, spawns the right agents, runs them in parallel.

- [ ] **Dynamic agent spawning** — orchestrator creates ephemeral sub-agents for a task
- [ ] **Task planner** — LLM decomposes complex intent into ordered + parallel sub-tasks
- [ ] **Parallel executor** — `asyncio.gather` across multiple agents simultaneously
- [ ] **Cross-agent memory** — agents share context via Pinecone during a task run
- [ ] **Permission request flow** — agent pauses, sends UI prompt "I need X to continue", user approves/denies
- [ ] **AgentBuilderAgent** — orchestrator can define + register a new temporary agent from a task description
- [ ] Task graph visualization in Agents page (tree of what's running / done / blocked)
- [ ] Agent-to-agent messaging via internal event bus

### Layer 5 — Jarvis Command Center

Goal: "Hey Captain, what's the update?" gives a full voice briefing + the holographic dashboard.

- [ ] **BriefingAgent** — aggregates all agent reports into a prioritized summary, reads it via TTS
- [ ] **Proactive wake** — Captain initiates voice at scheduled times ("Good morning" briefing at 8am)
- [ ] **Command Center UI** — full-screen dashboard page:
  - Animated particle/radar visualization (active agent nodes)
  - Live agent status grid (running / idle / blocked / done)
  - Notification feed (priority-ranked)
  - Financial snapshot widget
  - PR / GitHub status widget
  - Calendar strip (today's events)
  - Permission request popups (modal with approve/deny)
  - Memory activity log
- [ ] **Voice briefing script** — structured template: active agents → notifications → PRs → finances → calendar → tasks needing permission
- [ ] Multi-voice personas (different TTS voices per agent type for spatial audio feel)
- [ ] Dark holographic theme (cyan on near-black, animated glows, grid background)

---

## Tech Stack Quick Reference

| Layer | Technology |
|-------|-----------|
| Desktop shell | Tauri v2 (Rust) |
| Frontend | React + TypeScript + Tailwind CSS |
| Backend | Python 3.11, FastAPI, asyncpg, SQLAlchemy 2.0 |
| LLM primary | Ollama (REST :11434) |
| LLM fallback | MLX (Apple Silicon Python bindings) |
| STT | faster-whisper base.en |
| TTS | piper en_US-amy-medium |
| Wake word | openwakeword |
| Structured DB | Neon PostgreSQL |
| Vector DB | Pinecone serverless (`captain-memory` index) |
| Secrets | macOS Keychain |
| Encryption | AES-256-GCM |
| Scheduling | APScheduler (background agent runner) |
| Web search | DuckDuckGo API (ResearchAgent) |
| GitHub | PyGithub (GitHubAgent) |
| Finance | Plaid API or CSV import (FinanceAgent) |
| Browser automation | Playwright (BrowserAgent) |

---

## Key Files to Know

```
captain-core/main.py                        — FastAPI entry point
captain-core/orchestrator/orchestrator.py   — intent → agent routing
captain-core/orchestrator/intent.py         — LLM intent classification
captain-core/voice/engine.py                — voice pipeline coordinator
captain-core/memory/manager.py              — unified memory interface
captain-core/models/router.py               — Ollama/MLX model switching
captain-core/security/keychain.py           — macOS Keychain credential store
captain-desktop/src/pages/Chat.tsx          — main chat UI
captain-desktop/src/lib/ws.ts               — WebSocket client
```

---

## Dev Commands

```bash
make setup    # install all deps (Python venv + pnpm)
make dev      # start backend + Tauri frontend
make test     # run pytest suite
```
