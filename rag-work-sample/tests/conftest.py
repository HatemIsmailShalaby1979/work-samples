"""Shared pytest configuration."""

from __future__ import annotations

import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Run async tests on asyncio only — no trio dependency is installed."""
    return "asyncio"
