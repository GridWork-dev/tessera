# Lumen Edge Media Catalog — Development
.PHONY: dev backend frontend install build audit

# Start both backend + frontend
dev:
	@echo "▸ Starting Lumen Edge..."
	@echo "  Backend  → http://localhost:8000"
	@echo "  Frontend → http://localhost:5173"
	@trap 'kill 0' SIGINT; \
		cd frontend && npm run dev & \
		source venv/bin/activate && cd webui && python main.py & \
		wait

# Backend only
backend:
	@echo "▸ Starting FastAPI backend on :8000"
	source venv/bin/activate && cd webui && python main.py

# Frontend only
frontend:
	@echo "▸ Starting Vite frontend on :5173"
	cd frontend && npm run dev

# Install all dependencies
install:
	cd frontend && npm install
	python -m pip install -r frontend/../requirements.txt 2>/dev/null || true

# Build frontend for production (FastAPI serves dist/)
build:
	cd frontend && npm run build
	@echo "▸ Frontend built to frontend/dist/"

# Live visual audit — build, preview, screenshot routes (mocked, no backend)
audit:
	cd frontend && npm run audit
