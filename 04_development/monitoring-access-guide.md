# Monitoring Stack Access Guide v3.4

> Prometheus + Alertmanager + Grafana — accessed via Docker internal network.

## Quick Start

```powershell
# Start the monitoring stack
docker compose up -d prometheus alertmanager grafana

# Verify all 3 are running
docker compose ps prometheus alertmanager grafana
```

## Access URLs (localhost only)

| Service | URL | Default Credentials | Description |
|---------|-----|-------------------|-------------|
| **Prometheus** | http://localhost:9091 | — | Metrics query + alert status |
| **Alertmanager** | http://localhost:9093 | — | Alert routing + silences |
| **Grafana** | http://localhost:3000 | admin / admin | Dashboard visualizations |

> All ports are bound to `127.0.0.1` (localhost only) — no external access.

## Verifying the Stack

### 1. Prometheus Targets

```powershell
# Check all scrape targets are "UP"
curl http://localhost:9091/api/v1/targets | python -c "import json,sys; d=json.load(sys.stdin); [print(f'{t[\"labels\"][\"job\"]}: {t[\"health\"]}') for t in d['data']['activeTargets']]"
```

Expected output:
```
sap-bridge: up
watchdog: up
```

### 2. Query Metrics

```powershell
# Check SAP Bridge is scraping
curl "http://localhost:9091/api/v1/query?query=sap_bridge_mqtt_connected"

# Check Watchdog metrics
curl "http://localhost:9091/api/v1/query?query=watchdog_safe_mode"

# Check orders created in last 5 minutes
curl "http://localhost:9091/api/v1/query?query=rate(sap_bridge_orders_created_total[5m])"
```

### 3. Alert Rules

```powershell
# View all alert rules and their state
curl http://localhost:9091/api/v1/rules | python -c "import json,sys; d=json.load(sys.stdin); [print(f'{g[\"name\"]}: {len(g[\"rules\"])} rules') for g in d['data']['groups']]"
```

Expected: 1 group "robot-platform" with 12 alert rules.

### 4. Direct Metric Verification

```powershell
# SAP Bridge raw metrics (from inside Docker network)
curl -H "Accept: text/plain" http://localhost:8000/metrics | grep -E "^# HELP|^sap_bridge_"

# Watchdog raw metrics
curl -H "Accept: text/plain" http://localhost:9090/metrics | grep -E "^# HELP|^watchdog_"
```

## Grafana Dashboard

After logging in at http://localhost:3000 (admin/admin):
1. Go to Dashboards → Browse
2. Select "SAP-EWM Robot Dispatch Platform"
3. The dashboard has 12 panels across 3 rows:
   - **Row 1**: Orders created/sec, completed/sec, failed/sec, queue depth, dead letter count, uptime
   - **Row 2**: System connectivity table, Node-RED CPU %, checkpoint latency
   - **Row 3**: Safe mode/throttle state, Redis memory ratio, SQLite WAL size

To change Grafana password:
```powershell
docker compose exec grafana grafana-cli admin reset-admin-password <new-password>
```

## Alertmanager

Alerts route to Watchdog webhook → Feishu/WeCom notification channels.

```powershell
# View active alerts
curl http://localhost:9093/api/v2/alerts

# Silence an alert (15 min)
curl -X POST http://localhost:9093/api/v2/silences -H "Content-Type: application/json" -d '{
  "matchers": [{"name": "alertname", "value": "NodeREDHighCPU", "isRegex": false}],
  "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
  "endsAt": "'$(date -u -d '+15 minutes' +%Y-%m-%dT%H:%M:%SZ)'",
  "createdBy": "operator",
  "comment": "Maintenance window"
}'
```

## Alert Rules Summary

| Alert | Severity | Condition | Action |
|-------|----------|-----------|--------|
| SAPBridgeDown | critical | up == 0 for 30s | Check container |
| SAPBridgeHighErrorRate | warning | failures > 3/min | Check SAP connectivity |
| SAPBridgeSAPDisconnected | critical | sap_connected == 0 for 1m | Check SAP EWM |
| SAPBridgeMQTTDisconnected | critical | mqtt_connected == 0 for 30s | Check Mosquitto |
| DeadLetterQueueGrowing | warning | DLQ > 10 for 5m | Investigate orders |
| SafeModeActivated | critical | safe_mode == 1 | Emergency response |
| NodeREDHighCPU | warning | CPU > 80% for 2m | Consider scaling |
| NodeREDCheckpointHigh | warning | checkpoint > 5s for 2m | Check Node-RED health |
| RedisMemoryCritical | critical | mem ratio > 95% for 1m | Flush or scale Redis |
| RedisMemoryWarning | warning | mem ratio > 80% for 5m | Review TTLs |
| WALFileTooLarge | warning | WAL > 100MB for 5m | Check SQLite checkpoint |

## Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| Prometheus can't scrape sap-bridge | `docker compose logs prometheus` | Ensure sap-bridge is healthy |
| Grafana shows "No data" | Check datasource → Prometheus URL | Must be `http://prometheus:9090` (internal DNS) |
| Alertmanager not receiving alerts | `docker compose logs alertmanager` | Check prometheus.yml alerting config |
| Grafana login failed | default admin/admin | Run password reset command above |
| Watchdog returns JSON not Prometheus | Called without Accept header | Add `-H "Accept: text/plain"` |
