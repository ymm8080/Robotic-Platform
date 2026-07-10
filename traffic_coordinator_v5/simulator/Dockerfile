FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy core platform types and the simulator package.
COPY core /app/core
COPY traffic_coordinator_v5/simulator /app/traffic_coordinator_v5/simulator
COPY traffic_coordinator_v5/maps /app/traffic_coordinator_v5/maps
COPY pyproject.toml /app/pyproject.toml

RUN pip install --no-cache-dir -e "."

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from traffic_coordinator_v5.simulator import FleetSimulator, LaneGraph" || exit 1

CMD ["python", "-m", "traffic_coordinator_v5.simulator"]
