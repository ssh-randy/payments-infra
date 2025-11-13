"""Unit tests for configuration management."""

import os
from unittest.mock import patch

import pytest

from authorization_api.config import Settings


def test_settings_default_values():
    """Test that Settings loads with default values."""
    # Save existing env vars
    saved_db_url = os.environ.get("DATABASE_URL")
    saved_test_db_url = os.environ.get("TEST_DATABASE_URL")

    try:
        # Clear DATABASE_URL to test true defaults
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("TEST_DATABASE_URL", None)

        settings = Settings()

        assert settings.database_url == "postgresql://postgres:password@localhost:5432/payment_events_db"
        assert settings.database_pool_min_size == 10
        assert settings.database_pool_max_size == 20
        assert settings.aws_region == "us-east-1"
        assert settings.log_level == "INFO"
        assert settings.environment == "development"
        assert settings.service_name == "authorization-api"
        assert settings.outbox_processor_enabled is True
        assert settings.outbox_processor_interval_ms == 100
        assert settings.outbox_processor_batch_size == 100
    finally:
        # Restore env vars
        if saved_db_url:
            os.environ["DATABASE_URL"] = saved_db_url
        if saved_test_db_url:
            os.environ["TEST_DATABASE_URL"] = saved_test_db_url


def test_settings_from_environment():
    """Test that Settings can be overridden by environment variables."""
    env_vars = {
        "DATABASE_URL": "postgresql://testuser:testpass@testhost:5432/testdb",
        "LOG_LEVEL": "DEBUG",
        "ENVIRONMENT": "test",
        "OUTBOX_PROCESSOR_ENABLED": "false",
    }

    with patch.dict(os.environ, env_vars, clear=False):
        settings = Settings()

        assert settings.database_url == "postgresql://testuser:testpass@testhost:5432/testdb"
        assert settings.log_level == "DEBUG"
        assert settings.environment == "test"
        assert settings.outbox_processor_enabled is False


def test_settings_aws_configuration():
    """Test AWS configuration settings."""
    env_vars = {
        "AWS_REGION": "us-west-2",
        "AWS_ENDPOINT_URL": "http://localhost:4566",
        "AWS_ACCESS_KEY_ID": "test_key",
        "AWS_SECRET_ACCESS_KEY": "test_secret",
    }

    with patch.dict(os.environ, env_vars, clear=False):
        settings = Settings()

        assert settings.aws_region == "us-west-2"
        assert settings.aws_endpoint_url == "http://localhost:4566"
        assert settings.aws_access_key_id == "test_key"
        assert settings.aws_secret_access_key == "test_secret"


def test_settings_queue_urls():
    """Test SQS queue URL configuration."""
    settings = Settings()

    assert "auth-requests.fifo" in settings.auth_requests_queue_url
    assert "void-requests" in settings.void_requests_queue_url
