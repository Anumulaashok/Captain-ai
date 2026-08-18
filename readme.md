# 🤖 MARK XXXIX (39)
### The Ultimate Cross-Platform Personal AI Assistant — By FatihMakes

> 📺 **[Watch the full setup video on YouTube](https://youtu.be/ej1f5OE3SNQ?si=lCxDhJix9ungq1Ry)**

A real-time voice AI that can hear, see, understand, and control your computer — on any OS. Supporting Windows, macOS, and Linux. Local execution. Zero subscriptions. Engineered for total autonomy.

---

## ✨ Overview

MARK XXXIX represents the pinnacle of the Jarvis series, evolving into a more flexible and robust system. It bridges the gap between the operating system and human intent. Through natural dialogue, Mark 39 analyzes your screen, processes uploaded documents, and executes complex workflows with a brand-new, adaptive interface.

It's not just an assistant — it's an extension of your digital life.

---

## 🚀 Capabilities

### Core Features
| Feature | Description |
|---|---|
| 🎙️ Real-time Voice | Ultra-low latency conversation in any language |
| 🖥️ System Control | Launch apps, manage files, execute terminal commands |
| 🧩 Autonomous Tasks | High-level planning for complex, multi-step goals |
| 👁️ Visual Awareness | Real-time screen processing and webcam vision |
| 🧠 Persistent Memory | Deeply remembers your projects, preferences, and personal context |
| ⌨️ Hybrid Input | Seamlessly switch between keyboard typing and voice commands |

---

## 🆕 What's New in XXXIX

- 📂 **Advanced File Handling** — New support for direct file uploads. Drop PDFs, source code, or images into the assistant to have them analyzed, summarized, or edited instantly.
- 🎨 **Adaptive & Flexible UI** — A complete overhaul of the interface. The new UI is fully resizable and responsive, featuring transparency controls and customizable layouts to fit your workspace perfectly.
- 🐧🍎 **Refined Cross-Platform Stability** — Major fixes for macOS and Linux compatibility. Core system actions are now more consistent across all three major operating systems.
- ⚡ **Optimized Core Engine** — Significant performance boost in tool-calling logic and response generation, resulting in a 40% faster interaction speed.

---

## ⚡ Quick Start

```bash
git clone https://github.com/Anumulaashok/Captain-ai.git
cd Captain-ai
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install
python main.py
```

`requirements.txt` is fully pinned and covers every package actually imported by the
code, including document/media processing (pandas, pdfplumber, PyPDF2, pydub,
python-docx) and integrations (psycopg2, pinecone, slack_sdk) that were previously
missing entirely. Windows-only packages (comtypes, pycaw, win10toast, pywinauto) install
automatically only on Windows via environment markers — nothing extra to do per OS.

For development (tests, linting): `pip install -r requirements-dev.txt`.

## 🔑 Configuration

Required, at minimum:

| File | Key | What it's for |
|---|---|---|
| `config/api_keys.json` | `gemini_api_key` | Every LLM call — planning, tool execution, voice. Get one free at [aistudio.google.com](https://aistudio.google.com/apikey). |

Optional, per integration you want to enable (`config/integrations.json` — see
`integrations/manager.py:INTEGRATIONS` for the full list; connect via the in-app
`integration_setup` tool or by editing this file directly):

| Integration | Required keys |
|---|---|
| Gmail | `google_client_id`, `google_client_secret` |
| Slack | `slack_bot_token` (optional: `slack_default_channel`) |
| GitHub | `github_token` (optional: `github_username`) |
| Notion | `notion_token` |
| Linear | `linear_api_key` |
| Jira | `jira_url`, `jira_email`, `jira_api_token` |

Optional, for persistent memory across sessions (falls back to local JSON files under
`memory/` if not configured):

| Service | Where it's read from |
|---|---|
| PostgreSQL (Neon or any Postgres) | `postgres` credential, `url` key — set via `integrations/manager.py` helpers |
| Pinecone (semantic memory) | see `integrations/pinecone_memory.py` |

None of these files are committed — `config/api_keys.json`, `config/integrations.json`,
and `config/tokens/` are all gitignored.

---

## 📋 Requirements

| Requirement | Details |
|---|---|
| **OS** | Windows 10/11, macOS, or Linux |
| **Python** | 3.11 or 3.12 |
| **Microphone** | Required for voice interaction |
| **API Key** | Free Gemini API key |

---

## ⚠️ License

Personal and non-commercial use only.
Licensed under **[Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)**.

---

## 👤 Connect with the Creator

Engineered by a developer building a real-world JARVIS-style assistant.
⭐ **Star the repository to support the journey to Mark 100.**

| Platform | Link |
|---|---|
| YouTube | [@FatihMakes](https://www.youtube.com/@FatihMakes) |
| Instagram | [@fatihmakes](https://www.instagram.com/fatihmakes) |
