# P1 Audit Findings — 2026-06-23

## P1-a: Secrets Audit

| # | Finding | Severity | Location | Action |
|---|---------|----------|----------|--------|
| 1 | `NODE_RED_ADMIN_PASS=admin` in `.env` (plaintext) | YELLOW MED | `.env` | Document as known dev default; production must change |
| 2 | Hardcoded bcrypt hash in settings.js | GREEN LOW | `nodered/settings.js:85` | Documented as default, requires production override via env |
| 3 | SAP password via Docker Secrets | CHECK GOOD | `docker-compose.yml:151` | `SAP_PASSWORD_FILE=/run/secrets/sap_password` |
| 4 | Feishu/WeCom secrets via env vars | GREEN LOW | `docker-compose.yml:31-37` | Acceptable per PLAN.md notes (no Docker Secret option) |
| 5 | `.env` in `.gitignore` | CHECK GOOD | `.gitignore` | Confirmed not tracked |

**Conclusion**: No hardcoded credentials committed. The dev `.env` has a known-default admin password which must be changed in production.

## P1-b: Redis TTL Audit

| # | Finding | Severity | Location | Action |
|---|---------|----------|----------|--------|
| 1 | **maxmemory = 256mb** (PLAN.md specifies 8GB) | CHECK RESOLVED | `redis/redis.conf:8` | Already `maxmemory 8gb`, verified 2026-06-23 |
| 2 | `hset(robot:connection:*)` + `expire(300s)` | CHECK GOOD | `heartbeat_monitor.py:84-90` | TTL correct |
| 3 | `hset(robot:connection:*)` state update + `expire(300s)` | CHECK GOOD | `heartbeat_monitor.py:98-107` | TTL correct |
| 4 | `incr(mqtt:seq:*)` + `expire(86400s)` | CHECK GOOD | `mqtt_publisher.py:96-97` | TTL correct |
| 5 | `hset(order:*)` + `expire(86400*7)` | CHECK GOOD | `main.py:156-157` | TTL correct |
| 6 | `lpush(orders:recent)` — no TTL on list | GREEN LOW | `main.py:158-159` | Bounded by `ltrim(100)`, acceptable |
| 7 | Node-RED `global.set()` uses memory context | YELLOW MED | `flows.json` | Documented migration path: use Redis context store |
| 8 | AOF+RDB persistence enabled | CHECK GOOD | `redis.conf` | `appendonly yes`, `appendfsync everysec` |

**Conclusion**: All resolved. Redis correctly configured with 8GB maxmemory.

## P1-c: MQTT QoS/Sequence Audit

| # | Finding | Severity | Location | Action |
|---|---------|----------|----------|--------|
| 1 | **Order publish uses `qos=0`** (should be QoS 1) | CHECK RESOLVED | `main.py:202` | Already `qos=1`, verified 2026-06-23 |
| 2 | `mqtt_publisher.py` defaults to QoS 1 (correct) | CHECK GOOD | `mqtt_publisher.py:75` | Default is correct |
| 3 | LWT configured with QoS 1 + retain | CHECK GOOD | `mqtt_publisher.py:53-58` | VDA5050-compliant |
| 4 | Auto sequenceNumber via Redis INCR | CHECK GOOD | `mqtt_publisher.py:95-97` | VDA5050-compliant |
| 5 | Connection/state subscription QoS 1 | CHECK GOOD | `heartbeat_monitor.py:62-63` | Correct |
| 6 | `allow_anonymous true` in mosquitto.conf | YELLOW MED | `mosquitto.conf:4` | Production should use `password_file` |
| 7 | Node-RED flows — no MQTT output nodes | CHECK GOOD | `flows.json` | SAP Bridge handles all MQTT publishing |

**Conclusion**: Both HIGH items resolved. MED item (anonymous MQTT) remains for production hardening.

## P1-d: CI/CD & Infrastructure (NEW 2026-06-23)

| # | Finding | Severity | Location | Action |
|---|---------|----------|----------|--------|
| 1 | No CI/CD pipeline | CHECK RESOLVED | `.github/workflows/ci.yml` | Created CI with lint/test/build/docker stages |
| 2 | No dependency security scanning | CHECK RESOLVED | `.github/workflows/security-scan.yml` | pip-audit + npm-audit weekly |
| 3 | `.env.example` incomplete | CHECK RESOLVED | `.env.example` | Added all vars: WECOM, Dify, Feishu app, HOST, SAP_LANG |
| 4 | No Prompt version management dir | YELLOW MED | `prompts/` | Exists with 3 prompts, no version metadata |
| 5 | No data mask Function node | YELLOW MED | Node-RED | Design doc v3.35 requires Data_Mask node |

## Summary

| Category | HIGH | MED | LOW | GOOD/RESOLVED |
|----------|------|-----|-----|---------------|
| Secrets | 0 | 1 | 2 | 3 |
| Redis | 0 | 1 | 1 | 6 |
| MQTT | 0 | 1 | 0 | 6 |
| CI/CD | 0 | 2 | 0 | 3 |
| **Total** | **0** | **5** | **3** | **18** |
