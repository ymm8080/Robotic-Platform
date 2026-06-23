# WCS Shadow Sandbox — Multi-Brand Mock Service

> Design doc v3.35, Improvement #13: "WCS影子沙箱（FastAPI Mock+TEST_TIMEOUT前缀）"

## Purpose

| Function | Detail |
|----------|--------|
| **Negotiation leverage** | Demonstrate zone_lock API works — force WCS vendors to match |
| **Regression baseline** | Mock responses capture expected behavior for test automation |
| **Vendor blame evidence** | `known_deviations` log when WCS response differs from contract |
| **Development acceleration** | Develop & test dispatch logic without real WCS |

## Quick Start

```bash
cd wcs-sandbox
pip install -r requirements.txt
uvicorn main:app --port 8100 --reload
```

Or via Docker Compose (uncomment in `docker-compose.yml`):

```bash
docker compose up -d wcs-sandbox
```

## API Reference

### Zone Lock (WCS必须支持)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/zone_lock` | Acquire zone lock (423 if contested) |
| DELETE | `/api/zone_lock/{zone_id}` | Release zone lock (requires zone_token) |
| GET | `/api/zone_lock/{zone_id}` | Check zone lock status |

### Task Callback (标准化契约 §1)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/wcs/task_callback` | WCS → Platform callback (standard 5 fields) |
| GET | `/api/wcs/task_callbacks` | List recent callbacks |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/admin/brand/{brand}/configure` | Override brand behavior (delay, format, deviations) |
| GET | `/api/admin/brand/{brand}` | Get brand behavior config |
| GET | `/api/admin/deviation-log` | Known vendor deviations (blame evidence) |
| GET | `/api/admin/stress-test` | Generate zone lock contention for load testing |

## Brand Behaviors

| Brand | Zone Lock | Delay | Known Deviations |
|-------|-----------|-------|------------------|
| Geek+ | ✅ | 200ms | `zone_token_missing_on_release` |
| Hikrobot | ✅ | 500ms | `nested_response_wrapper`, `slow_callback` |
| MiR | ❌ | 100ms | `no_zone_lock` |

## TEST_TIMEOUT

Prepend `TEST_TIMEOUT_N_` to any robot_id or task_id to inject N ms delay:

```bash
# 5 second delay
curl -X POST http://localhost:8100/api/zone_lock \
  -d '{"zone_id":"Z01","robot_id":"TEST_TIMEOUT_5000_R001","brand":"geekplus"}'

# 10 second delay on task callback
curl -X POST http://localhost:8100/api/wcs/task_callback \
  -d '{"task_id":"TEST_TIMEOUT_10000_T001","status":"COMPLETED"}'
```

## Testing

```bash
# Health check
curl http://localhost:8100/health

# Acquire lock
curl -X POST http://localhost:8100/api/zone_lock \
  -H "Content-Type: application/json" \
  -d '{"zone_id":"CROSS_01","robot_id":"R001","brand":"geekplus","duration_seconds":120}'

# Lock contention (should get 423)
curl -X POST http://localhost:8100/api/zone_lock \
  -H "Content-Type: application/json" \
  -d '{"zone_id":"CROSS_01","robot_id":"R002","brand":"hikrobot"}'

# Release lock
curl -X DELETE "http://localhost:8100/api/zone_lock/CROSS_01?robot_id=R001&zone_token=zt_..."

# Stress test
curl "http://localhost:8100/api/admin/stress-test?count=50&brand=geekplus"
```
