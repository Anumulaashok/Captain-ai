# Captain AI — Architecture Design Document

> Production-ready, fully local macOS AI assistant  
> Hardware target: MacBook, 16 GB RAM, ~250 GB free storage

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Technology Stack Decisions](#2-technology-stack-decisions)
3. [High-Level Architecture Diagram](#3-high-level-architecture-diagram)
4. [Folder Structure](#4-folder-structure)
5. [Database Schema](#5-database-schema)
6. [Agent Framework Design](#6-agent-framework-design)
7. [Memory System Design](#7-memory-system-design)
8. [Voice System Design](#8-voice-system-design)
9. [Model Management Design](#9-model-management-design)
10. [Security Architecture](#10-security-architecture)
11. [API Contracts](#11-api-contracts)
12. [Event Flow](#12-event-flow)
13. [Development Roadmap](#13-development-roadmap)
14. [Hardware Usage Estimates](#14-hardware-usage-estimates)
15. [Risks & Mitigations](#15-risks--mitigations)
16. [Packaging & Distribution](#16-packaging--distribution)

---

## 1. System Overview

Captain AI is a layered system with four primary subsystems:

```
┌─────────────────────────────────────────────────────────┐
│                    DESKTOP SHELL (Tauri)                │
│   React/TypeScript UI  ←→  Rust IPC Bridge             │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP + WebSocket
┌──────────────────────▼──────────────────────────────────┐
│                  CAPTAIN CORE (Python/FastAPI)           │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │Orchestrator │  │ Voice Engine │  │ Model Manager │  │
│  └──────┬──────┘  └──────────────┘  └───────────────┘  │
│         │                                               │
│  ┌──────▼──────────────────────────────────────────┐    │
│  │              Agent Framework                    │    │
│  │  Coding│Email│Browser│Calendar│File│Terminal    │    │
│  │  Research│…future agents…                       │    │
│  └──────┬──────────────────────────────────────────┘    │
│         │                                               │
│  ┌──────▼──────────────────────────────────────────┐    │
│  │              Memory System                      │    │
│  │  SQLite (structured) + ChromaDB (vectors)       │    │
│  └─────────────────────────────────────────────────┘    │
└──────────────────────┬──────────────────────────────────┘
                       │ gRPC/REST
┌──────────────────────▼──────────────────────────────────┐
│                  LLM RUNTIME LAYER                      │
│  Ollama (primary)  │  MLX (Apple Silicon)  │  llama.cpp  │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Technology Stack Decisions

### Desktop Framework: **Tauri v2** (over Electron)

| Criterion        | Tauri                          | Electron                        |
|-----------------|--------------------------------|---------------------------------|
| Binary size     | ~10 MB                         | ~150 MB                         |
| RAM at idle     | ~50 MB                         | ~200–400 MB                     |
| CPU at idle     | Near zero                      | 1–3% baseline                   |
| Native look     | Uses macOS WebView (excellent) | Chromium (acceptable)           |
| Security        | Rust-safe, no Node.js surface  | Node.js attack surface          |
| macOS APIs      | First-class Rust bindings      | Via native modules               |
| Build tooling   | `cargo`-based, fast            | node/npm-based                  |
| **Verdict**     | ✅ **Choose Tauri**            | Only if web-compat is critical  |

### Backend: **Python 3.11+ + FastAPI**
- AsyncIO throughout for non-blocking LLM streaming
- Pydantic v2 for schema validation
- SQLAlchemy 2.0 async for SQLite
- WebSockets for real-time streaming tokens

### LLM Runtime Strategy (layered)

```
1. Ollama (default)    — easiest model management, REST API, broad model support
2. MLX (Apple Silicon) — fastest on M1/M2/M3, 2–4× faster than Ollama for inference
3. llama.cpp           — fallback/advanced, most quantization options
```

**Recommended models for 16 GB RAM:**

| Use Case        | Model                    | Size   | RAM    | Quality |
|----------------|--------------------------|--------|--------|---------|
| Daily chat/tasks | Qwen2.5-7B-Instruct (Q4) | 4.7 GB | 6 GB   | ★★★★   |
| Coding          | Qwen2.5-Coder-7B (Q4)   | 4.7 GB | 6 GB   | ★★★★   |
| Fast/light      | Gemma2-2B (Q8)           | 2.7 GB | 3.5 GB | ★★★    |
| Heavy reasoning | Mistral-7B-v0.3 (Q5)    | 5.1 GB | 7 GB   | ★★★★   |
| Multimodal      | LLaVA-7B (Q4)            | 4.5 GB | 7 GB   | ★★★    |

**Note:** Run one 7B Q4 model at a time on 16 GB. The OS + app uses ~4–5 GB, leaving ~11 GB for model.

### Voice
- **STT**: `faster-whisper` (whisper.cpp port, 3–5× faster, tiny.en = 39 MB, base.en = 142 MB)
- **TTS**: `piper-tts` (neural, offline, <100 ms latency, natural-sounding voices)
- **Wake word**: `openwakeword` (runs at <1% CPU)

### Database
- **SQLite** (via SQLAlchemy async) — conversations, agent state, preferences, logs
- **ChromaDB** (local mode) — vector embeddings for semantic memory search
- **Keychain** — macOS Keychain via `keyring` library for secrets

---

## 3. High-Level Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          macOS Menu Bar                             │
│  [Captain Icon] → Quick Chat | Agents | Settings | Quit            │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│                     Tauri Desktop Shell                             │
│  ┌──────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────────────┐  │
│  │   Chat   │ │Agents  │ │Models  │ │Memory  │ │Settings / Logs │  │
│  └────┬─────┘ └───┬────┘ └───┬────┘ └───┬────┘ └───────┬────────┘  │
│       └───────────┴──────────┴──────────┴───────────────┘          │
│                    Tauri IPC / HTTP+WS Bridge                       │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│                     Captain Core  (FastAPI :8765)                   │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      Orchestrator                           │    │
│  │  Intent Classifier → Task Planner → Agent Router           │    │
│  │  Task Executor → Result Aggregator → Response Formatter     │    │
│  └──────────────────────────┬──────────────────────────────────┘    │
│                             │                                       │
│  ┌──────────────────────────▼──────────────────────────────────┐    │
│  │                    Agent Registry                           │    │
│  │  ┌──────────┐ ┌───────┐ ┌─────────┐ ┌──────────┐          │    │
│  │  │  Coding  │ │ Email │ │ Browser │ │ Calendar │  ...      │    │
│  │  └──────────┘ └───────┘ └─────────┘ └──────────┘          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ┌────────────────┐  ┌───────────────┐  ┌────────────────────┐      │
│  │  Voice Engine  │  │ Model Manager │  │  Memory System     │      │
│  │  STT + TTS     │  │ Ollama + MLX  │  │  SQLite+ChromaDB   │      │
│  │  Wake word     │  │ Download/Del  │  │  Episodic+Semantic │      │
│  └────────────────┘  └───────────────┘  └────────────────────┘      │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────┐
│                       LLM Runtime Layer                             │
│  ┌─────────────────┐  ┌───────────────────┐  ┌──────────────────┐  │
│  │     Ollama      │  │     MLX Server    │  │   llama.cpp      │  │
│  │  :11434 REST    │  │  Python bindings  │  │  subprocess      │  │
│  └─────────────────┘  └───────────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Folder Structure

```
captain/
├── ARCHITECTURE.md
├── README.md
├── Makefile                    # dev shortcuts
├── .env.example
│
├── captain-core/               # Python backend
│   ├── pyproject.toml
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # settings / env
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── chat.py         # /api/chat (stream)
│   │   │   ├── agents.py       # /api/agents
│   │   │   ├── models.py       # /api/models (CRUD)
│   │   │   ├── memory.py       # /api/memory
│   │   │   ├── voice.py        # /api/voice
│   │   │   └── settings.py     # /api/settings
│   │   ├── websocket.py        # WS event bus
│   │   └── middleware.py       # CORS, auth, logging
│   │
│   ├── orchestrator/
│   │   ├── __init__.py
│   │   ├── orchestrator.py     # main orchestrator
│   │   ├── intent.py           # intent classification
│   │   ├── planner.py          # task decomposition
│   │   └── executor.py         # parallel task execution
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py             # AgentBase ABC
│   │   ├── registry.py         # agent discovery + registration
│   │   ├── coding/
│   │   │   ├── __init__.py
│   │   │   └── agent.py
│   │   ├── email/
│   │   │   ├── __init__.py
│   │   │   └── agent.py
│   │   ├── browser/
│   │   │   ├── __init__.py
│   │   │   └── agent.py
│   │   ├── calendar/
│   │   │   ├── __init__.py
│   │   │   └── agent.py
│   │   ├── file/
│   │   │   ├── __init__.py
│   │   │   └── agent.py
│   │   ├── terminal/
│   │   │   ├── __init__.py
│   │   │   └── agent.py
│   │   └── research/
│   │       ├── __init__.py
│   │       └── agent.py
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── manager.py          # unified memory interface
│   │   ├── episodic.py         # conversation + event history
│   │   ├── semantic.py         # ChromaDB vector store
│   │   ├── preferences.py      # user preferences store
│   │   └── schemas.py          # pydantic memory models
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── manager.py          # model lifecycle management
│   │   ├── ollama_client.py    # Ollama API client
│   │   ├── mlx_client.py       # MLX inference
│   │   ├── llamacpp_client.py  # llama.cpp subprocess
│   │   └── registry.py         # known models catalog
│   │
│   ├── voice/
│   │   ├── __init__.py
│   │   ├── engine.py           # voice engine coordinator
│   │   ├── stt.py              # faster-whisper STT
│   │   ├── tts.py              # piper TTS
│   │   └── wakeword.py         # openwakeword listener
│   │
│   ├── security/
│   │   ├── __init__.py
│   │   ├── keychain.py         # macOS Keychain integration
│   │   ├── encryption.py       # AES-256-GCM local encryption
│   │   └── permissions.py      # agent permission manager
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py         # SQLAlchemy async engine
│   │   ├── models.py           # ORM models
│   │   └── migrations/         # Alembic migrations
│   │
│   └── tests/
│       ├── test_orchestrator.py
│       ├── test_agents.py
│       ├── test_memory.py
│       └── test_voice.py
│
├── captain-desktop/            # Tauri + React frontend
│   ├── src-tauri/
│   │   ├── Cargo.toml
│   │   ├── tauri.conf.json
│   │   └── src/
│   │       ├── main.rs         # Tauri app entry
│   │       ├── commands.rs     # IPC commands
│   │       ├── tray.rs         # system tray
│   │       └── updater.rs      # auto-update
│   │
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── store/              # Zustand state
│       │   ├── chat.ts
│       │   ├── agents.ts
│       │   ├── models.ts
│       │   └── settings.ts
│       ├── pages/
│       │   ├── Chat.tsx
│       │   ├── Agents.tsx
│       │   ├── Models.tsx
│       │   ├── Memory.tsx
│       │   ├── Settings.tsx
│       │   └── Logs.tsx
│       ├── components/
│       │   ├── MessageBubble.tsx
│       │   ├── VoiceButton.tsx
│       │   ├── ModelCard.tsx
│       │   ├── AgentCard.tsx
│       │   └── StreamingText.tsx
│       └── lib/
│           ├── api.ts          # HTTP client
│           └── ws.ts           # WebSocket client
│
└── scripts/
    ├── setup.sh                # dev environment setup
    ├── build.sh                # production build
    ├── notarize.sh             # macOS notarization
    └── release.sh              # full release pipeline
```

---

## 5. Database Schema

### SQLite (SQLAlchemy ORM)

```sql
-- Conversations
CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,   -- uuid4
    title       TEXT,
    created_at  DATETIME NOT NULL,
    updated_at  DATETIME NOT NULL,
    model_id    TEXT,
    agent_id    TEXT,
    meta        JSON
);

-- Messages
CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role            TEXT NOT NULL,  -- user | assistant | system | tool
    content         TEXT NOT NULL,
    tokens_used     INTEGER,
    latency_ms      INTEGER,
    created_at      DATETIME NOT NULL,
    meta            JSON            -- tool calls, citations, etc.
);

-- Models
CREATE TABLE models (
    id              TEXT PRIMARY KEY,   -- e.g. "qwen2.5-7b-instruct-q4"
    name            TEXT NOT NULL,
    provider        TEXT NOT NULL,      -- ollama | mlx | llamacpp
    family          TEXT,               -- llama | qwen | mistral | gemma
    size_gb         REAL,
    ram_required_gb REAL,
    quantization    TEXT,
    is_active       BOOLEAN DEFAULT 0,
    is_downloaded   BOOLEAN DEFAULT 0,
    downloaded_at   DATETIME,
    last_used_at    DATETIME,
    performance_tps REAL,               -- measured tokens/sec
    meta            JSON
);

-- Agents
CREATE TABLE agents (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    is_enabled  BOOLEAN DEFAULT 1,
    permissions JSON,                   -- list of allowed capabilities
    config      JSON,
    created_at  DATETIME NOT NULL
);

-- Tasks
CREATE TABLE tasks (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id),
    agent_id        TEXT REFERENCES agents(id),
    status          TEXT NOT NULL,      -- pending|running|done|failed|cancelled
    intent          TEXT,
    input           JSON,
    output          JSON,
    error           TEXT,
    started_at      DATETIME,
    completed_at    DATETIME,
    created_at      DATETIME NOT NULL
);

-- Memory (long-term facts)
CREATE TABLE memory_entries (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL,          -- fact | preference | entity | event
    key         TEXT,
    value       TEXT NOT NULL,
    source      TEXT,                   -- conversation_id or agent_id
    embedding_id TEXT,                  -- ChromaDB doc ID
    confidence  REAL DEFAULT 1.0,
    created_at  DATETIME NOT NULL,
    expires_at  DATETIME
);

-- Preferences
CREATE TABLE preferences (
    key         TEXT PRIMARY KEY,
    value       JSON NOT NULL,
    updated_at  DATETIME NOT NULL
);

-- Logs
CREATE TABLE logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level       TEXT NOT NULL,          -- DEBUG|INFO|WARN|ERROR
    component   TEXT,
    message     TEXT NOT NULL,
    data        JSON,
    created_at  DATETIME NOT NULL
);
```

### ChromaDB Collections

```
collection: "long_term_memory"
  - documents: extracted facts, summaries, notes
  - metadatas: {type, source, created_at, agent_id}
  - embeddings: nomic-embed-text (local, via Ollama)

collection: "conversation_summaries"
  - documents: conversation summaries (auto-generated after N messages)
  - metadatas: {conversation_id, date, participant}

collection: "documents"
  - documents: indexed local files (for file agent)
  - metadatas: {path, filename, mime_type, modified_at}
```

---

## 6. Agent Framework Design

### Base Agent Contract

```python
class AgentBase(ABC):
    id: str                    # unique agent identifier
    name: str                  # display name
    description: str           # capability description for orchestrator
    capabilities: list[str]    # ["read_email", "draft_email", ...]
    permissions: list[str]     # system permissions required

    async def run(self, task: AgentTask) -> AgentResult
    async def validate_permissions(self) -> bool
    async def get_tools(self) -> list[Tool]      # LLM function-calling tools
    async def health_check(self) -> HealthStatus
```

### Agent Tool Model (OpenAI-compatible function calling)

```python
class Tool(BaseModel):
    name: str
    description: str
    parameters: dict            # JSON Schema
    handler: Callable           # actual implementation
```

### Task & Result Models

```python
class AgentTask(BaseModel):
    id: str
    agent_id: str
    intent: str
    user_message: str
    context: dict               # conversation history, user prefs
    tools_available: list[str]
    max_iterations: int = 10

class AgentResult(BaseModel):
    task_id: str
    success: bool
    response: str
    artifacts: list[Artifact]   # files, code, urls, etc.
    tool_calls: list[ToolCall]
    tokens_used: int
    latency_ms: int
    error: str | None
```

### Multi-Agent Orchestration Flow

```
User: "Research the latest Rust async patterns and write a summary to research.md"

Orchestrator Intent Classification:
  → Research subtask: ResearchAgent
  → File write subtask: FileAgent

Task Plan:
  1. ResearchAgent.search("Rust async patterns 2024") [parallel]
  2. ResearchAgent.summarize(results)                  [sequential]
  3. FileAgent.write("research.md", summary)           [sequential]
  4. Format final response for user

Memory Written:
  → long_term_memory: "User is interested in Rust async"
  → preferences: "User stores research in *.md files"
```

---

## 7. Memory System Design

### Memory Architecture

```
┌─────────────────────────────────────────────────┐
│                 Memory Manager                  │
│  (unified interface for all memory operations)  │
└──────┬─────────────┬──────────────┬─────────────┘
       │             │              │
┌──────▼──────┐ ┌────▼──────┐ ┌────▼──────────────┐
│  Episodic   │ │ Semantic  │ │   Preferences     │
│  (SQLite)   │ │(ChromaDB) │ │   (SQLite)        │
│             │ │           │ │                   │
│ - messages  │ │ - vector  │ │ - user prefs      │
│ - tasks     │ │   search  │ │ - agent configs   │
│ - events    │ │ - facts   │ │ - UI state        │
│ - timeline  │ │ - docs    │ │ - model prefs     │
└─────────────┘ └───────────┘ └───────────────────┘
```

### Memory Retrieval Strategy

1. **Recency** — last N messages from current conversation (SQLite)
2. **Semantic relevance** — ChromaDB cosine similarity search on user query
3. **Explicit facts** — named entity extraction stored as key-value pairs
4. **User preferences** — always injected into system prompt

### Context Window Budget (for 7B model, 4096 ctx)

```
System prompt:        ~200 tokens
User preferences:     ~100 tokens
Retrieved memories:   ~500 tokens
Conversation history: ~1500 tokens
User message:         ~500 tokens
Response budget:      ~1000 tokens
Safety buffer:        ~296 tokens
```

---

## 8. Voice System Design

### Pipeline

```
Microphone
    │
    ▼
[OpenWakeWord]  ←── always-on, <1% CPU, listens for "Hey Captain"
    │ wake detected
    ▼
[Audio Capture] ─── record until silence (WebRTC VAD)
    │
    ▼
[faster-whisper] ─── base.en model (~142 MB), ~300 ms transcription
    │  transcript
    ▼
[Orchestrator]  ─── process intent, run agents
    │  response text
    ▼
[Piper TTS]  ─── neural TTS, <100 ms, en_US-amy-medium voice
    │  audio
    ▼
Speaker
```

### Modes

| Mode              | Description                              | CPU Cost |
|------------------|------------------------------------------|----------|
| Wake word         | Always listening for "Hey Captain"       | <1%      |
| Push-to-talk      | Hold key combo (⌃Space) to record        | 0% idle  |
| Continuous        | Always transcribing (battery drain)      | 15–25%   |

### VAD (Voice Activity Detection)

- Use `webrtcvad` Python bindings
- Silence threshold: 1.5 seconds of silence → end recording
- Minimum recording: 0.5 seconds (ignore short noise bursts)

---

## 9. Model Management Design

### Download Flow

```
User selects model in UI
    → ModelManager.download(model_id)
    → Resolve provider (Ollama/HuggingFace/MLX)
    → Stream progress via WebSocket event: {type: "download_progress", pct: 0.42}
    → Verify checksum
    → Register in SQLite models table
    → Benchmark (run 50 token test, measure TPS)
    → WebSocket event: {type: "model_ready", model_id: "...", tps: 45}
```

### Model Registry (built-in catalog)

```python
KNOWN_MODELS = [
    {
        "id": "qwen2.5-7b-instruct-q4_k_m",
        "name": "Qwen 2.5 7B Instruct",
        "provider": "ollama",
        "ollama_id": "qwen2.5:7b-instruct-q4_K_M",
        "size_gb": 4.7,
        "ram_required_gb": 6.0,
        "recommended_for": ["chat", "tasks", "coding"],
        "description": "Best all-around model for 16 GB Macs",
    },
    # ... more models
]
```

### Model Switching (zero-downtime)

```
1. Load new model into Ollama (background)
2. Wait for "model loaded" signal
3. Swap active_model pointer in config
4. Unload previous model from Ollama (free RAM)
5. WebSocket event: {type: "model_switched"}
```

---

## 10. Security Architecture

### Principles

1. **Local-only by default** — no outbound network calls except user-initiated model downloads
2. **Minimal permissions** — each agent declares exactly what it needs
3. **Keychain-backed secrets** — credentials stored in macOS Keychain, never on disk
4. **Sandboxed agent execution** — agents run in restricted subprocess scope
5. **Encrypted storage** — sensitive DB fields encrypted with AES-256-GCM

### macOS Permissions Required

| Permission       | Used By                    | Request Timing     |
|-----------------|----------------------------|--------------------|
| Microphone      | Voice engine               | On first voice use |
| Accessibility   | Browser/Calendar agents    | On agent enable    |
| Full Disk Access| File agent                 | On agent enable    |
| Contacts        | Email/Calendar agents      | On agent enable    |
| Calendar        | Calendar agent             | On agent enable    |

### Credential Storage (Keychain)

```
Service: "CaptainAI"
Accounts:
  - "email_oauth_token"     → OAuth token (Email agent)
  - "openai_api_key"        → Future cloud plugin
  - "anthropic_api_key"     → Future cloud plugin
  - "db_encryption_key"     → AES key for SQLite encryption
```

### Agent Permission Model

```python
class Permission(str, Enum):
    FILESYSTEM_READ  = "filesystem:read"
    FILESYSTEM_WRITE = "filesystem:write"
    NETWORK_FETCH    = "network:fetch"
    EMAIL_READ       = "email:read"
    EMAIL_WRITE      = "email:write"
    CALENDAR_READ    = "calendar:read"
    CALENDAR_WRITE   = "calendar:write"
    TERMINAL_EXECUTE = "terminal:execute"
    BROWSER_OPEN     = "browser:open"
```

---

## 11. API Contracts

### REST Endpoints

```
POST   /api/chat                    # send message, returns stream
GET    /api/conversations           # list conversations
GET    /api/conversations/:id       # get conversation with messages
DELETE /api/conversations/:id

GET    /api/agents                  # list all agents + status
POST   /api/agents/:id/enable
POST   /api/agents/:id/disable
POST   /api/agents/:id/run          # run agent directly

GET    /api/models                  # list all models (catalog + installed)
POST   /api/models/:id/download     # start download
DELETE /api/models/:id              # delete model files
POST   /api/models/:id/activate     # switch active model
GET    /api/models/active           # get active model info

GET    /api/memory                  # search memory
POST   /api/memory                  # add memory entry
DELETE /api/memory/:id

GET    /api/settings
PUT    /api/settings

POST   /api/voice/transcribe        # transcribe audio file
POST   /api/voice/speak             # TTS, returns audio stream
POST   /api/voice/wake/enable
POST   /api/voice/wake/disable
```

### WebSocket Events (`ws://localhost:8765/ws`)

```json
// Server → Client
{"type": "token",            "data": {"text": "Hello", "done": false}}
{"type": "token",            "data": {"text": "", "done": true}}
{"type": "agent_started",    "data": {"agent_id": "coding", "task_id": "..."}}
{"type": "agent_finished",   "data": {"task_id": "...", "success": true}}
{"type": "download_progress","data": {"model_id": "...", "pct": 0.42, "speed_mb": 12.3}}
{"type": "model_ready",      "data": {"model_id": "...", "tps": 45}}
{"type": "voice_transcript", "data": {"text": "What's the weather?", "confidence": 0.97}}
{"type": "wake_detected",    "data": {"confidence": 0.94}}
{"type": "system_event",     "data": {"level": "INFO", "message": "..."}}
```

---

## 12. Event Flow

### Complete Chat Request Flow

```
1. User types/speaks message
   └── [UI] ChatInput.send() → WebSocket or POST /api/chat

2. Captain Core receives request
   └── [API] chat.py receives, creates conversation/message record

3. Orchestrator processes
   ├── [Intent] classify: "What is this about?" → simple_chat | agent_task | multi_agent
   ├── [Memory] retrieve: semantic search + recent history
   └── [Planner] if agent_task: decompose into steps

4a. Simple chat path
    └── [ModelManager] stream tokens from Ollama
        └── WebSocket: {type: "token", data: {text: "..."}}

4b. Agent task path
    ├── [AgentRegistry] find best agent(s)
    ├── [Executor] run agent(s), possibly in parallel
    │   ├── [Agent] run tool loop (LLM function-calling)
    │   ├── [Agent] execute tools (real side effects)
    │   └── [Agent] synthesize final response
    └── WebSocket: agent_started / tool_calls / agent_finished

5. Memory consolidation
   └── [Memory] extract facts → ChromaDB + SQLite

6. Response delivered
   └── [UI] display streaming tokens + artifacts
```

---

## 13. Development Roadmap

### Phase 1 — MVP (Weeks 1–4)

**Goal:** Basic chat working with local models

- [x] Project scaffold (backend + frontend)
- [ ] FastAPI server with `/api/chat` streaming endpoint
- [ ] Ollama client integration
- [ ] SQLite conversation storage
- [ ] Tauri desktop shell with Chat page
- [ ] Basic model manager (download, switch, delete)
- [ ] System tray integration

**Deliverable:** User can chat with Qwen2.5-7B locally

### Phase 2 — Voice + Memory (Weeks 5–7)

- [ ] faster-whisper STT integration
- [ ] Piper TTS integration
- [ ] OpenWakeWord wake-word detection
- [ ] ChromaDB semantic memory
- [ ] Memory page in UI
- [ ] Context injection from memory into prompts

**Deliverable:** Full voice conversation with memory

### Phase 3 — Agent Framework (Weeks 8–11)

- [ ] AgentBase class + registry
- [ ] Orchestrator with intent classification
- [ ] CodingAgent (code gen, explain, review)
- [ ] FileAgent (search, read, summarize)
- [ ] TerminalAgent (safe shell execution)
- [ ] ResearchAgent (web search + summarize)
- [ ] Agents page in UI with enable/disable
- [ ] Permission management dialog

**Deliverable:** Multi-agent task execution

### Phase 4 — Full Polish (Weeks 12–16)

- [ ] EmailAgent (Apple Mail integration)
- [ ] CalendarAgent (EventKit)
- [ ] BrowserAgent (Playwright)
- [ ] MLX inference backend
- [ ] Settings page (all preferences)
- [ ] Logs page (real-time)
- [ ] Dark/light mode
- [ ] macOS notifications
- [ ] Performance profiling + optimization

**Deliverable:** Production-ready v1.0

### Phase 5 — Packaging & Distribution

- [ ] macOS code signing
- [ ] Notarization
- [ ] Auto-update (Sparkle/Tauri updater)
- [ ] DMG installer
- [ ] App Store consideration

---

## 14. Hardware Usage Estimates

### Idle (no LLM loaded)

| Component        | CPU    | RAM     | Disk I/O |
|-----------------|--------|---------|----------|
| Tauri shell      | 0.0%   | 50 MB   | minimal  |
| FastAPI server   | 0.1%   | 80 MB   | minimal  |
| Wake word        | 0.5%   | 30 MB   | none     |
| ChromaDB         | 0.0%   | 40 MB   | none     |
| **Total idle**   | **~1%**| **~200 MB** | minimal |

### Active Chat (Qwen2.5-7B Q4 via Ollama)

| Component        | CPU    | RAM     | Notes                        |
|-----------------|--------|---------|------------------------------|
| Model loaded     | 0%     | 5.5 GB  | stays resident between turns |
| During inference | 50–80% | +500 MB | Apple Neural Engine helps    |
| FastAPI + app    | 2%     | 200 MB  | baseline                     |
| **Total active** | **~60%**| **~6.2 GB** | leaves 9.8 GB free    |

### Voice Active (STT + TTS + model)

| Component        | CPU    | RAM     |
|-----------------|--------|---------|
| faster-whisper   | 30%    | 300 MB  |
| Piper TTS        | 5%     | 100 MB  |
| Model (7B Q4)    | 60%    | 5.5 GB  |
| **Total**        | **~95%** | **~6.1 GB** |

**Recommendation:** During voice + inference, close other heavy apps. The 16 GB is sufficient but not spacious.

### Storage Usage

| Component                  | Size      |
|---------------------------|-----------|
| Captain app + runtime      | ~500 MB   |
| Qwen2.5-7B Q4 model        | 4.7 GB    |
| Whisper base.en model      | 142 MB    |
| Piper TTS voice            | 60 MB     |
| ChromaDB + SQLite data     | 1–5 GB    |
| **Total**                  | **~7 GB** |

---

## 15. Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| RAM exhaustion with large models | High | Enforce model size limits per available RAM; auto-unload idle models |
| Ollama process crash | Medium | Health check every 30s; auto-restart; fallback to llama.cpp |
| Wake word false positives | Medium | Confirmation threshold 0.85; visual indicator; push-to-talk alternative |
| Agent tool misuse (e.g. rm -rf) | High | Allowlist of safe commands; confirmation dialog for destructive ops |
| macOS permission revocation | Medium | Permission check before each agent run; graceful degradation |
| SQLite corruption | Low | WAL mode; nightly backups to ~/Library/Application Support/Captain/backups/ |
| Model download corruption | Medium | SHA256 verification; resume-capable downloads |
| STT accuracy for technical terms | Medium | Whisper small.en for better accuracy; user correction flow |
| Electron/Tauri WebView crashes | Low | Crash reporting; auto-restart renderer |
| API key storage (future cloud) | High | Keychain only; never written to disk or env files |

---

## 16. Packaging & Distribution

### Development Build
```bash
# Terminal 1: Python backend
cd captain-core && uvicorn main:app --reload --port 8765

# Terminal 2: Tauri frontend
cd captain-desktop && pnpm tauri dev
```

### Production Build
```bash
cd captain-desktop
pnpm tauri build
# Output: src-tauri/target/release/bundle/macos/Captain.app
#         src-tauri/target/release/bundle/dmg/Captain_1.0.0_aarch64.dmg
```

### macOS Signing + Notarization
```bash
# Sign
codesign --deep --force --verify --verbose \
  --sign "Developer ID Application: Your Name (TEAM_ID)" \
  Captain.app

# Notarize
xcrun notarytool submit Captain.dmg \
  --apple-id "your@email.com" \
  --team-id "TEAM_ID" \
  --password "@keychain:AC_PASSWORD" \
  --wait

# Staple
xcrun stapler staple Captain.dmg
```

### Auto-Updates
- Tauri Updater plugin reads from `https://releases.captain.ai/latest.json`
- Background update check every 24h
- User prompted before applying update
- Rollback supported via previous version cache
