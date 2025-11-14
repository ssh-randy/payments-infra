"""Docker Compose fixtures for E2E tests."""

import subprocess
import time
from pathlib import Path
from typing import Generator

import sys
from pathlib import Path

import pytest

# Add e2e directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.wait_for_services import wait_for_all_services


def setup_test_restaurant_config(restaurant_id: str) -> None:
    """Set up test restaurant configuration in the database.

    Args:
        restaurant_id: Restaurant UUID to configure
    """
    print(f"Setting up test restaurant configuration for {restaurant_id}...")

    # Insert restaurant config directly into database
    result = subprocess.run(
        [
            "docker", "exec", "payments-postgres",
            "psql", "-U", "postgres", "-d", "payment_events_e2e",
            "-c",
            f"""
            INSERT INTO restaurant_payment_configs
                (restaurant_id, config_version, processor_name, processor_config, is_active)
            VALUES
                ('{restaurant_id}'::UUID, 'v1', 'mock', '{{}}'::JSONB, true)
            ON CONFLICT (restaurant_id)
            DO UPDATE SET
                processor_name = 'mock',
                processor_config = '{{}}'::JSONB,
                is_active = true;
            """
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Failed to set up restaurant config: {result.stderr}")
        raise RuntimeError(f"Failed to set up test restaurant configuration: {result.stderr}")

    print(f"✓ Test restaurant configuration created for {restaurant_id}")


# Path to docker-compose file
DOCKER_COMPOSE_FILE = Path(__file__).parents[3] / "infrastructure" / "docker" / "docker-compose.e2e.yml"


@pytest.fixture(scope="session")
def docker_compose_file() -> Path:
    """Get the path to the docker-compose file.

    Returns:
        Path to docker-compose.e2e.yml
    """
    return DOCKER_COMPOSE_FILE


@pytest.fixture(scope="session")
def docker_services(docker_compose_file: Path) -> Generator[None, None, None]:
    """Start all services via docker-compose.

    This fixture:
    1. Cleans up any existing containers from previous runs
    2. Starts all services defined in docker-compose.e2e.yml
    3. Waits for services to be healthy
    4. Yields control to tests
    5. Cleans up by stopping and removing containers

    Yields:
        None (services are available at their exposed ports)
    """
    print("\n" + "=" * 80)
    print("Starting Docker services for E2E tests...")
    print("=" * 80)

    # Check if Docker is running
    docker_check = subprocess.run(
        ["docker", "info"],
        check=False,
        capture_output=True,
        text=True,
    )
    if docker_check.returncode != 0:
        raise RuntimeError(
            "Docker is not running. Please start Docker Desktop and try again.\n"
            f"Error: {docker_check.stderr}"
        )

    # Clean up any existing containers from previous runs
    print("Cleaning up any existing E2E test containers...")

    # First, use docker-compose down to clean up containers from the compose file
    subprocess.run(
        ["docker-compose", "-f", str(docker_compose_file), "down", "-v"],
        check=False,
        capture_output=True,
        text=True,
    )

    # Also explicitly remove any containers with conflicting names
    # (in case they were created outside of docker-compose)
    container_names = [
        "payments-localstack",
        "payments-postgres",
        "payments-postgres-tokens",
        "authorization-api",
        "payment-token",
        "auth-processor-worker",
    ]
    for container_name in container_names:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            check=False,
            capture_output=True,
            text=True,
        )

    print("Cleanup complete.")

    # Start services
    try:
        subprocess.run(
            [
                "docker-compose",
                "-f",
                str(docker_compose_file),
                "up",
                "-d",
                "--build",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Failed to start Docker services: {e.stderr}")
        raise

    # Wait a bit for containers to initialize
    time.sleep(5)

    # Wait for services to be healthy
    services = {
        "Authorization API": "http://localhost:8000/health",
        "Payment Token Service": "http://localhost:8001/health",
    }

    try:
        wait_for_all_services(services, timeout=60, interval=2.0)
    except TimeoutError as e:
        # If health checks fail, show logs and cleanup
        print("\n" + "=" * 80)
        print("Service health checks failed. Showing logs:")
        print("=" * 80)
        subprocess.run(
            ["docker-compose", "-f", str(docker_compose_file), "logs"],
            check=False,
        )
        # Cleanup
        subprocess.run(
            ["docker-compose", "-f", str(docker_compose_file), "down", "-v"],
            check=False,
        )
        raise e

    print("\n" + "=" * 80)
    print("All services are healthy and ready for testing!")
    print("=" * 80 + "\n")

    # Set up test restaurant configuration
    # This is done here instead of in a migration to avoid polluting production data
    setup_test_restaurant_config("12345678-1234-5678-1234-567812345678")

    yield

    # Cleanup
    print("\n" + "=" * 80)
    print("Stopping Docker services...")
    print("=" * 80)

    subprocess.run(
        ["docker-compose", "-f", str(docker_compose_file), "down", "-v"],
        check=False,
    )

    print("Docker services stopped and cleaned up.\n")


@pytest.fixture(scope="session")
def authorization_api_url(docker_services: None) -> str:
    """Get the Authorization API URL.

    Args:
        docker_services: Ensures Docker services are running

    Returns:
        Base URL for Authorization API
    """
    return "http://localhost:8000"


@pytest.fixture(scope="session")
def payment_token_service_url(docker_services: None) -> str:
    """Get the Payment Token Service URL.

    Args:
        docker_services: Ensures Docker services are running

    Returns:
        Base URL for Payment Token Service
    """
    return "http://localhost:8001"
