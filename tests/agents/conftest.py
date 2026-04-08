"""Pytest configuration for agent tests.

Loads .env file and provides fixtures for Claude Agent SDK usage.
"""

import os
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from dotenv import load_dotenv


def pytest_configure(config):
    """Load .env file and set up sys.path before running tests."""
    # Add repo root to sys.path for importing scripts
    repo_root = Path(__file__).parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # Load .env from repo root
    env_file = repo_root / ".env"

    if env_file.exists():
        load_dotenv(env_file)
        print(f"\n✅ Loaded environment from: {env_file}")

        # Verify critical vars loaded
        critical_vars = [
            "ANTHROPIC_VERTEX_PROJECT_ID",
            "GOOGLE_APPLICATION_CREDENTIALS",
        ]
        for var in critical_vars:
            value = os.getenv(var)
            if value:
                print(f"   ✓ {var}: {value[:50]}...")
            else:
                print(f"   ✗ {var}: NOT SET")
    else:
        print(f"\n⚠️  No .env file found at: {env_file}")


@contextmanager
def claude_sdk_context():
    """Context manager to temporarily unset GOOGLE_APPLICATION_CREDENTIALS for Claude SDK.

    Claude Agent SDK uses Application Default Credentials (ADC), but
    GOOGLE_APPLICATION_CREDENTIALS (for Gemini LLM-under-test) confuses it.

    Usage:
        with claude_sdk_context():
            # Call Claude Agent SDK here
            async for msg in claude_query(...):
                ...
    """
    saved = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    try:
        yield
    finally:
        if saved:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = saved


@pytest.fixture
def unset_google_creds_for_claude():
    """Fixture to automatically unset GOOGLE_APPLICATION_CREDENTIALS for Claude SDK tests.

    Use this fixture in tests that call Claude Agent SDK.

    Example:
        @pytest.mark.asyncio
        async def test_claude(unset_google_creds_for_claude):
            async for msg in claude_query(...):
                ...
    """
    saved = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    yield
    if saved:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = saved
