# ⚓ Captain AI

> Production-ready, fully local macOS AI assistant — voice-enabled, multi-agent, always-on.

## What is Captain?

Captain is a Jarvis-style AI assistant for macOS that:
- Runs **entirely on your Mac** (no cloud required by default)
- Streams responses from **local LLMs** via Ollama (Qwen2.5, Mistral, Gemma, Llama)
- Supports **voice interaction** — wake word, push-to-talk, TTS
- Runs **7 intelligent agents** (Coding, Email, Browser, Calendar, File, Terminal, Research)
- Stores **long-term memory** in Pinecone + Neon PostgreSQL
- Lives in the **macOS menu bar** with a full Tauri desktop UI

## Architecture

```
Tauri Desktop (React + TypeScript)
    ↕ HTTP + WebSocket
FastAPI Backend (Python 3.11)
    ├── Orchestrator (intent → agent routing)
    ├── 7 Agents (coding, email, browser, calendar, file, terminal, research)
    ├── Memory (Neon PostgreSQL + Pinecone)
    ├── Voice (faster-whisper STT + piper TTS + openwakeword)
    └── Model Manager (Ollama + MLX)
```

See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full design document.

## Quick Start

### Prerequisites

- macOS 13+, Apple Silicon or Intel
- Python 3.11+
- Node.js 20+
- Rust (for Tauri)
- [Ollama](https://ollama.ai) (`brew install ollama`)

### Setup

```bash
# Clone and enter project
cd captain

# One-command setup
make setup

# Start development
make dev
```

This opens the Tauri window and starts the FastAPI backend on `localhost:8765`.

### First Run

1. Open the **Models** tab — download `Qwen 2.5 7B` (recommended)
2. Open the **Accounts** tab — verify Neon + Pinecone are connected
3. Go to **Chat** and start talking to Captain
4. Enable agents in the **Agents** tab as needed

## Services

| Service | Purpose | Config |
|---------|---------|--------|
| Neon PostgreSQL | Conversations, agents, tasks, preferences | `DATABASE_URL` in `.env` |
| Pinecone | Semantic memory search | `PINECONE_API_KEY` in `.env` |
| Ollama | LLM inference | Auto-detected at `localhost:11434` |

## App Icon Integration

**Click the menu bar icon** → main window opens  
**Right-click the menu bar icon** → Quick menu: New Chat, Accounts & Connections, Toggle Voice, Quit  
**Menu item "Accounts & Connections"** → Opens the Accounts page showing live status of all connected services

## Recommended Models (16 GB Mac)

| Model | Size | RAM | Best For |
|-------|------|-----|----------|
| Qwen 2.5 7B Instruct Q4 | 4.7 GB | 6 GB | General chat, tasks |
| Qwen 2.5 Coder 7B Q4 | 4.7 GB | 6 GB | Code generation |
| Gemma 2 2B Q8 | 2.7 GB | 3.5 GB | Fast responses |
| Mistral 7B v0.3 Q5 | 5.1 GB | 7 GB | Reasoning |

## Development Commands

```bash
make dev          # Start backend + frontend (hot reload)
make backend      # Backend only
make test         # Run pytest suite
make build        # Production build + DMG
make health       # Check backend health
make accounts     # Check service connections
```

## Project Structure

```
captain/
├── captain-core/       # Python FastAPI backend
│   ├── agents/         # 7 AI agents
│   ├── memory/         # Neon + Pinecone memory system
│   ├── models/         # Ollama + MLX model manager
│   ├── voice/          # STT + TTS + wake word
│   ├── orchestrator/   # Intent classification + routing
│   └── security/       # Keychain + encryption
└── captain-desktop/    # Tauri + React frontend
    └── src/pages/      # Chat, Agents, Models, Memory, Accounts, Settings
```
