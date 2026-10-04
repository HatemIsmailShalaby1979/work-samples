# syntax=docker/dockerfile:1
#
# Local development and demonstration image for the support-assistant work sample.
#
# This image is built and run locally only. It is not deployed anywhere, no
# registry is involved, and nothing here constitutes a production deployment.
# See docs/CLOUD_MAPPING.md for what a real deployment would additionally need —
# documented as a design exercise, explicitly not performed.

FROM python:3.13-slim AS base

# Fail fast on warnings, do not buffer stdout (so structured logs stream), and
# do not write .pyc files into a read-only filesystem.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first, so the layer caches across source changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY src/ ./src/
COPY corpus/ ./corpus/

# The process must not need to write anywhere. /app is owned by the runtime
# user only so that an accidental write attempt fails loudly rather than
# silently succeeding in a layer that will be discarded.
RUN useradd --create-home --shell /usr/sbin/nologin --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

ENV PYTHONPATH=/app/src \
    SUPPORT_HOST=0.0.0.0 \
    SUPPORT_PORT=8080 \
    SUPPORT_LOG_LEVEL=INFO \
    SUPPORT_LOG_QUERY_TEXT=false \
    SUPPORT_GENERATOR=mock \
    SUPPORT_CORPUS_PATH=/app/corpus/harbourline_procedures.json

EXPOSE 8080

# Healthcheck uses the interpreter already in the image — no curl is installed,
# deliberately, to keep the attack surface and the image size down.
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).status == 200 else 1)"]

# Unbuffered, exec form, so the process receives SIGTERM directly and the
# graceful-shutdown handler in service.py actually runs.
CMD ["python", "-m", "support_assistant.service"]
