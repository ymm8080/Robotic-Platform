# Logging Standards

**Last Updated**: 2026-06-21

## Docker Log Driver

All services use `json-file` driver with:
```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"   # Rotate at 10MB per file
    max-file: "3"     # Keep 3 rotated files max
```

**Result**: Max 30MB log footprint per service, auto-rotated.

## Per-Service Log Locations

| Service | Log Source | Access |
|---------|-----------|--------|
| Node-RED | `docker logs robot-platform-nodered` | stdout/stderr |
| SAP Bridge | `docker logs robot-platform-sap-bridge` + `/app/logs/` | stdout + volume |
| Watchdog | `docker logs robot-platform-watchdog` + `/app/logs/` | stdout + volume |
| MQTT | `docker logs robot-platform-mqtt` + `/mosquitto/log/` | stdout + volume |

## Verification

```bash
# Check log size per container
docker ps -q | xargs -I {} sh -c 'echo "{}: $(docker inspect {} --format={{.LogPath}} | xargs ls -lh 2>/dev/null | awk "{print \$5}")"'

# Force rotate (test)
docker kill -s USR1 robot-platform-nodered  # if logger supports it
```
