# P1 Audit Findings — 2026-06-23

## P1-a: Secrets Audit

| # | Finding | Severity | Location | Action |
|---|---------|----------|----------|--------|
| 1 | `NODE_RED_ADMIN_PASS=admin` in `.env` (plaintext) | 🟡 MED | `.env` line 45 | Document as known dev default; production must change |
| 2 | Hardcoded bcrypt hash in settings.js | 🟢 LOW | `nodered/settings.js:85` | Documented as default, requires production override via env |
| 3 | SAP password via Docker Secrets | ✅ GOOD | `docker-compose.yml:151` | `SAP_PASSWORD_FILE=/run/secrets/sap_password` |
| 4 | Feishu/WeCom secrets via env vars | 🟢 LOW | `docker-compose.yml:31-37` | Acceptable per PLAN.md notes (no Docker Secret option for Dify) |
| 5 | `.env` in `.gitignore` | ✅ GOOD | `.gitignore` | Confirmed not tracked |

**Conclusion**: No hardcoded credentials committed. The dev `.env` has a known-default admin password which must be changed in production.

## P1-b: Redis TTL Audit

| # | Finding | Severity | Location | Action |
|---|---------|----------|----------|--------|
| 1 | **maxmemory = 256mb** (PLAN.md specifies 8GB) | 🔴 HIGH | `redis/redis.conf:6` | Update to `maxmemory 8gb` |
| 2 | `hset(robot:connection:*)` + `expire(300s)` | ✅ GOOD | `heartbeat_monitor.py:84-90` | TTL correct |
| 3 | `hset(robot:connection:*)` state update + `expire(300s)` | ✅ GOOD | `heartbeat_monitor.py:98-107` | TTL correct |
| 4 | `incr(mqtt:seq:*)` + `expire(86400s)` | ✅ GOOD | `mqtt_publisher.py:96-97` | TTL correct |
| 5 | `hset(order:*)` + `expire(86400*7)` | ✅ GOOD | `main.py:156-157` | TTL correct |
| 6 | `lpush(orders:recent)` — no TTL on list | 🟢 LOW | `main.py:158-159` | Bounded by `ltrim(100)`, acceptable |
| 7 | Node-RED `global.set()` uses memory context | 🟡 MED | `flows.json` | Documented migration path: use Redis context store |
| 8 | AOF+RDB persistence enabled | ✅ GOOD | `redis.conf` | `appendonly yes`, `appendfsync everysec` |

**Conclusion**: Only the maxmemory mismatch needs fixing. All Redis operations with TTL are handled correctly.

## P1-c: MQTT QoS/Sequence Audit

| # | Finding | Severity | Location | Action |
|---|---------|----------|----------|--------|
| 1 | **Order publish uses `qos=0`** (should be QoS 1) | 🔴 HIGH | `main.py:186` | Change to `qos=1` |
| 2 | `mqtt_publisher.py` defaults to QoS 1 (correct) | ✅ GOOD | `mqtt_publisher.py:75` | Default is correct |
| 3 | LWT configured with QoS 1 + retain | ✅ GOOD | `mqtt_publisher.py:53-58` | VDA5050-compliant |
| 4 | Auto sequenceNumber via Redis INCR | ✅ GOOD | `mqtt_publisher.py:95-97` | VDA5050-compliant |
| 5 | Connection/state subscription QoS 1 | ✅ GOOD | `heartbeat_monitor.py:62-63` | Correct |
| 6 | `allow_anonymous true` in mosquitto.conf | 🟡 MED | `mosquitto.conf:4` | Production should use `password_file` |
| 7 | Node-RED flows — no MQTT output nodes | ✅ GOOD | `flows.json` | SAP Bridge handles all MQTT publishing |
