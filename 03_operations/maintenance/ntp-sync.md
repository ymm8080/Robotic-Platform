# NTP Clock Sync

> **Location:** `03_operations/maintenance/ntp-sync.md`
> **Last Updated:** 2026-06-22

## Requirement

All platform hosts must have synchronized clocks. Clock drift >1s causes:

- MQTT message timestamp confusion
- SAP OData CSRF token expiry
- Redis key TTL drift
- Log correlation failures

## Windows Host Configuration

```powershell
# Check current NTP status
w32tm /query /status

# Check current time source
w32tm /query /source

# Configure NTP server
w32tm /config /manualpeerlist:"pool.ntp.org" /syncfromflags:manual /reliable:yes /update

# Force sync
w32tm /resync

# Verify drift
w32tm /query /peers
```

## Docker Containers

All containers inherit host time via `TZ=UTC` in docker-compose.yml. No extra NTP config needed inside containers.

## Verification

```bash
# Check time difference between host and containers
docker exec sap-bridge date
docker exec nodered date
docker exec mqtt date

# All should show UTC time within 1s of each other
```

## Monitoring

| Metric | Threshold | Action |
|--------|-----------|--------|
| Clock drift | >1s | Re-sync NTP |
| NTP source unreachable | >30min | Check network/firewall |
