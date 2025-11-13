"""Pytest configuration and shared fixtures for all tests.

This module provides shared test fixtures including:
- Test database setup with Alembic migrations
- Async database connection management
- Sample test data
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config

# Add src and shared to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(
    0, "/Users/randy/sudocodeai/demos/payments-infra/shared/python"
)
sys.path.insert(
    0, "/Users/randy/sudocodeai/demos/payments-infra/shared/python/payments_proto"
)


# Test database URL - use a separate test database
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:password@localhost:5432/payment_events_test",
)

# Set DATABASE_URL environment variable for the transaction functions to use
os.environ["DATABASE_URL"] = TEST_DATABASE_URL


def check_postgres_availability():
    """Check if PostgreSQL is available for integration tests."""
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 5432))
        sock.close()

        if result != 0:
            error_message = (
                "\n\n" + "="*80 + "\n"
                "ERROR: PostgreSQL is not running on localhost:5432\n"
                "="*80 + "\n\n"
                "  Start services with:\n"
                "    cd ../../infrastructure/docker\n"
                "    docker-compose up -d postgres\n\n"
                "="*80 + "\n"
            )
            pytest.exit(error_message, returncode=1)
    except Exception as e:
        pytest.exit(f"Failed to check PostgreSQL: {e}", returncode=1)


@pytest.fixture(scope="session", autouse=True)
def check_services_for_integration_tests(request):
    """Check service availability before running integration tests."""
    # Check if we're running integration tests
    integration_tests = False
    for item in request.session.items:
        if item.get_closest_marker("integration"):
            integration_tests = True
            break

    # Only check services if running integration tests
    if integration_tests:
        check_postgres_availability()


@pytest_asyncio.fixture(scope="session")
async def setup_test_database():
    """Set up test database with Alembic migrations.

    This fixture:
    1. Creates test database if it doesn't exist
    2. Runs Alembic migrations to set up schema
    3. Yields for tests
    4. Cleans up after all tests complete
    """
    # Parse database URL to get connection details
    parts = TEST_DATABASE_URL.replace("postgresql://", "").split("@")
    user_pass = parts[0].split(":")
    host_port_db = parts[1].split("/")
    host_port = host_port_db[0].split(":")

    user = user_pass[0]
    password = user_pass[1]
    host = host_port[0]
    port = host_port[1] if len(host_port) > 1 else "5432"
    dbname = host_port_db[1]

    # Connect to postgres database to create test database
    postgres_url = f"postgresql://{user}:{password}@{host}:{port}/postgres"

    try:
        conn = await asyncpg.connect(postgres_url)

        # Drop and recreate test database
        await conn.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
        await conn.execute(f'CREATE DATABASE "{dbname}"')

        await conn.close()
    except Exception as e:
        print(f"Warning: Could not recreate database: {e}")

    # Run Alembic migrations
    migrations_dir = Path(__file__).parent.parent.parent.parent / "infrastructure" / "migrations"
    alembic_cfg = Config(str(migrations_dir / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(migrations_dir / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    # Upgrade to head (create all tables)
    command.upgrade(alembic_cfg, "head")

    yield

    # Cleanup: drop database
    try:
        conn = await asyncpg.connect(postgres_url)
        await conn.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
        await conn.close()
    except Exception as e:
        print(f"Warning: Could not drop database: {e}")


@pytest_asyncio.fixture(scope="function")
async def db_pool(setup_test_database):
    """Create a database connection pool for each test.

    This fixture:
    1. Creates a connection pool
    2. Yields the pool for the test
    3. Closes the pool after the test
    """
    pool = await asyncpg.create_pool(
        dsn=TEST_DATABASE_URL,
        min_size=1,
        max_size=5,
        command_timeout=30.0,
    )

    yield pool

    await pool.close()


@pytest_asyncio.fixture
async def db_conn(db_pool):
    """Get a database connection for each test.

    This fixture:
    1. Acquires a connection from the pool
    2. Yields the connection for the test
    3. Cleans up all test data after the test
    """
    # Import here to avoid circular dependency
    from auth_processor_worker.infrastructure import database

    # Close any existing pool from transaction functions to avoid event loop issues
    await database.close_pool()

    conn = await db_pool.acquire()

    yield conn

    # Cleanup: delete all test data (but keep schema)
    await conn.execute("TRUNCATE auth_processing_locks CASCADE")
    await conn.execute("TRUNCATE auth_request_state CASCADE")
    await conn.execute("TRUNCATE payment_events CASCADE")

    await db_pool.release(conn)

    # Close the global pool again after test
    await database.close_pool()


@pytest.fixture
def test_auth_request_id():
    """Generate a unique auth request ID for each test."""
    return uuid.uuid4()


@pytest.fixture
def test_restaurant_id():
    """Standard test restaurant ID (valid UUID format)."""
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def test_payment_token():
    """Standard test payment token."""
    return "pt_test_12345678"


@pytest_asyncio.fixture
async def seed_auth_request(db_conn, test_auth_request_id, test_restaurant_id, test_payment_token):
    """Seed a basic auth request in the database for testing.

    This creates an auth_request_state record in PENDING status.
    """
    await db_conn.execute(
        """
        INSERT INTO auth_request_state (
            auth_request_id,
            restaurant_id,
            payment_token,
            status,
            amount_cents,
            currency,
            created_at,
            updated_at,
            last_event_sequence
        )
        VALUES ($1, $2, $3, 'PENDING', 1000, 'USD', NOW(), NOW(), 0)
        """,
        test_auth_request_id,
        test_restaurant_id,
        test_payment_token,
    )

    return test_auth_request_id


# ============================================================================
# Helper Functions for Integration Tests
# ============================================================================

@pytest_asyncio.fixture
async def write_void_event(db_conn):
    """
    Helper fixture to write an AuthVoidRequested event for testing race conditions.

    Usage:
        async def test_void_race(write_void_event, test_auth_request_id):
            await write_void_event(test_auth_request_id)
            # Now worker should detect void and expire the request

    Returns:
        Callable: Async function to write void event
    """
    from datetime import datetime
    from payments_proto.payments.v1 import events_pb2

    async def _write_void_event(
        auth_request_id: uuid.UUID,
        reason: str = "Customer requested cancellation",
    ) -> int:
        """
        Write an AuthVoidRequested event to the event store.

        Args:
            auth_request_id: Authorization request ID
            reason: Reason for void request

        Returns:
            int: Sequence number of the created event
        """
        # Create the void event protobuf
        event_data = events_pb2.AuthVoidRequested(
            auth_request_id=str(auth_request_id),
            reason=reason,
            requested_at=int(datetime.utcnow().timestamp()),
        )

        # Insert into payment_events
        result = await db_conn.fetchrow(
            """
            INSERT INTO payment_events (
                aggregate_id,
                aggregate_type,
                event_type,
                event_data,
                metadata,
                sequence_number
            )
            VALUES ($1, 'AuthRequest', 'AuthVoidRequested', $2, $3,
                    COALESCE((SELECT MAX(sequence_number) FROM payment_events WHERE aggregate_id = $1), 0) + 1)
            RETURNING sequence_number
            """,
            auth_request_id,
            event_data.SerializeToString(),
            {"test": "void_event"},
        )

        return result["sequence_number"]

    return _write_void_event


@pytest_asyncio.fixture
async def get_events_for_auth_request(db_conn):
    """
    Helper fixture to retrieve all events for an auth request.

    Usage:
        async def test_something(get_events_for_auth_request, test_auth_request_id):
            events = await get_events_for_auth_request(test_auth_request_id)
            assert len(events) == 3

    Returns:
        Callable: Async function to get events
    """
    async def _get_events(auth_request_id: uuid.UUID) -> list[asyncpg.Record]:
        """
        Get all events for an auth request, ordered by sequence.

        Args:
            auth_request_id: Authorization request ID

        Returns:
            list: List of event records
        """
        return await db_conn.fetch(
            """
            SELECT
                event_id,
                aggregate_id,
                event_type,
                event_data,
                metadata,
                sequence_number,
                created_at
            FROM payment_events
            WHERE aggregate_id = $1
            ORDER BY sequence_number ASC
            """,
            auth_request_id,
        )

    return _get_events


@pytest_asyncio.fixture
async def get_auth_request_state(db_conn):
    """
    Helper fixture to retrieve auth request state from read model.

    Usage:
        async def test_something(get_auth_request_state, test_auth_request_id):
            state = await get_auth_request_state(test_auth_request_id)
            assert state["status"] == "AUTHORIZED"

    Returns:
        Callable: Async function to get auth request state
    """
    async def _get_state(auth_request_id: uuid.UUID) -> asyncpg.Record | None:
        """
        Get auth request state from read model.

        Args:
            auth_request_id: Authorization request ID

        Returns:
            asyncpg.Record: Auth request state record or None
        """
        return await db_conn.fetchrow(
            """
            SELECT *
            FROM auth_request_state
            WHERE auth_request_id = $1
            """,
            auth_request_id,
        )

    return _get_state


@pytest_asyncio.fixture
async def seed_restaurant_config(db_conn):
    """
    Helper fixture to seed custom restaurant payment configurations.

    Usage:
        async def test_something(seed_restaurant_config):
            restaurant_id = await seed_restaurant_config(
                processor_name="mock",
                processor_config={"default_response": "declined"},
            )

    Returns:
        Callable: Async function to seed restaurant config
    """
    async def _seed_config(
        restaurant_id: uuid.UUID | None = None,
        processor_name: str = "mock",
        processor_config: dict | None = None,
        config_version: str = "v1",
        is_active: bool = True,
    ) -> uuid.UUID:
        """
        Seed a restaurant payment configuration.

        Args:
            restaurant_id: Restaurant ID (auto-generated if None)
            processor_name: Processor name (stripe, mock, etc.)
            processor_config: Processor configuration dict
            config_version: Config version string
            is_active: Whether config is active

        Returns:
            uuid.UUID: The restaurant ID
        """
        if restaurant_id is None:
            restaurant_id = uuid.uuid4()

        if processor_config is None:
            processor_config = {}

        # Insert or update the config
        await db_conn.execute(
            """
            INSERT INTO restaurant_payment_configs (
                restaurant_id,
                config_version,
                processor_name,
                processor_config,
                is_active
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (restaurant_id)
            DO UPDATE SET
                config_version = EXCLUDED.config_version,
                processor_name = EXCLUDED.processor_name,
                processor_config = EXCLUDED.processor_config,
                is_active = EXCLUDED.is_active,
                updated_at = NOW()
            """,
            restaurant_id,
            config_version,
            processor_name,
            processor_config,
            is_active,
        )

        return restaurant_id

    return _seed_config


@pytest_asyncio.fixture
async def get_processing_lock(db_conn):
    """
    Helper fixture to check if a processing lock exists.

    Usage:
        async def test_something(get_processing_lock, test_auth_request_id):
            lock = await get_processing_lock(test_auth_request_id)
            assert lock is not None
            assert lock["worker_id"] == "test-worker-123"

    Returns:
        Callable: Async function to get lock info
    """
    async def _get_lock(auth_request_id: uuid.UUID) -> asyncpg.Record | None:
        """
        Get processing lock information.

        Args:
            auth_request_id: Authorization request ID

        Returns:
            asyncpg.Record: Lock record or None if no lock exists
        """
        return await db_conn.fetchrow(
            """
            SELECT
                auth_request_id,
                worker_id,
                locked_at,
                expires_at
            FROM auth_processing_locks
            WHERE auth_request_id = $1
            """,
            auth_request_id,
        )

    return _get_lock


@pytest_asyncio.fixture
async def count_events_by_type(db_conn):
    """
    Helper fixture to count events by type for an auth request.

    Usage:
        async def test_something(count_events_by_type, test_auth_request_id):
            counts = await count_events_by_type(test_auth_request_id)
            assert counts["AuthAttemptStarted"] == 1
            assert counts["AuthResponseReceived"] == 1

    Returns:
        Callable: Async function to count events
    """
    async def _count_events(auth_request_id: uuid.UUID) -> dict[str, int]:
        """
        Count events by type for an auth request.

        Args:
            auth_request_id: Authorization request ID

        Returns:
            dict: Mapping of event_type to count
        """
        rows = await db_conn.fetch(
            """
            SELECT event_type, COUNT(*) as count
            FROM payment_events
            WHERE aggregate_id = $1
            GROUP BY event_type
            """,
            auth_request_id,
        )

        return {row["event_type"]: row["count"] for row in rows}

    return _count_events
