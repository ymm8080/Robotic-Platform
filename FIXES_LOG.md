# Fixes Log

This file records every code change made during the design-core review session.
Changes are grouped by file, with the reason (design-core requirement or bug) and a short diff summary.

## Format

- **File**: path relative to repo root
- **Priority**: P0 / P1 / P2 / P3
- **Reason**: which v5.x baseline section or bug category
- **Change**: short description

---

### sap-bridge/simulators/run.py
- **Priority**: P0
- **Reason**: Imported `sap_bridge` package, but the directory is named `sap-bridge` (hyphen), which is not a valid Python package name.
- **Change**: Changed imports to package-relative `from simulators.xxx import ...` since `run.py` lives inside `sap-bridge/simulators/`.

### watchdog/watchdog.py
- **Priority**: P0
- **Reason**: Feishu HMAC signature was computed with missing key argument, causing Feishu to reject all signed watchdog alerts.
- **Change**: Fixed `_gen_sign()` to call `hmac.new(self.secret.encode(...), string_to_sign.encode(...), hashlib.sha256)`.

### gateway/app/main.py
- **Priority**: P0
- **Reason**: `await request.json()` was unguarded, returning HTTP 500 on malformed JSON callbacks.
- **Change**: Wrapped `request.json()` in try/except and return HTTP 400 on `JSONDecodeError`.

- **Priority**: P0
- **Reason**: Core platform response was parsed as JSON before status check, causing HTTP 500 on non-JSON error pages.
- **Change**: Checked `core_resp.status_code` first, guarded `.json()` with `JSONDecodeError`, and captured error text for non-2xx.

- **Priority**: P0 (security)
- **Reason**: Gateway Redis connection ignored TLS settings; `rediss://` URL or `REDIS_SSL=true` were not honored.
- **Change**: Added SSL parameter detection in lifespan: if URL starts with `rediss://` or `REDIS_SSL=true`, pass `ssl=True` and `ssl_cert_reqs` to `aioredis.from_url()`.

### gateway/app/email_gateway.py
- **Priority**: P0
- **Reason**: `smtplib.SMTP` calls inside `async def send` blocked the asyncio event loop.
- **Change**: Moved blocking SMTP logic to `_send_sync()` and invoked it via `asyncio.to_thread()`.

### gateway/app/card_template_engine.py
- **Priority**: P0
- **Reason**: DingTalk action URLs hardcoded `https://ewma.example.com/api/callback`, which does not match the real `/webhook/dingtalk` endpoint.
- **Change**: Introduced `GATEWAY_PUBLIC_URL` from env var and replaced all DingTalk action URLs with `{GATEWAY_PUBLIC_URL}/webhook/dingtalk?...`.

### gateway/app/config.py
- **Priority**: P0 (security)
- **Reason**: `ELASTICSEARCH_PASSWORD` defaulted to hardcoded `robot-platform-es`.
- **Change**: Removed hardcoded default; gateway now requires the password to be supplied via environment/secret.

### sap-bridge/main.py (additional)
- **Priority**: P1
- **Reason**: `robot_status` read `brand` and `raw_state`, but heartbeat monitor stores `manufacturer` and previously did not store `raw_state`.
- **Change**: `robot_status` now reads `manufacturer` from Redis and normalizes via `raw_state`.

- **Priority**: P2
- **Reason**: Pydantic models used mutable list defaults, which can leak state across requests.
- **Change**: Replaced `nodes: list = []` / `edges: list = []` with `Field(default_factory=list)` in `DispatchRequest` and `CreateOrderRequest`; imported `Field` from pydantic.

---

### gateway/app/card_template_engine.py (additional)
- **Priority**: P0
- **Reason**: `GATEWAY_PUBLIC_URL` default value referenced itself (`f"{GATEWAY_PUBLIC_URL}"`), causing `NameError` on module import.
- **Change**: Changed default to literal `"https://ewma.example.com"`.

- **Priority**: P1
- **Reason**: WeChat card action URL was hardcoded `https://ewma.example.com/...`, inconsistent with configurable public URL and broken if gateway is hosted elsewhere.
- **Change**: Replaced hardcoded WeChat card URL with `{GATEWAY_PUBLIC_URL}/{target_type}/{target_id}`.

### sap-bridge/mqtt_publisher.py
- **Priority**: P1
- **Reason**: VDA5050 envelope fields (`headerId`, `timestamp`, `version`, `manufacturer`, `serialNumber`) could be silently overwritten by caller-supplied `payload` because `**payload` was unpacked after the envelope fields.
- **Change**: Reordered message build so `**payload` is unpacked first and envelope fields are set explicitly, preventing header spoofing/sequence corruption.

- **Priority**: P0 (security)
- **Reason**: MQTT connections used plaintext (port 1883) with no authentication or TLS, violating zero-trust transport requirements.
- **Change**: Added `MQTT_USE_TLS`, `MQTT_USERNAME`, `MQTT_PASSWORD`, `MQTT_CA_CERT`, `MQTT_CLIENT_CERT`, `MQTT_CLIENT_KEY` env vars and applied `tls_set()` / `username_pw_set()` in `connect()`.

### sap-bridge/heartbeat_monitor.py
- **Priority**: P0 (security)
- **Reason**: Heartbeat monitor subscribed to VDA5050 topics over plaintext MQTT, inconsistent with the publisher's transport security.
- **Change**: Added the same MQTT TLS/auth env vars and configuration in `start()` so inbound robot telemetry uses authenticated/TLS transport.

### sap-bridge/main.py (additional)
- **Priority**: P0 (security)
- **Reason**: All `/api/v1/` HTTP endpoints were publicly accessible without authentication, allowing unauthenticated dispatch/order/control operations.
- **Change**: Added `api_key_middleware` that requires `X-API-Key` header for `/api/v1/` paths; key loaded from `SAP_BRIDGE_API_KEY` env var or Docker secret at `SAP_BRIDGE_API_KEY_FILE`. Health/readiness/metrics endpoints are exempt.

### sap-bridge/services/order_service.py
- **Priority**: P1 (state consistency)
- **Reason**: `_update()` incremented `order.version` in memory before executing the UPDATE, so a failed optimistic-lock left the in-memory object with a version that no longer matched the database.
- **Change**: Compute `new_version` locally, UPDATE using the current DB version in the WHERE clause, and only assign `order.version = new_version` after the UPDATE succeeds.

### sap-bridge/backends/wm_backend.py
- **Priority**: P0 (security)
- **Reason**: WM backend fell back to `SAP_PASSWORD` env var when the Docker secret password file was missing, silently degrading secret management and potentially exposing credentials.
- **Change**: Aligned with EWM backend: raise `FileNotFoundError` when the password file is missing.

- **Priority**: P2
- **Reason**: `list_tasks()` had unreachable `AssertionError` after `raise_for_status()`; `get_task()` and `create_task()` called `resp.json()` twice, which can fail if the response body is consumed.
- **Change**: Removed dead code and stored JSON result in a local variable before parsing.

- **Priority**: P1 (security hygiene)
- **Reason**: Commented-out Redis context config contained a hardcoded fallback password `robot-platform-redis`; risk of being uncommented later and exposing a default credential.
- **Change**: Removed the hardcoded fallback so the password must be supplied via `REDIS_PASSWORD`.

- **Priority**: P0 (security)
- **Reason**: Hardcoded dashboard login password `admin123` committed to source control.
- **Change**: Moved `DASHBOARD_URL`, `LOGIN_EMAIL`, `LOGIN_PASSWORD`, and `LOGIN_ROLE` to environment variables with empty-password default.

- **Priority**: P0 (security)
- **Reason**: v5.0 Traffic Coordinator HTTP endpoints (`/ingest`, `/order`, `/state`, `/metrics`) were unauthenticated, allowing unauthenticated order submission and fleet state ingestion.
- **Change**: Added `TC_API_KEY` / `TC_API_KEY_FILE` loading and `_check_auth()`; require `X-API-Key` for all endpoints except `/health` and `/version`.

- **Priority**: P1 (input validation)
- **Reason**: `/order` endpoint built `ActionPrimitive[a]` directly from user input, raising unhandled `KeyError` on unknown action strings.
- **Change**: Wrapped action parsing in try/except and return HTTP 400 with the invalid action name.

### wcs-sandbox/main.py
- **Priority**: P2
- **Reason**: `BrandConfigRequest.known_deviations` used mutable list default, which can leak state across requests.
- **Change**: Replaced with `Field(default_factory=list)`.

### gateway/app/platform_adapters/feishu.py
### gateway/app/platform_adapters/wechat.py
- **Priority**: P1 (reliability)
- **Reason**: Access-token refresh in all three adapters called `resp.json()` without handling HTTP errors, non-JSON error pages, or network failures, causing unhandled exceptions and failed alert delivery.
- **Change**: Wrapped token requests in `try/except httpx.HTTPError`, called `raise_for_status()`, and returned empty token on failure so `send_message` degrades gracefully.

### watchdog/watchdog.py (additional)
- **Priority**: P1 (reliability)
- **Reason**: Watchdog stored the safe-mode reason string (e.g., `REDIS_OOM`) in Redis key `system:safe_mode`, but Gateway's action validator checks for exact value `"true"`, so gateway never detected safe mode.
- **Change**: Split the contract: `system:safe_mode` now stores `"true"`/`"false"` and `system:safe_mode_reason` stores the reason string; updated `_recover_state`, `enter_safe_mode`, and `exit_safe_mode` accordingly.

---

## Batch C — Gateway internal API authentication, Redis TLS, platform-adapter hardening

### gateway/app/config.py
- **Priority**: P0 (security)
- **Reason**: Gateway internal endpoints (`/api/v1/notifications/send`, `/api/v1/operations/*`, `/api/v1/audit/logs`) and outbound core-platform calls had no API-key configuration surface.
- **Change**: Added `CORE_PLATFORM_API_KEY`/`CORE_PLATFORM_API_KEY_FILE`, `GATEWAY_API_KEY`/`GATEWAY_API_KEY_FILE` settings and helper properties.

### gateway/app/main.py
- **Priority**: P0 (security)
- **Reason**: Internal gateway endpoints were publicly accessible, allowing unauthenticated alert injection, operation queries, and audit-log reads.
- **Change**: Added `_require_gateway_api_key()` helper and required `X-API-Key` header on `/api/v1/notifications/send`, `/api/v1/operations/{id}`, and `/api/v1/audit/logs`.

- **Priority**: P1 (security)
- **Reason**: Outbound core-platform `/api/execute` calls carried no authentication.
- **Change**: Added `X-API-Key` header using `settings.core_platform_api_key` when calling the core platform.

### gateway/app/action_validator.py
- **Priority**: P1 (security)
- **Reason**: Action validator's Redis connection did not honor `rediss://` or `REDIS_SSL=true`, and outbound object-validation requests to the core platform were unauthenticated.
- **Change**: Added Redis TLS detection in `init()` and added `X-API-Key` header to robot/order/zone validation HTTP calls via `_core_headers()`.

### gateway/app/message_router.py
- **Priority**: P1 (security)
- **Reason**: Message router's Redis connection ignored TLS settings, inconsistent with the main gateway lifespan.
- **Change**: Added Redis TLS detection in `init()`.

### gateway/app/platform_adapters/dingtalk.py
- **Priority**: P1 (security)
- **Reason**: Callback signature verification used `==`, making it vulnerable to timing attacks.
- **Change**: Replaced direct comparison with `hmac.compare_digest()`.

- **Priority**: P1 (reliability)
- **Reason**: `send_message()` called `resp.json()` without checking HTTP status or handling non-JSON error pages.
- **Change**: Added `raise_for_status()`, caught `httpx.HTTPError` and `json.JSONDecodeError`, returning a failed status instead of raising.

### gateway/app/platform_adapters/feishu.py
- **Priority**: P1 (security)
- **Reason**: Token verification used `==`, vulnerable to timing attacks.
- **Change**: Replaced direct comparison with `hmac.compare_digest()`.

- **Priority**: P1 (reliability)
- **Reason**: `send_message()` called `resp.json()` without checking HTTP status or handling non-JSON error pages.
- **Change**: Added `raise_for_status()`, caught `httpx.HTTPError` and `json.JSONDecodeError`.

### gateway/app/platform_adapters/wechat.py
- **Priority**: P1 (security)
- **Reason**: Callback signature verification used `==`, vulnerable to timing attacks.
- **Change**: Replaced direct comparison with `hmac.compare_digest()`.

- **Priority**: P1 (reliability)
- **Reason**: `send_message()` called `resp.json()` without checking HTTP status or handling non-JSON error pages.
- **Change**: Added `raise_for_status()`, caught `httpx.HTTPError` and `json.JSONDecodeError`.

### gateway/app/audit_logger.py
- **Priority**: P1 (security)
- **Reason**: Elasticsearch client ignored HTTPS/TLS verification settings.
- **Change**: Added TLS detection: if URL is `https://` or `ELASTICSEARCH_SSL=true`, set `verify_certs` based on `ELASTICSEARCH_SSL_VERIFY`.

## Batch D — SAP Bridge Redis TLS, MQTT hardening, IDoc XXE protection

### sap-bridge/redis_client.py
- **Priority**: P1 (security)
- **Reason**: Redis connections were created inconsistently across the bridge, many ignoring `rediss://` and `REDIS_SSL`.
- **Change**: New shared helper module `redis_client.py` with `redis_from_url()` and `async_redis_from_url()` that honor TLS env vars.

### sap-bridge/main.py
- **Priority**: P1 (security)
- **Reason**: Module-level shared Redis client ignored TLS settings.
- **Change**: Switched module-level Redis client to `redis_client.redis_from_url()`.

### sap-bridge/mqtt_publisher.py
- **Priority**: P1 (security)
- **Reason**: MQTT password was only read from environment variable; Redis connection ignored TLS; topic path components were not validated.
- **Change**: Read MQTT password from `MQTT_PASSWORD_FILE` secret with env fallback; switched Redis to `redis_from_url`; added `ALLOWED_TOPIC_SUFFIXES` and regex validation for `manufacturer`/`serial_number` to prevent topic injection.

### sap-bridge/heartbeat_monitor.py
- **Priority**: P1 (security)
- **Reason**: MQTT password was only read from environment variable; Redis connection ignored TLS.
- **Change**: Read MQTT password from `MQTT_PASSWORD_FILE` secret with env fallback; switched Redis to `redis_from_url`.

### sap-bridge/services/idoc_listener.py
- **Priority**: P0 (security)
- **Reason**: `xml.etree.ElementTree.fromstring()` parsed arbitrary IDoc XML with no entity/DTD restrictions, exposing XXE and XML bomb vulnerabilities.
- **Change**: Reject payloads larger than `MAX_IDOC_SIZE_BYTES` (1 MB default); reject any payload containing `<!DOCTYPE/ENTITY/ELEMENT/ATTLIST/NOTATION`; switched Redis to `redis_from_url`.

### sap-bridge/dispatch_queue/priority_queue.py
- **Priority**: P1 (security)
- **Reason**: Redis connection ignored TLS settings.
- **Change**: Switched to `redis_client.redis_from_url()`.

### sap-bridge/dispatch_queue/worker.py
- **Priority**: P1 (security)
- **Reason**: Worker Redis connection ignored TLS settings.
- **Change**: Switched to `redis_client.redis_from_url()`.

### sap-bridge/backends/ewm_backend.py
- **Priority**: P1 (security)
- **Reason**: CSRF token manager's Redis connection ignored TLS settings.
- **Change**: Switched lazy Redis initialization to `redis_client.redis_from_url()`.

### sap-bridge/main.py (additional)
- **Priority**: P1 (security)
- **Reason**: `dispatch_order`, `create_order`, and `robot_command` accepted arbitrary `manufacturer`/`serialNumber` values that were interpolated into MQTT topics, and did not detect publisher failures.
- **Change**: Added `_SAFE_ID_RE` validation helper and `_validate_robot_id_parts()`; applied validation in the three endpoints; return HTTP 502 when `publish()` returns `None`.

## Batch E — Watchdog Redis TLS, HTTP API auth, safe defaults

### watchdog/watchdog.py
- **Priority**: P1 (security)
- **Reason**: Watchdog Redis connection ignored TLS settings.
- **Change**: Added `rediss://` / `REDIS_SSL=true` detection in `RedisClient._connect()` with `ssl_cert_reqs`.

- **Priority**: P0 (security)
- **Reason**: Watchdog HTTP endpoints (`/metrics`, `/snapshots`, `/api/v1/alert/prometheus`) were unauthenticated.
- **Change**: Added `WATCHDOG_API_KEY`/`WATCHDOG_API_KEY_FILE` loading and `_check_auth()` requiring `X-API-Key` for all endpoints except `/health`.

- **Priority**: P1 (reliability)
- **Reason**: `do_POST()` read arbitrary `Content-Length` without a maximum, risking memory exhaustion.
- **Change**: Added `MAX_BODY_BYTES = 1 MB` limit and return HTTP 413 when exceeded.

- **Priority**: P2 (security hygiene)
- **Reason**: `OPS_PHONE` defaulted to placeholder `13800000000`.
- **Change**: Default changed to empty string so operators must configure a real contact.

## Batch F — v5.0 Traffic Coordinator input validation

### v5.0/traffic_coordinator_main.py
- **Priority**: P1 (security)
- **Reason**: `/ingest/{brand}` and `/order/{order_id}/cancel` accepted arbitrary path-derived identifiers; `_read_json()` had no body-size limit.
- **Change**: Added `_MAX_BODY_BYTES = 1 MB`; added `_SAFE_ID_RE` validation for `brand` and `order_id`; return HTTP 400 on invalid identifiers or oversized body.

---

## Batch G — Docker Compose secret/env wiring for new API keys and TLS flags

### docker-compose.yml
- **Priority**: P0 (security / operational)
- **Reason**: New `*_API_KEY_FILE` and `MQTT_PASSWORD_FILE` secrets were introduced in code but not declared/mounted in Compose, and new TLS env vars (`REDIS_SSL`, `ELASTICSEARCH_SSL`) were not passed to containers, so hardened settings would be ignored at runtime.
- **Change**: Declared `gateway_api_key`, `core_platform_api_key`, `sap_bridge_api_key`, `watchdog_api_key`, `mqtt_password` in top-level `secrets`; mounted them in `message-gateway`, `sap-bridge`, and `watchdog`; added `REDIS_SSL`/`REDIS_SSL_CERT_REQS` to `nodered`, `sap-bridge`, `watchdog`, and `message-gateway`; added `ELASTICSEARCH_SSL`/`ELASTICSEARCH_SSL_VERIFY` and API-key files to `message-gateway`; added MQTT TLS/auth env vars and `SAP_BRIDGE_API_KEY_FILE` to `sap-bridge`; added `WATCHDOG_API_KEY_FILE` to `watchdog`.

### docker-compose-v5.yml
- **Priority**: P0 (security / operational)
- **Reason**: v5.0 Traffic Coordinator gained `TC_API_KEY_FILE` and Redis TLS support but Compose did not expose them.
- **Change**: Added `TC_API_KEY_FILE=/run/secrets/tc_api_key`, `REDIS_SSL`, `REDIS_SSL_CERT_REQS` to `traffic-coordinator`; declared top-level `tc_api_key` secret and mounted it.

### .env.example
- **Priority**: P1 (security hygiene / documentation)
- **Reason**: New secrets/TLS settings had no discoverable configuration surface for operators.
- **Change**: Added `REDIS_SSL`, `REDIS_SSL_CERT_REQS`, `SAP_BRIDGE_API_KEY`, `SAP_BRIDGE_API_KEY_FILE`, MQTT TLS/auth vars, `ELASTICSEARCH_SSL`, `ELASTICSEARCH_SSL_VERIFY`, `GATEWAY_API_KEY`, `GATEWAY_API_KEY_FILE`, `CORE_PLATFORM_API_KEY`, `CORE_PLATFORM_API_KEY_FILE`, `WATCHDOG_API_KEY`, `WATCHDOG_API_KEY_FILE`, `TC_API_KEY`, `TC_API_KEY_FILE`.

### secrets/*.txt
- **Priority**: P1 (operational)
- **Reason**: Docker Compose secret mounts require files to exist; missing files would prevent services from starting.
- **Change**: Created empty placeholder files for `gateway_api_key.txt`, `core_platform_api_key.txt`, `sap_bridge_api_key.txt`, `watchdog_api_key.txt`, `mqtt_password.txt`, and `tc_api_key.txt`. Empty files keep authentication disabled until operators populate real keys.

---

## Batch H — Fix sap-bridge system_health regression after Watchdog auth

### sap-bridge/main.py
- **Priority**: P0 (reliability)
- **Reason**: After adding `X-API-Key` auth to Watchdog `/metrics`, the aggregated `system_health` endpoint in SAP Bridge could no longer retrieve watchdog metrics, leaving fleet/system health incomplete.
- **Change**: Added `WATCHDOG_API_KEY_FILE`/`WATCHDOG_API_KEY` loading and passed `X-API-Key` header in the internal `/metrics` HTTP request.

### docker-compose.yml
- **Priority**: P0 (operational)
- **Reason**: SAP Bridge needs the Watchdog API key secret to authenticate its internal health call.
- **Change**: Added `WATCHDOG_API_KEY_FILE` environment variable and mounted the `watchdog_api_key` secret in the `sap-bridge` service.

### .env.example
- **Priority**: P1 (documentation)
- **Reason**: New `WATCHDOG_API_KEY`/`WATCHDOG_API_KEY_FILE` settings for SAP Bridge were not documented.
- **Change**: Added entries under the SAP Bridge API authentication section.

---

## Batch I — Remove hardcoded credentials and unsafe defaults

### .env
- **Priority**: P0 (security)
- **Reason**: File contained real-looking credentials and placeholders for rescue phone, SAP host/user, notification webhooks, Node-RED admin password, and third-party API keys.
- **Change**: Cleared all sensitive fields so operators must configure real values; no defaults remain.

### .env.example
- **Priority**: P0 (security hygiene)
- **Reason**: Example/template still shipped with default passwords (`robot-platform-redis`, `robot-platform-es`, `admin`, `changeme_*`).
- **Change**: Emptied `REDIS_PASSWORD`, `ELASTIC_PASSWORD`, `NODE_RED_ADMIN_PASS`, `DIFY_DB_PASSWORD`, and removed password from `DB_URL`.

### redis/redis.conf
- **Priority**: P0 (security)
- **Reason**: Hardcoded `requirepass robot-platform-redis` committed to source control.
- **Change**: Removed the hardcoded password; password is now injected at container startup via `REDIS_PASSWORD`.

### docker-compose.yml
- **Priority**: P0 (security / operational)
- **Reason**: Default password fallbacks (`${REDIS_PASSWORD:-robot-platform-redis}`, `${ELASTIC_PASSWORD:-robot-platform-es}`, `${GRAFANA_ADMIN_PASSWORD:-admin}`, `${RESCUE_OPS_PHONE:-13800000000}`) allowed deployments to start with known credentials.
- **Change**: Removed all fallback defaults for Redis, Elasticsearch, Grafana admin password, and rescue ops phone; services now rely on operator-supplied environment variables.

### nodered/settings.js
- **Priority**: P0 (security)
- **Reason**: Hardcoded bcrypt hash for default admin password 'admin'.
- **Change**: `NODE_RED_ADMIN_PASS` is now required; Node-RED exits on startup if it is missing or empty.

- **Priority**: P1 (operational)
- **Reason**: Middleware treated every `POST` request as a protected path, blocking legitimate external webhook traffic (Feishu/DingTalk/WeChat) reaching Node-RED HTTP nodes.
- **Change**: Restricted IP whitelist to the explicit rescue API paths; general POST/webhook endpoints are no longer blocked by this middleware.

- **Priority**: P1 (reliability)
- **Reason**: SQLite audit logger inserted into `audit_log` table without ensuring the table exists, causing silent write failures on fresh deployments.
- **Change**: Added `CREATE TABLE IF NOT EXISTS audit_log` before each insert.

### mqtt/mosquitto.conf
- **Priority**: P0 (security)
- **Reason**: `allow_anonymous true` with auth/ACL commented out allowed any client to publish/subscribe.
- **Change**: Set `allow_anonymous false`, enabled `password_file` and `acl_file`, added packet-size/keepalive limits, and added commented TLS listener template.

### mqtt/passwd
- **Priority**: P1 (operational)
- **Reason**: Mosquitto `password_file` must exist; an empty file prevents startup failure while keeping authentication disabled until populated.
- **Change**: Replaced any prior content with a placeholder comment directing operators to run `mosquitto_passwd`.

---

## Batch J — Fix P0 runtime bugs

### core/coordinator.py
- **Priority**: P0 (correctness)
- **Reason**: `OrderStatus` and `ActionPrimitive` were referenced in `_fail_task`, `_mark_order_*`, `cancel_order`, and `_ensure_charging` but never imported, causing `NameError` at runtime on failure/completion transitions and charger dispatch.
- **Change**: Imported `OrderStatus` from `core.orders` and `ActionPrimitive` from `core.messages`.

### sap-bridge/main.py
- **Priority**: P0 (state consistency)
- **Reason**: `create_order` persisted the order and immediately marked it `ASSIGNED` before publishing via MQTT; if the broker rejected the message, the order stayed `ASSIGNED` but the robot never received it.
- **Change**: Persist in `CREATED`, publish first, and only transition to `ASSIGNED` after the broker accepts the message. On publish failure the order is marked `FAILED` with reason `mqtt_publish_failed`.



