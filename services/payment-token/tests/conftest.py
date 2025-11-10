"""Pytest configuration and shared fixtures for all tests.

This module provides shared test fixtures including:
- Test database setup with Alembic migrations
- Database session management
- Sample test data
"""

import os
import sys
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, "/Users/randy/sudocodeai/demos/payments-infra/shared/python")
sys.path.insert(0, "/Users/randy/sudocodeai/demos/payments-infra/shared/python/payments_proto")

from payment_token.infrastructure.database import Base


# Test database URL - use a separate test database
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/payment_tokens_test",
)


@pytest.fixture(scope="session")
def db_engine():
    """Create a test database engine and apply migrations.

    This fixture:
    1. Creates a test database engine
    2. Runs Alembic migrations to set up schema
    3. Yields the engine for tests
    4. Cleans up after all tests complete
    """
    # Create engine
    engine = create_engine(TEST_DATABASE_URL, echo=False)

    # Set PostgreSQL settings
    @event.listens_for(engine, "connect")
    def set_postgresql_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("SET timezone='UTC'")
        cursor.close()

    # Run Alembic migrations to create schema
    alembic_cfg = Config()
    alembic_cfg.set_main_option(
        "script_location",
        str(Path(__file__).parent.parent / "alembic"),
    )
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    # Set the connection for Alembic to use
    with engine.begin() as connection:
        alembic_cfg.attributes["connection"] = connection

        # Downgrade to base (clean slate)
        try:
            command.downgrade(alembic_cfg, "base")
        except Exception:
            # Tables might not exist yet, that's okay
            pass

        # Upgrade to head (create all tables)
        command.upgrade(alembic_cfg, "head")

    yield engine

    # Cleanup: drop all tables
    with engine.begin() as connection:
        alembic_cfg.attributes["connection"] = connection
        command.downgrade(alembic_cfg, "base")

    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """Create a fresh database session for each test.

    This fixture:
    1. Creates a new database session
    2. Begins a transaction
    3. Yields the session for the test
    4. Rolls back the transaction after the test (cleanup)
    """
    connection = db_engine.connect()
    transaction = connection.begin()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = TestingSessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def service_key():
    """Generate a test service encryption key (32 bytes for AES-256)."""
    return b"0" * 32


@pytest.fixture
def test_restaurant_id():
    """Standard test restaurant ID (valid UUID format)."""
    return "12345678-1234-1234-1234-123456789abc"


@pytest.fixture
def test_device_token():
    """Standard test device token."""
    return "device_test_456"
