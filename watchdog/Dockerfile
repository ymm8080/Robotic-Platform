# =============================================================================
# SAP-EWM Watchdog v3.4 — Dockerfile
# =============================================================================
# Stage 1: docker CLI binary
FROM docker:27-cli AS docker-cli

# Stage 2: runtime
FROM python:3.11-slim

LABEL maintainer="robot-platform-team"
LABEL version="v3.4"
LABEL description="Watchdog: health monitoring + circuit breaker + safe mode"

# Copy docker CLI binary from official image
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

# System deps: only curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# App
WORKDIR /app
COPY watchdog.py .
COPY config.yaml .

RUN mkdir -p /app/logs

# Non-root
RUN groupadd -r watchdog && useradd -r -g watchdog watchdog \
    && chown watchdog:watchdog /app/logs
USER watchdog

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9090/health || exit 1

CMD ["python", "-u", "watchdog.py"]
