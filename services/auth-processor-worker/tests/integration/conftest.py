"""Integration test configuration and fixture imports.

This module imports all fixtures needed for integration tests and configures
the test environment for end-to-end testing.

IMPORTANT: Integration tests should be run serially (not in parallel) because:
- They use a shared LocalStack SQS queue
- They test with real PostgreSQL database
- Worker instances manage global state

Run integration tests with:
    pytest tests/integration -v

Do NOT use -n flag (pytest-xdist parallel execution).
"""

import uuid

import pytest
import pytest_asyncio


# Import all integration test fixtures
pytest_plugins = [
    "tests.integration.fixtures.sqs_fixtures",
    "tests.integration.fixtures.token_fixtures",
    "tests.integration.fixtures.worker_fixtures",
]


def pytest_configure(config):
    """Configure pytest for integration tests."""
    # Add markers
    config.addinivalue_line(
        "markers",
        "e2e: end-to-end integration tests that test full worker flow"
    )
    config.addinivalue_line(
        "markers",
        "serial: tests that must run serially (no parallel execution)"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark all integration tests as serial and integration."""
    for item in items:
        # If test is in integration directory, mark it
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.serial)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def setup_mock_processor_config(db_conn, test_restaurant_id):
    """
    Automatically configure the test restaurant to use 'mock' processor.

    This fixture runs before every integration test to ensure the restaurant
    config uses MockProcessor instead of the default Stripe processor.

    This is autouse=True so it applies to all integration tests automatically.
    """
    # Update the test restaurant to use mock processor
    await db_conn.execute(
        """
        INSERT INTO restaurant_payment_configs (
            restaurant_id,
            config_version,
            processor_name,
            processor_config,
            is_active
        )
        VALUES ($1, 'v1', 'mock', '{}', true)
        ON CONFLICT (restaurant_id)
        DO UPDATE SET
            processor_name = 'mock',
            processor_config = '{}',
            is_active = true,
            updated_at = NOW()
        """,
        test_restaurant_id,
    )
