.PHONY: help setup proto install test lint format docker-up docker-down clean

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
NC := \033[0m # No Color

help: ## Show this help message
	@echo "$(BLUE)Available targets:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

setup: ## Initial setup (install dependencies and generate protos)
	@echo "$(BLUE)Setting up project...$(NC)"
	@echo "Installing shared packages..."
	cd shared/python/payments_proto && poetry install
	cd shared/python/payments_common && poetry install
	@echo "Installing services..."
	cd services/payment-token && poetry install
	cd services/authorization-api && poetry install
	cd services/auth-processor-worker && poetry install
	$(MAKE) proto
	@echo "$(GREEN)✓ Setup complete$(NC)"

proto: ## Generate protobuf code
	@echo "$(BLUE)Generating protobuf code...$(NC)"
	./scripts/generate_protos.sh

install: ## Install all dependencies
	@echo "$(BLUE)Installing dependencies...$(NC)"
	cd shared/python/payments_proto && poetry install
	cd shared/python/payments_common && poetry install
	cd services/payment-token && poetry install
	cd services/authorization-api && poetry install
	cd services/auth-processor-worker && poetry install

test: ## Run all tests
	@echo "$(BLUE)Running tests...$(NC)"
	cd services/payment-token && poetry run pytest
	cd services/authorization-api && poetry run pytest
	cd services/auth-processor-worker && poetry run pytest
	cd shared/python/payments_common && poetry run pytest

test-unit: ## Run unit tests only
	@echo "$(BLUE)Running unit tests...$(NC)"
	cd services/payment-token && poetry run pytest tests/unit
	cd services/authorization-api && poetry run pytest tests/unit
	cd services/auth-processor-worker && poetry run pytest tests/unit

test-integration: ## Run integration tests
	@echo "$(BLUE)Running integration tests...$(NC)"
	cd services/payment-token && poetry run pytest tests/integration
	cd services/authorization-api && poetry run pytest tests/integration
	cd services/auth-processor-worker && poetry run pytest tests/integration
	poetry run pytest tests/integration

test-e2e: ## Run end-to-end tests
	@echo "$(BLUE)Running e2e tests...$(NC)"
	poetry run pytest tests/e2e

lint: ## Run linters (ruff)
	@echo "$(BLUE)Running linters...$(NC)"
	cd services/payment-token && poetry run ruff check src
	cd services/authorization-api && poetry run ruff check src
	cd services/auth-processor-worker && poetry run ruff check src
	cd shared/python/payments_common && poetry run ruff check payments_common

format: ## Format code (black + ruff)
	@echo "$(BLUE)Formatting code...$(NC)"
	cd services/payment-token && poetry run black src tests && poetry run ruff check --fix src
	cd services/authorization-api && poetry run black src tests && poetry run ruff check --fix src
	cd services/auth-processor-worker && poetry run black src tests && poetry run ruff check --fix src
	cd shared/python/payments_common && poetry run black payments_common && poetry run ruff check --fix payments_common

typecheck: ## Run type checking (mypy)
	@echo "$(BLUE)Running type checks...$(NC)"
	cd services/payment-token && poetry run mypy src
	cd services/authorization-api && poetry run mypy src
	cd services/auth-processor-worker && poetry run mypy src

docker-up: ## Start local development environment (docker-compose)
	@echo "$(BLUE)Starting local environment...$(NC)"
	docker-compose -f infrastructure/docker/docker-compose.yml up -d
	@echo "$(GREEN)✓ Services started$(NC)"
	@echo "Waiting for services to be ready..."
	sleep 5
	./scripts/setup_local_db.sh

docker-down: ## Stop local development environment
	@echo "$(BLUE)Stopping local environment...$(NC)"
	docker-compose -f infrastructure/docker/docker-compose.yml down

docker-logs: ## View logs from docker-compose services
	docker-compose -f infrastructure/docker/docker-compose.yml logs -f

seed-data: ## Seed test data for local development
	@echo "$(BLUE)Seeding test data...$(NC)"
	./scripts/seed_test_data.py

clean: ## Clean generated files and caches
	@echo "$(BLUE)Cleaning generated files...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf shared/python/payments_proto/payments/v1/*_pb2.py
	rm -rf shared/python/payments_proto/payments/v1/*_pb2.pyi
	rm -rf shared/python/payments_proto/payments/v1/*_pb2_grpc.py
	@echo "$(GREEN)✓ Cleaned$(NC)"

ci: lint typecheck test ## Run all CI checks (lint, typecheck, test)
