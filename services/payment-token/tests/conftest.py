"""Pytest configuration and shared fixtures for all tests.

This module provides shared test fixtures including:
- Test database setup with Alembic migrations
- Database session management
- Sample test data
- Service availability checks for integration tests
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
    "postgresql://postgres:password@localhost:5433/payment_tokens_test",
)


def check_service_availability():
    """Check if required services for integration tests are available.

    This function checks:
    - PostgreSQL is running and accessible on port 5433 (postgres-tokens)
    - LocalStack is running (for KMS integration tests)

    If services are not available, it provides helpful error messages.
    """
    import socket

    errors = []

    # Check PostgreSQL on port 5433 (postgres-tokens container)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 5433))
        sock.close()

        if result != 0:
            errors.append(
                "PostgreSQL is not running on localhost:5433\n"
                "  Start services with:\n"
                "    cd ../../infrastructure/docker\n"
                "    docker-compose up -d postgres-tokens localstack"
            )
    except Exception as e:
        errors.append(f"Failed to check PostgreSQL: {e}")

    # Check LocalStack (for KMS)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 4566))
        sock.close()

        if result != 0:
            errors.append(
                "LocalStack is not running on localhost:4566\n"
                "  This is required for integration tests that use KMS.\n"
                "  Start services with:\n"
                "    cd ../../infrastructure/docker\n"
                "    docker-compose up -d postgres-tokens localstack"
            )
    except Exception as e:
        errors.append(f"Failed to check LocalStack: {e}")

    if errors:
        error_message = "\n\n" + "="*80 + "\n"
        error_message += "ERROR: Required services are not available for integration tests\n"
        error_message += "="*80 + "\n\n"
        error_message += "\n\n".join(errors)
        error_message += "\n\n" + "="*80 + "\n"
        error_message += "See tests/README.md for more details on running integration tests.\n"
        error_message += "="*80 + "\n"
        pytest.exit(error_message, returncode=1)


@pytest.fixture(scope="session", autouse=True)
def check_services_for_integration_tests(request):
    """Check service availability before running tests.

    This fixture runs automatically for all test sessions.

    Note:
    - Integration tests are self-contained (use SQLite + mocked KMS)
      and don't require external services.
    - E2E tests manage their own Docker infrastructure via docker_services fixture,
      so we skip the check for them.
    """
    # Don't run service checks - let each test type handle its own infrastructure:
    # - Unit tests: no external services needed
    # - Integration tests: use SQLite + mocked KMS (no external services)
    # - E2E tests: manage their own docker-compose infrastructure
    pass


def ensure_test_database_exists():
    """Ensure the test database exists before running migrations.

    This function:
    1. Connects to the default postgres database
    2. Creates the test database if it doesn't exist
    """
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    # Parse database URL to get connection details
    # postgresql://user:password@host:port/dbname
    parts = TEST_DATABASE_URL.replace("postgresql://", "").split("@")
    user_pass = parts[0].split(":")
    host_port_db = parts[1].split("/")
    host_port = host_port_db[0].split(":")

    user = user_pass[0]
    password = user_pass[1] if len(user_pass) > 1 else ""
    host = host_port[0]
    port = int(host_port[1]) if len(host_port) > 1 else 5432
    dbname = host_port_db[1]

    # Connect to postgres database to check/create test database
    try:
        conn = psycopg2.connect(
            dbname="postgres",
            user=user,
            password=password,
            host=host,
            port=port,
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        # Check if database exists
        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (dbname,)
        )
        exists = cursor.fetchone()

        if not exists:
            print(f"Creating test database: {dbname}")
            cursor.execute(f'CREATE DATABASE "{dbname}"')

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Warning: Could not create test database: {e}")
        # Continue anyway - migrations might handle it


@pytest.fixture(scope="session")
def db_engine():
    """Create a test database engine and apply migrations.

    This fixture:
    1. Ensures test database exists
    2. Creates a test database engine
    3. Runs Alembic migrations to set up schema
    4. Yields the engine for tests
    5. Cleans up after all tests complete
    """
    # Ensure test database exists
    ensure_test_database_exists()

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
