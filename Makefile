.PHONY: setup dev dev-backend dev-frontend test build clean

# ── Setup ──────────────────────────────────────────────────────────
setup:
	@bash scripts/setup.sh

# ── Development ────────────────────────────────────────────────────
dev:
	@echo "Starting Captain AI in development mode..."
	@make -j2 dev-backend dev-frontend

dev-backend:
	@cd captain-core && .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8765 --reload --log-level info

dev-frontend:
	@cd captain-desktop && pnpm tauri dev

# Backend only (useful for API testing)
backend:
	@cd captain-core && .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8765 --reload

# ── Testing ────────────────────────────────────────────────────────
test:
	@cd captain-core && .venv/bin/pytest tests/ -v --cov=. --cov-report=term-missing

test-watch:
	@cd captain-core && .venv/bin/pytest tests/ -v -f

# ── Production build ───────────────────────────────────────────────
build:
	@bash scripts/build.sh

# ── Maintenance ────────────────────────────────────────────────────
clean:
	@rm -rf captain-core/.venv captain-core/__pycache__ captain-core/.pytest_cache
	@rm -rf captain-desktop/node_modules captain-desktop/dist
	@rm -rf captain-desktop/src-tauri/target
	@echo "Cleaned build artifacts"

# Check Ollama status
ollama-check:
	@curl -s http://localhost:11434/api/tags | python3 -m json.tool

# Check backend health
health:
	@curl -s http://localhost:8765/health | python3 -m json.tool

# Check account connections
accounts:
	@curl -s http://localhost:8765/api/accounts | python3 -m json.tool
