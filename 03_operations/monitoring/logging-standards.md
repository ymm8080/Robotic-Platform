# Logging Standards

> **Location:** `03_operations/monitoring/logging-standards.md`
> **Last Updated:** 2026-06-22

## Docker Log Driver

All services use `json-file` driver with:

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"   # Rotate at 10MB per file
    max-file: "3"     # Keep 3 rotated files max
```

Configured in `docker-compose.yml` at service level.

## Log Format

### Structured JSON (Recommended for SAP Bridge)

```json
{
  "timestamp": "2026-06-22T10:00:00.000Z",
  "level": "info",
  "service": "sap-bridge",
  "request_id": "req-001",
  "message": "Warehouse task confirmed",
  "details": {
    "warehouse": "WM01",
    "task_id": "T1000",
    "sap_status": 200
  }
}
```

### Plain Text (Node-RED)

```
2026-06-22 10:00:00 [info] [mqtt-broker:connected] Connected to broker
2026-06-22 10:00:01 [info] [order:dispatched] ORDER-001 → KUKA-001
```

## Log Sources

| Service | Log Location (Docker) | Key Events |
|---------|----------------------|------------|
| Node-RED | `docker logs nodered` | Flow execution, MQTT events |
| SAP Bridge | `docker logs sap-bridge` | OData calls, RFC calls, errors |
| Watchdog | `docker logs watchdog` | Health checks, alerts, safe-mode |
| Mosquitto | `docker logs mqtt` | Client connect/disconnect |

## Verification

```bash
# Check log size
docker logs nodered 2>&1 | measure | wc -c

# Force rotation test
docker logs nodered --tail 1000000 > /dev/null
# Verify old log still accessible

# Check no log > 10MB
docker exec nodered ls -la /data/ | grep -c "\.log"
```
