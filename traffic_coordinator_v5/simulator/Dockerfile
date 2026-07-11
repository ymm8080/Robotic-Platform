FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy core platform types, the simulator package, maps, and package metadata.
COPY core /app/core
COPY traffic_coordinator_v5/__init__.py /app/traffic_coordinator_v5/__init__.py
COPY traffic_coordinator_v5/simulator /app/traffic_coordinator_v5/simulator
COPY traffic_coordinator_v5/maps /app/traffic_coordinator_v5/maps
COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md

RUN pip install --no-cache-dir -e "."

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from traffic_coordinator_v5.simulator import FleetSimulator, LaneGraph" || exit 1

CMD ["python", "-m", "traffic_coordinator_v5.simulator"]
