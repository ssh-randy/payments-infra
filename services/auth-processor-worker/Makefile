.PHONY: help test test-unit test-integration test-all test-external test-all-external test-parallel test-setup test-teardown

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ''
	@echo 'Note: By default, tests exclude external APIs (Stripe, etc.)'
	@echo '      Use test-external or test-all-external to include them.'

test-setup: ## Start test infrastructure (PostgreSQL + LocalStack)
	@echo "Starting test infrastructure..."
	@cd ../../infrastructure/docker && docker-compose up -d postgres localstack
	@echo "Waiting for services to be ready..."
	@sleep 5
	@echo "✓ Test infrastructure ready"

test-teardown: ## Stop test infrastructure
	@echo "Stopping test infrastructure..."
	@cd ../../infrastructure/docker && docker-compose down
	@echo "✓ Test infrastructure stopped"

test-unit: ## Run unit tests only (no infrastructure, excludes external)
	@echo "Running unit tests (excluding external APIs)..."
	@poetry run pytest tests/unit -v -m "not external"

test-integration: test-setup ## Run integration tests (excludes external APIs)
	@echo "Running integration tests (excluding external APIs)..."
	@AWS_ENDPOINT_URL=http://localhost:4566 \
	 AWS_ACCESS_KEY_ID=test \
	 AWS_SECRET_ACCESS_KEY=test \
	 poetry run pytest tests/integration -v -m "not external"
	@$(MAKE) test-teardown

test-all: test-setup ## Run all tests (unit + integration, excludes external)
	@echo "Running all tests (excluding external APIs)..."
	@poetry run pytest tests/unit -v -m "not external"
	@AWS_ENDPOINT_URL=http://localhost:4566 \
	 AWS_ACCESS_KEY_ID=test \
	 AWS_SECRET_ACCESS_KEY=test \
	 poetry run pytest tests/integration -v -m "not external"
	@$(MAKE) test-teardown

test-external: test-setup ## Run ONLY external API tests (requires STRIPE_TEST_API_KEY)
	@echo "Running external API tests (Stripe, etc.)..."
	@if [ -z "$$STRIPE_TEST_API_KEY" ]; then \
		echo "⚠️  Warning: STRIPE_TEST_API_KEY not set, tests may be skipped"; \
	fi
	@AWS_ENDPOINT_URL=http://localhost:4566 \
	 AWS_ACCESS_KEY_ID=test \
	 AWS_SECRET_ACCESS_KEY=test \
	 poetry run pytest tests/integration -v -m "external"
	@$(MAKE) test-teardown

test-all-external: test-setup ## Run ALL tests including external APIs (requires STRIPE_TEST_API_KEY)
	@echo "Running all tests INCLUDING external APIs..."
	@if [ -z "$$STRIPE_TEST_API_KEY" ]; then \
		echo "⚠️  Warning: STRIPE_TEST_API_KEY not set, external tests may be skipped"; \
	fi
	@poetry run pytest tests/unit -v
	@AWS_ENDPOINT_URL=http://localhost:4566 \
	 AWS_ACCESS_KEY_ID=test \
	 AWS_SECRET_ACCESS_KEY=test \
	 poetry run pytest tests/integration -v
	@$(MAKE) test-teardown

test: test-all ## Alias for test-all (default target, excludes external)

test-parallel: ## Run unit tests in parallel (fast, excludes external)
	@echo "Running unit tests in parallel (excluding external APIs)..."
	@poetry run pytest tests/unit -n auto -m "not external"

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
