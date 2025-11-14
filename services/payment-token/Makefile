.PHONY: help test test-unit test-integration test-e2e test-all test-setup test-teardown

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

test-setup: ## Start test infrastructure (PostgreSQL + LocalStack)
	@echo "Starting test infrastructure..."
	@docker-compose -f docker-compose.integration.yml up -d
	@echo "Waiting for services to be ready..."
	@sleep 3
	@echo "✓ Test infrastructure ready"

test-teardown: ## Stop test infrastructure
	@echo "Stopping test infrastructure..."
	@docker-compose -f docker-compose.integration.yml down
	@echo "✓ Test infrastructure stopped"

test-unit: ## Run unit tests only (no infrastructure needed)
	@echo "Running unit tests..."
	@poetry run pytest tests/unit -v

test-integration: test-setup ## Run integration tests (starts infrastructure automatically)
	@echo "Running integration tests..."
	@TEST_DATABASE_URL="postgresql://postgres:password@localhost:5433/payment_tokens_test" \
	 AWS_ENDPOINT_URL=http://localhost:4566 \
	 AWS_ACCESS_KEY_ID=test \
	 AWS_SECRET_ACCESS_KEY=test \
	 AWS_REGION=us-east-1 \
	 poetry run pytest tests/integration -v
	@$(MAKE) test-teardown

test-e2e: test-setup ## Run E2E tests (starts infrastructure automatically)
	@echo "Running E2E tests..."
	@TEST_DATABASE_URL="postgresql://postgres:password@localhost:5433/payment_tokens_test" \
	 AWS_ENDPOINT_URL=http://localhost:4566 \
	 AWS_ACCESS_KEY_ID=test \
	 AWS_SECRET_ACCESS_KEY=test \
	 AWS_REGION=us-east-1 \
	 poetry run pytest tests/e2e -v
	@$(MAKE) test-teardown

test-all: test-setup ## Run all tests (unit + integration + e2e)
	@echo "Running all tests..."
	@poetry run pytest tests/unit -v
	@TEST_DATABASE_URL="postgresql://postgres:password@localhost:5433/payment_tokens_test" \
	 AWS_ENDPOINT_URL=http://localhost:4566 \
	 AWS_ACCESS_KEY_ID=test \
	 AWS_SECRET_ACCESS_KEY=test \
	 AWS_REGION=us-east-1 \
	 poetry run pytest tests/integration tests/e2e -v
	@$(MAKE) test-teardown

test: test-all ## Alias for test-all (default target)

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
	@echo "✓ Cleaned up"
