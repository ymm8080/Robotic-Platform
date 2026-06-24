# Disaster Recovery Drill Procedure

> **Target:** Full system recovery within 1 hour
> **Frequency:** Quarterly
> **Prerequisites:** Backup scripts verified, staging environment ready

## Recovery Scenarios

### Scenario A: Complete Data Center Loss
Simulates total infrastructure failure — restore everything from off-site backups.

### Scenario B: Single Service Failure
Simulates a critical service crash — test Docker restart policy and Watchdog recovery.

### Scenario C: SAP Connection Loss
Simulates SAP EWM/WM outage — verify outbox pattern queues and recovers post-restore.

---

## Scenario A — Full Recovery

### Phase 1: Assessment (0-5 min)

```bash
# 1. Check what's available
docker compose ps                    # All down?
docker volume ls                     # Volumes intact?
ls -la /var/lib/docker/volumes/     # Check data persistence
ping sap-ewm.example.com             # SAP reachable?

# 2. Report to incident channel
# Severity: CRITICAL
# Impact: All robot dispatch stopped
```

### Phase 2: Restore Infrastructure (5-20 min)

```bash
# 1. Check disk and Docker
df -h /var/lib/docker
systemctl status docker

# 2. Restore volumes from backup
BACKUP_FILE="D:/EWM ROBOT/backups/$(date +%Y%m%d)/nodered-data.tar.gz"
docker run --rm -v nodered-data:/target -v $(dirname $BACKUP_FILE):/backup \
  alpine tar xzf /backup/$(basename $BACKUP_FILE) -C /target

# Repeat for: redis-data, mqtt-data, grafana-data, prometheus-data

# 3. Restore secrets
cp secrets/sap_password.txt.backup secrets/sap_password.txt
```

### Phase 3: Start Services (20-30 min)

```bash
# 1. Start core infrastructure first
docker compose up -d redis mqtt
sleep 5

# 2. Start data-dependent services
docker compose up -d nodered sap-bridge
sleep 10

# 3. Start monitoring
docker compose up -d prometheus grafana alertmanager watchdog
sleep 5

# 4. Start auxiliary
docker compose up -d nginx-rescue dashboard docker-socket-proxy
```

### Phase 4: Verify (30-45 min)

```bash
# 1. All services healthy?
docker compose ps | grep -c "Up"  # Should be 10+

# 2. MQTT reachable?
mosquitto_sub -t "vda5050/+/+/connection" -C 1 -W 5

# 3. Redis data restored?
docker exec robot-platform-redis redis-cli DBSIZE
redis-cli GET "sap:csrf_last_refresh"  # Should exist if restored

# 4. SAP connection?
curl -f http://localhost:8000/api/v1/sap/health

# 5. Robot states restored?
curl -f http://localhost:1880/api/v1/robots/status

# 6. Outbox items intact?
curl http://localhost:1880/api/v1/admin/queue/depth

# 7. Deadletter items intact?
curl http://localhost:1880/api/v1/admin/deadletter
```

### Phase 5: Resume Dispatch (45-60 min)

```bash
# 1. Exit safe mode if active
curl -X POST http://localhost:1880/api/restore-mode

# 2. Flush outbox (retry pending SAP calls)
# Watchdog auto-flushes on start, check:
docker logs robot-platform-watchdog --tail 20 | grep outbox

# 3. Verify order flow
curl -X POST http://localhost:1880/api/v1/orders \
  -H "Content-Type: application/json" \
  -d '{"manufacturer":"KUKA","serialNumber":"DR-TEST-001","orderId":"DR-DRILL-'$(date +%s)'","orderType":"MOVE","priority":2}'

# 4. Confirm dispatch
curl http://localhost:1880/api/v1/orders | jq '.orders[-1]'
```

---

## Scenario B — Single Service Failure

```bash
# 1. Detect failure
docker ps --filter "status=exited"
docker logs robot-platform-nodered --tail 50

# 2. Verify Docker restart policy triggered
docker inspect robot-platform-nodered --format '{{.RestartPolicy}}'
# Expected: {Name:unless-stopped MaximumRetryCount:0}

# 3. If restart policy failed
docker compose up -d nodered --no-deps

# 4. Verify recovery
curl -f http://localhost:1880/api/system-health
```

---

## Scenario C — SAP Connection Loss

```bash
# 1. Verify SAP is unreachable
curl -f http://localhost:8000/api/v1/sap/health
# Expected: {"connected": false, ...}

# 2. Check outbox not growing unbounded
curl http://localhost:1880/api/v1/admin/queue/depth

# 3. When SAP returns, verify outbox drains
for i in $(seq 1 30); do
  pending=$(curl -s http://localhost:8000/api/v1/admin/queue/depth | python3 -c "import sys,json; print(json.load(sys.stdin).get('depth', -1))")
  echo "Pending: $pending"
  [ "$pending" -eq 0 ] && break
  sleep 5
done
```

---

## Post-Drill Checklist

| Item | Verified | Notes |
|------|----------|-------|
| All 10 services "Up" + "healthy" | ☐ | |
| Backup restoration verified | ☐ | |
| SAP connection established | ☐ | |
| MQTT pub/sub working | ☐ | |
| Robot states restored | ☐ | |
| Outbox empty (processing normally) | ☐ | |
| Deadletter items reviewed | ☐ | |
| Order creation working | ☐ | |
| Order dispatch verified | ☐ | |
| Dashboard accessible | ☐ | |
| Alert rules firing correctly | ☐ | |
| Recovery time < 1 hour | ☐ | |

## Escalation Contacts

| Role | Contact | Backup |
|------|---------|--------|
| Platform Ops | ops@example.com | +86-138-0000-0000 |
| SAP Admin | sap@example.com | +86-138-0000-0001 |
| Infra Lead | infra@example.com | +86-138-0000-0002 |
