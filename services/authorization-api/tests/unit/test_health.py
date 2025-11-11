"""Unit tests for health check endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_pool():
    """Mock database connection pool."""
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetchval = AsyncMock(return_value=1)
    pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock()))
    return pool


@pytest.mark.asyncio
async def test_health_check_success(mock_pool):
    """Test health check returns 200 when database is healthy."""
    with patch("authorization_api.api.main.get_pool", return_value=mock_pool):
        from authorization_api.api.main import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert response.json()["service"] == "authorization-api"
        assert "environment" in response.json()


@pytest.mark.asyncio
async def test_health_check_database_failure():
    """Test health check returns 503 when database connection fails."""
    mock_pool_error = MagicMock()
    mock_pool_error.acquire.side_effect = Exception("Database connection failed")

    with patch("authorization_api.api.main.get_pool", return_value=mock_pool_error):
        from authorization_api.api.main import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 503
        assert response.json()["status"] == "unhealthy"
        assert "error" in response.json()


def test_root_endpoint():
    """Test root endpoint returns service information."""
    # Import without lifespan to avoid database connection
    from authorization_api.api.main import root
    import asyncio

    result = asyncio.run(root())

    assert result["service"] == "Authorization API"
    assert result["version"] == "0.1.0"
    assert result["status"] == "running"
