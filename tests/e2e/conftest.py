"""Pytest configuration for E2E tests with Docker containers."""

import sys
from pathlib import Path

# Ensure fixtures and helpers are importable
sys.path.insert(0, str(Path(__file__).parent))

# Import all fixtures so they're available to tests
from fixtures.docker_fixtures import *  # noqa: F401, F403
