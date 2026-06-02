#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
RESET='\033[0m'

info() { echo -e "${BOLD}[voice]${RESET} $1"; }
ok()   { echo -e "${GREEN}✓${RESET} $1"; }
warn() { echo -e "${YELLOW}⚠${RESET} $1"; }

echo ""
info "Captain AI — Voice Setup"
echo ""

CORE_DIR="$(cd "$(dirname "$0")/../captain-core" && pwd)"
cd "$CORE_DIR"

# ── 1. Fix Ollama ──────────────────────────────────────────────────
info "Step 1: Checking Ollama..."
if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  # Test if llama-server actually works
  RESULT=$(curl -sf -X POST http://localhost:11434/api/chat \
    -H "Content-Type: application/json" \
    -d '{"model":"gemma2:2b-instruct-q8_0","messages":[{"role":"user","content":"hi"}],"stream":false}' 2>/dev/null || echo '{"error":"fail"}')
  if echo "$RESULT" | grep -q '"error"'; then
    warn "Ollama is running but broken (missing llama-server binary)"
    info "Reinstalling Ollama from official installer..."
    brew services stop ollama 2>/dev/null || true
    brew uninstall ollama --force 2>/dev/null || true
    curl -fsSL https://ollama.com/install.sh | sh
    sleep 3
    ok "Ollama reinstalled"
  else
    ok "Ollama working"
  fi
else
  info "Installing Ollama..."
  curl -fsSL https://ollama.com/install.sh | sh
  sleep 3
fi

# Start Ollama if not running
ollama serve &>/dev/null &
sleep 3
ok "Ollama running"

# ── 2. Pull models ──────────────────────────────────────────────────
info "Step 2: Pulling required models..."

# Chat model
if ! ollama list 2>/dev/null | grep -q "gemma2"; then
  info "Pulling gemma2:2b (fast model, 2.7 GB)..."
  ollama pull gemma2:2b-instruct-q8_0
fi
ok "gemma2:2b ready"

# Embedding model
if ! ollama list 2>/dev/null | grep -q "nomic-embed-text"; then
  info "Pulling nomic-embed-text (274 MB)..."
  ollama pull nomic-embed-text
fi
ok "nomic-embed-text ready"

# ── 3. Install Python voice packages ───────────────────────────────
info "Step 3: Installing Python voice packages..."
source .venv/bin/activate

# Piper TTS
pip install --quiet piper-tts 2>/dev/null || \
pip install --quiet "piper-tts==1.2.0" 2>/dev/null || \
warn "piper-tts install failed — will use macOS say as fallback"

# ── 4. Download Piper voice model ──────────────────────────────────
info "Step 4: Downloading Piper TTS voice model..."
mkdir -p data/piper
PIPER_MODEL="en_US-amy-medium"
if [ ! -f "data/piper/${PIPER_MODEL}.onnx" ]; then
  PIPER_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium"
  curl -L --progress-bar \
    "${PIPER_URL}/${PIPER_MODEL}.onnx" \
    -o "data/piper/${PIPER_MODEL}.onnx" && \
  curl -sL \
    "${PIPER_URL}/${PIPER_MODEL}.onnx.json" \
    -o "data/piper/${PIPER_MODEL}.onnx.json"
  ok "Piper voice model downloaded"
else
  ok "Piper voice model already present"
fi

# ── 5. Download Whisper model ───────────────────────────────────────
info "Step 5: Pre-downloading Whisper speech-to-text model..."
mkdir -p data/whisper
python3 - <<'PYEOF'
import sys
try:
    from faster_whisper import WhisperModel
    print("  Downloading Whisper base.en model (~142 MB)...")
    m = WhisperModel("base.en", device="cpu", compute_type="int8",
                     download_root="./data/whisper")
    print("  Whisper model ready")
except Exception as e:
    print(f"  Warning: {e}")
PYEOF
ok "Whisper base.en ready"

# ── 6. Download OpenWakeWord models ────────────────────────────────
info "Step 6: Downloading wake word models..."
python3 - <<'PYEOF'
try:
    import openwakeword
    openwakeword.utils.download_models()
    print("  OpenWakeWord models downloaded")
except Exception as e:
    print(f"  Warning: {e}")
PYEOF
ok "Wake word models ready"

# ── 7. macOS Microphone permission hint ────────────────────────────
info "Step 7: Microphone access..."
echo ""
echo "  ┌─────────────────────────────────────────────────────┐"
echo "  │  IMPORTANT: Grant microphone access                 │"
echo "  │                                                     │"
echo "  │  macOS System Settings → Privacy & Security        │"
echo "  │  → Microphone → Allow 'Terminal' (dev mode)        │"
echo "  │     or 'Captain' (installed app)                   │"
echo "  └─────────────────────────────────────────────────────┘"
echo ""

# ── Done ───────────────────────────────────────────────────────────
echo ""
ok "Voice setup complete!"
echo ""
echo "  Wake word:  'Hey Captain'  (or 'Hey Jarvis' — both work)"
echo "  Push-to-talk: Hold ⌃Space in the app"
echo "  STT model:  Whisper base.en (fast, accurate)"
echo "  TTS voice:  Amy (neural, natural)"
echo ""
echo "  Start with: make backend  (then enable Voice in app Settings)"
