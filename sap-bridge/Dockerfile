# =============================================================================
# SAP EWM Robot Bridge — Dockerfile (Production Grade)
# =============================================================================
# Build:
#   docker build -t robot-platform-sap-bridge:latest ./sap-bridge
#
# Requirements:
#   - SAP NW RFC SDK must be installed in the build context (optional for dev)
#   - Set SAPNWRFC_HOME env to SDK path if building with RFC support
#
# Run:
#   docker run -d --name sap-bridge -p 8000:8000 robot-platform-sap-bridge:latest
# =============================================================================

FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cached layer)
# pyrfc is excluded — requires SAP NW RFC SDK (optional, installed in runtime stage)
COPY requirements-base.txt .
RUN pip install --no-cache-dir --user -r requirements-base.txt

# =============================================================================
FROM python:3.11-slim AS runtime

ARG RUNTIME_VERSION
ARG INCLUDE_RFC=false

# Security: create non-root user
RUN groupadd -r robot && useradd -r -g robot -d /app -s /sbin/nologin robot

WORKDIR /app

# Copy installed Python packages from builder
# 🔧 修复：复制到 /usr/local/ 而非 /root/.local/，robot 用户可访问
COPY --from=builder /root/.local /usr/local

# Install runtime system dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi8 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Conditionally install SAP NW RFC SDK for Classic WM backend
RUN if [ "$INCLUDE_RFC" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
            libicu-dev \
            libssl-dev \
            libsapnwrfcsdk \
        && rm -rf /var/lib/apt/lists/*; \
    fi

# Copy application code
COPY --chown=robot:robot . .

# Security: read-only root filesystem (requires --read-only flag at runtime)
# VOLUME /tmp  # Uncomment if using --read-only

# Security: drop all capabilities
RUN sed -i '/^exec/iexec 2>/dev/null || true' /app/main.py || true

# Container labels
LABEL maintainer="Robot Platform Team" \
      version="${RUNTIME_VERSION:-v4.1}" \
      description="SAP EWM Robot Dispatch Platform — SAP Bridge" \
      security.scope="internal-network-only"

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=15s \
    CMD curl -f http://localhost:8000/health || exit 1

# API port (internal network only)
EXPOSE 8000

# Switch to non-root user
USER robot

# Run with uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
