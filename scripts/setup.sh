#!/usr/bin/env bash
set -e

RESET='\033[0m'
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'

info()  { echo -e "${BOLD}[captain]${RESET} $1"; }
ok()    { echo -e "${GREEN}✓${RESET} $1"; }
warn()  { echo -e "${YELLOW}⚠${RESET} $1"; }
error() { echo -e "${RED}✗${RESET} $1"; exit 1; }

info "Captain AI — Development Setup"
echo ""

# ── Prerequisites ──────────────────────────────────────────────────
info "Checking prerequisites..."

# Prefer Python 3.11 or 3.12 — 3.13/3.14 may lack binary wheels for some packages
PYTHON_BIN=""
for candidate in python3.11 python3.12 python3.13 python3.14 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done
[ -z "$PYTHON_BIN" ] && error "Python 3.11+ required. Install: brew install python@3.11"
PYTHON_VERSION=$("$PYTHON_BIN" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MINOR=$("$PYTHON_BIN" -c "import sys; print(sys.version_info.minor)")
info "Python version: $PYTHON_VERSION (using $PYTHON_BIN)"
if [ "$PYTHON_VERSION" = "3.14" ] || [ "$PYTHON_VERSION" = "3.13" ]; then
  warn "Python $PYTHON_VERSION detected. Some audio packages may need compilation."
  warn "For best compatibility, consider: brew install python@3.12"
fi

command -v node >/dev/null 2>&1 || error "Node.js 20+ required. Install: brew install node"
ok "Node.js $(node --version)"

command -v pnpm >/dev/null 2>&1 || { info "Installing pnpm..."; npm install -g pnpm; }
ok "pnpm $(pnpm --version)"

command -v rustc >/dev/null 2>&1 || error "Rust required. Install: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
ok "Rust $(rustc --version)"

command -v ollama >/dev/null 2>&1 || warn "Ollama not found. Install: brew install ollama  (required for LLM)"

# ── Python venv ────────────────────────────────────────────────────
info "Setting up Python virtual environment..."
cd captain-core
# Remove stale venv if it was built with wrong Python version
if [ -d ".venv" ]; then
  VENV_PYTHON=$(.venv/bin/python --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
  if [[ "$VENV_PYTHON" == "3.13" || "$VENV_PYTHON" == "3.14" ]]; then
    warn "Removing stale venv (Python $VENV_PYTHON — too new for all packages)"
    rm -rf .venv
  fi
fi
if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv
fi
source .venv/bin/activate
pip install --quiet --upgrade pip

# Install all dependencies directly (skip editable install to avoid build-system issues)
pip install --quiet \
  fastapi uvicorn[standard] websockets sse-starlette \
  pydantic pydantic-settings \
  "sqlalchemy[asyncio]" asyncpg alembic \
  pinecone \
  httpx aiohttp \
  ollama \
  keyring cryptography \
  pypdf python-docx pillow \
  playwright beautifulsoup4 lxml \
  rich python-multipart python-dotenv arrow \
  pytest pytest-asyncio pytest-cov

# Install voice packages separately (may need system libs)
info "Installing voice packages (may take a moment)..."
pip install --quiet faster-whisper || warn "faster-whisper failed — voice STT disabled"
pip install --quiet pyaudio sounddevice numpy || warn "pyaudio/sounddevice failed — microphone disabled"
pip install --quiet piper-tts || warn "piper-tts failed — TTS disabled"
pip install --quiet openwakeword || warn "openwakeword failed — wake word disabled"
pip install --quiet webrtcvad-wheels || pip install --quiet webrtcvad || warn "webrtcvad failed — VAD disabled"

ok "Python dependencies installed"

# ── Download Piper voice model ──────────────────────────────────────
mkdir -p data/piper
if [ ! -f "data/piper/en_US-amy-medium.onnx" ]; then
  info "Downloading Piper TTS voice model..."
  PIPER_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium"
  curl -sSL "$PIPER_BASE/en_US-amy-medium.onnx" -o data/piper/en_US-amy-medium.onnx
  curl -sSL "$PIPER_BASE/en_US-amy-medium.onnx.json" -o data/piper/en_US-amy-medium.onnx.json
  ok "Piper voice downloaded"
else
  ok "Piper voice already present"
fi

# ── Ollama models ───────────────────────────────────────────────────
if command -v ollama >/dev/null 2>&1; then
  info "Pulling recommended models (this may take a few minutes)..."
  ollama pull qwen2.5:7b-instruct-q4_K_M &
  ollama pull nomic-embed-text &
  wait
  ok "Models pulled"
fi

cd ..

# ── Frontend dependencies ──────────────────────────────────────────
info "Installing frontend dependencies..."
cd captain-desktop
pnpm install --silent
ok "Frontend dependencies installed"
cd ..

# ── .env check ─────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
  cp .env.example .env
  warn ".env created from template — add your Pinecone and DB credentials"
else
  ok ".env already exists"
fi

echo ""
info "Setup complete! Start with: ${BOLD}make dev${RESET}"
