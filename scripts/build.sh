#!/usr/bin/env bash
set -e

info()  { echo "[captain-build] $1"; }
ok()    { echo "✓ $1"; }

info "Building Captain AI for production..."

# Build Python backend as standalone binary
info "Bundling Python backend..."
cd captain-core
source .venv/bin/activate
pip install pyinstaller --quiet
pyinstaller --onefile \
  --name captain-core \
  --hidden-import asyncpg \
  --hidden-import aiosqlite \
  --add-data "data:data" \
  main.py
ok "Backend binary: captain-core/dist/captain-core"
cd ..

# Copy binary into Tauri sidecar location
mkdir -p captain-desktop/src-tauri/binaries
cp captain-core/dist/captain-core captain-desktop/src-tauri/binaries/captain-core-aarch64-apple-darwin

# Build Tauri app
info "Building Tauri app..."
cd captain-desktop
pnpm build
pnpm tauri build
ok "App bundle: captain-desktop/src-tauri/target/release/bundle/"

echo ""
info "Build complete!"
info "  .app: captain-desktop/src-tauri/target/release/bundle/macos/Captain.app"
info "  .dmg: captain-desktop/src-tauri/target/release/bundle/dmg/"
