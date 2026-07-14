# =============================================================================
# Enterprise AI Control Plane — Makefile
# =============================================================================
# Usage:
#   make up        — Start the full stack with docker compose
#   make down      — Stop all containers
#   make build     — Build all Docker images
#   make test      — Run all tests
#   make lint      — Run linters (ruff)
#   make typecheck — Run type checker (mypy)
# =============================================================================

.PHONY: up down build test lint typecheck clean setup

# Default target
all: up

# ── Docker Compose ──────────────────────────────────────────────────────────

up:
	@echo "Starting the full AI Control Plane stack..."
	docker compose up -d
	@echo "Stack started. Services available at:"
	@echo "  Control Plane:   http://localhost:8000"
	@echo "  Agent Runtime:   http://localhost:8001"
	@echo "  Tool Gateway:    http://localhost:8002"
	@echo "  CRM Service:     http://localhost:8003"
	@echo "  Ticketing:       http://localhost:8004"
	@echo "  Notification:    http://localhost:8005"
	@echo "  Prometheus:      http://localhost:9090"
	@echo "  Grafana:         http://localhost:3000 (admin/admin)"
	@echo "  Jaeger:          http://localhost:16686"
	@echo "  OpenSearch:      http://localhost:9200"
	@echo "  OpenSearch Dash: http://localhost:5601"

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

restart:
	docker compose restart

# ── Setup ───────────────────────────────────────────────────────────────────

setup:
	@echo "Setting up Python virtual environment..."
	python3.11 -m venv .venv
	. .venv/bin/activate && \
		pip install -e 'libs/shared_schemas[dev]' && \
		pip install -r services/control-plane/requirements.txt && \
		pip install -r services/agent-runtime/requirements.txt && \
		pip install -r services/tool-gateway/requirements.txt && \
		pip install ruff mypy pytest pytest-asyncio httpx
	@echo "Setup complete. Activate with: source .venv/bin/activate"

# ── Testing ─────────────────────────────────────────────────────────────────

test: test-shared test-control-plane

test-shared:
	cd libs/shared_schemas && python -m pytest -v

test-control-plane:
	cd services/control-plane && python -m pytest -v

test-agent-runtime:
	cd services/agent-runtime && python -m pytest -v

test-tool-gateway:
	cd services/tool-gateway && python -m pytest -v

test-all: test-shared test-control-plane test-agent-runtime test-tool-gateway

# ── Linting & Type Checking ─────────────────────────────────────────────────

lint:
	ruff check libs/shared_schemas/ services/control-plane/ services/agent-runtime/ services/tool-gateway/ backend-systems/

typecheck:
	mypy libs/shared_schemas/ services/control-plane/ --ignore-missing-imports

# ── Cleanup ─────────────────────────────────────────────────────────────────

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .venv
	@echo "Cleanup complete."
