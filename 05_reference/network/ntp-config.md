# NTP Clock Sync

**Last Updated**: 2026-06-21

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

# Set NTP server (use pool or internal time server)
w32tm /config /manualpeerlist:"time.windows.com,0x9 pool.ntp.org,0x9" /syncfromflags:MANUAL
w32tm /config /update
w32tm /resync

# Verify
w32tm /query /status
```

## Docker Containers
All containers inherit host clock via `TZ=UTC`. No additional config needed.
Clock sync is verified by NTP on the host.

## Monitoring
- Watchdog checks clock offset daily
- Alert if drift > 1 second
- Check: `docker exec robot-platform-nodered date`
