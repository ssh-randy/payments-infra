.PHONY: help test test-unit test-integration test-e2e test-all test-setup test-teardown test-parallel test-consistency

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

test-setup: ## Start test infrastructure (PostgreSQL + LocalStack)
	@echo "Starting test infrastructure..."
	@cd ../../infrastructure/docker && docker-compose up -d postgres
	@echo "Starting LocalStack without volume mounts (macOS compatibility)..."
	@docker rm -f payments-localstack 2>/dev/null || true
	@docker run -d --name payments-localstack \
		--network payments-network \
		-p 4566:4566 \
		-e SERVICES=sqs,kms,secretsmanager \
		-e DEBUG=1 \
		localstack/localstack:latest
	@echo "Waiting for services to be ready..."
	@sleep 8
	@echo "Checking LocalStack health..."
	@for i in 1 2 3 4 5; do \
		if curl -sf http://localhost:4566/_localstack/health >/dev/null 2>&1; then \
			echo "✓ LocalStack is healthy"; \
			break; \
		else \
			echo "Waiting for LocalStack... ($$i/5)"; \
			sleep 2; \
		fi; \
	done
	@echo "✓ Test infrastructure ready"

test-teardown: ## Stop test infrastructure
	@echo "Stopping test infrastructure..."
	@docker rm -f payments-localstack 2>/dev/null || true
	@cd ../../infrastructure/docker && docker-compose down
	@echo "✓ Test infrastructure stopped"

test-unit: ## Run unit tests only (no infrastructure needed)
	@echo "Running unit tests..."
	@poetry run pytest tests/unit -v

test-integration: test-setup ## Run integration tests (starts infrastructure automatically)
	@echo "Running integration tests..."
	@AWS_ENDPOINT_URL=http://localhost:4566 \
	 AWS_ACCESS_KEY_ID=test \
	 AWS_SECRET_ACCESS_KEY=test \
	 poetry run pytest tests/integration -v
	@$(MAKE) test-teardown

test-e2e: test-setup ## Run E2E tests (starts infrastructure automatically)
	@echo "Running E2E tests..."
	@AWS_ENDPOINT_URL=http://localhost:4566 \
	 AWS_ACCESS_KEY_ID=test \
	 AWS_SECRET_ACCESS_KEY=test \
	 poetry run pytest tests/e2e -v
	@$(MAKE) test-teardown

test-all: test-setup ## Run all tests (unit + integration + e2e)
	@echo "Running all tests..."
	@poetry run pytest tests/unit -v
	@AWS_ENDPOINT_URL=http://localhost:4566 \
	 AWS_ACCESS_KEY_ID=test \
	 AWS_SECRET_ACCESS_KEY=test \
	 poetry run pytest tests/integration tests/e2e -v
	@$(MAKE) test-teardown

test: test-all ## Alias for test-all (default target)

test-parallel: ## Run unit tests in parallel (fast)
	@echo "Running unit tests in parallel..."
	@poetry run pytest tests/unit -n auto

test-consistency: test-setup ## Run tests 3 times to verify consistency
	@echo "Running consistency check (3 consecutive runs)..."
	@for i in 1 2 3; do \
		echo "=== Run $$i/3 ==="; \
		AWS_ENDPOINT_URL=http://localhost:4566 \
		AWS_ACCESS_KEY_ID=test \
		AWS_SECRET_ACCESS_KEY=test \
		poetry run pytest tests/unit tests/integration -q || exit 1; \
	done
	@$(MAKE) test-teardown
	@echo "✓ All 3 runs passed"

install: ## Install dependencies
	@poetry install

lint: ## Run linting
	@poetry run ruff check src tests

format: ## Format code
	@poetry run black src tests
	@poetry run ruff check --fix src tests

typecheck: ## Run type checking
	@poetry run mypy src

clean: test-teardown ## Clean up test infrastructure and artifacts
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf htmlcov .coverage 2>/dev/null || true
	@echo "✓ Cleaned up"
