"""Tests for environment configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from support_assistant.config import ENV_PREFIX, SERVICE_NAME, SERVICE_VERSION, Settings


def test_defaults_are_safe() -> None:
    settings = Settings.from_env({})
    assert settings.port == 8080
    assert settings.generator == "mock"
    # The important default: query text is not logged.
    assert settings.log_query_text is False


def test_environment_overrides_are_applied() -> None:
    settings = Settings.from_env(
        {
            f"{ENV_PREFIX}PORT": "9999",
            f"{ENV_PREFIX}LOG_LEVEL": "DEBUG",
            f"{ENV_PREFIX}GENERATOR": "ollama",
            f"{ENV_PREFIX}LOG_QUERY_TEXT": "true",
        }
    )
    assert settings.port == 9999
    assert settings.log_level == "DEBUG"
    assert settings.generator == "ollama"
    assert settings.log_query_text is True


def test_unprefixed_variables_are_ignored() -> None:
    """Only SUPPORT_-prefixed variables may configure the service."""
    settings = Settings.from_env({"PORT": "9999", "LOG_LEVEL": "DEBUG"})
    assert settings.port == 8080
    assert settings.log_level == "INFO"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("PORT", "0"),
        ("PORT", "70000"),
        ("PORT", "not-a-number"),
        ("LOG_LEVEL", "TRACE"),
        ("GENERATOR", "gpt"),
        ("REQUEST_TIMEOUT_SECONDS", "0"),
        ("REQUEST_TIMEOUT_SECONDS", "-1"),
    ],
)
def test_invalid_values_are_rejected(key: str, value: str) -> None:
    with pytest.raises(ValidationError):
        Settings.from_env({f"{ENV_PREFIX}{key}": value})


def test_redacted_summary_contains_no_secret_and_names_the_service() -> None:
    summary = Settings.from_env({}).redacted_summary()
    assert summary["service"] == SERVICE_NAME
    assert summary["version"] == SERVICE_VERSION
    assert "password" not in str(summary).lower()
    assert "token" not in str(summary).lower()
