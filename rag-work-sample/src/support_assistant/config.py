"""Explicit environment configuration.

Every value the service depends on is declared here, validated by Pydantic, and
read from the environment with a documented default. Nothing is read from the
environment anywhere else in the package, so this file is the complete list of
what can be configured.

No secret is read here, and none is required. The service has no credentials
because it calls nothing external: the default answer generator is local and
deterministic, and the optional model adapter talks to a runtime on the same
machine.
"""

from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Prefix for every environment variable this service reads.
ENV_PREFIX = "SUPPORT_"

SERVICE_NAME = "support-assistant-work-sample"
SERVICE_VERSION = "0.1.0"


class Settings(BaseModel):
    """Validated runtime settings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8080, ge=1, le=65535)

    #: Whole-request budget for the workflow, in seconds.
    request_timeout_seconds: float = Field(default=10.0, gt=0.0)
    #: How long to wait for a slow client before closing the connection.
    client_timeout_seconds: float = Field(default=15.0, gt=0.0)

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    #: When false (the default) query text is never written to logs — only a
    #: truncated digest and the character count. Set true only for local
    #: debugging, and never against real customer text.
    log_query_text: bool = False

    generator: Literal["mock", "ollama"] = "mock"
    ollama_url: str = Field(default="http://127.0.0.1:11434")
    ollama_model: str = Field(default="qwen2.5-coder:latest")

    corpus_path: str = Field(default="corpus/harbourline_procedures.json")
    #: Directory the process will write nothing to. Declared so a deployment can
    #: assert it stays unwritten.
    data_dir: str = Field(default="build")

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> Settings:
        """Build settings from the environment, validating every value."""
        source = os.environ if environ is None else environ

        raw: dict[str, object] = {}
        for field_name in cls.model_fields:
            key = f"{ENV_PREFIX}{field_name.upper()}"
            if key in source:
                raw[field_name] = source[key]
        return cls.model_validate(raw)

    def redacted_summary(self) -> dict[str, object]:
        """A loggable summary of the configuration.

        Returns the settings that are safe to emit on startup. There are no
        secrets today; if one is ever added, it must be excluded here rather
        than trusted not to appear.
        """
        return {
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
            "host": self.host,
            "port": self.port,
            "request_timeout_seconds": self.request_timeout_seconds,
            "log_level": self.log_level,
            "log_query_text": self.log_query_text,
            "generator": self.generator,
            "corpus_path": self.corpus_path,
        }
