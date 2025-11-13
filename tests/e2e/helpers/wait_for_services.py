"""Helper functions for waiting on service health checks."""

import time
from typing import Optional

import httpx


def wait_for_service(
    url: str,
    timeout: int = 60,
    interval: float = 1.0,
    expected_status: int = 200,
) -> None:
    """Wait for a service to be healthy.

    Args:
        url: The health check URL to poll
        timeout: Maximum time to wait in seconds
        interval: Time between checks in seconds
        expected_status: Expected HTTP status code for healthy service

    Raises:
        TimeoutError: If service does not become healthy within timeout
    """
    start = time.time()
    last_error: Optional[Exception] = None

    while time.time() - start < timeout:
        try:
            response = httpx.get(url, timeout=5.0)
            if response.status_code == expected_status:
                print(f"✓ Service at {url} is healthy")
                return
            last_error = Exception(f"Unexpected status code: {response.status_code}")
        except Exception as e:
            last_error = e

        time.sleep(interval)

    error_msg = f"Service at {url} not healthy after {timeout}s"
    if last_error:
        error_msg += f": {last_error}"
    raise TimeoutError(error_msg)


def wait_for_all_services(
    services: dict[str, str],
    timeout: int = 60,
    interval: float = 1.0,
) -> None:
    """Wait for multiple services to be healthy.

    Args:
        services: Dict mapping service names to health check URLs
        timeout: Maximum time to wait for each service
        interval: Time between checks

    Raises:
        TimeoutError: If any service does not become healthy
    """
    for service_name, health_url in services.items():
        print(f"Waiting for {service_name}...")
        wait_for_service(health_url, timeout=timeout, interval=interval)
