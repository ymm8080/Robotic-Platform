# ADR-004: Redis over PostgreSQL for Session & Real-Time State

**Status**: Accepted (v3.4)

**Date**: 2026-06-02

## Context

The platform needs to store:

- Robot session state (connection status, current order, position)
- Real-time pub/sub for inter-service messaging
- Ephemeral caching (inventory snapshots, SAP responses)
- Distributed state shared across Node-RED, SAP Bridge, Watchdog, and Dashboard

Options considered: PostgreSQL, Redis, SQLite (Node-RED default).

## Decision

Use **Redis 7** as the primary session store, cache, and pub/sub backbone. SQLite remains the persistent/durable store (Node-RED internal state, outbox table).

Rationale:

- **Low latency**: Redis operations complete in sub-millisecond — critical for real-time robot state updates arriving at 1-10 Hz per robot
- **TTL-based expiry**: Every key gets a TTL — prevents memory leaks naturally, unlike PostgreSQL where expired data must be cleaned up by cron jobs
- **Pub/sub built-in**: Redis pub/sub enables real-time event distribution (robot state changes, system alerts) without a separate message broker
- **Data structures**: Hashes (robot connection state), Sorted Sets (priority queue), Lists (command buffer) map directly to dispatch needs
- **Distributed**: Single Redis instance serves all services, providing a consistent view of robot state across the platform

## Consequences

**Positive**:
- Sub-millisecond read/write latency for robot state
- Automatic key eviction via TTL — no manual cleanup
- Pub/sub channels for real-time events reduce inter-service coupling
- Rich data structures simplify priority queue and state tracking implementation
- Connection state tracking with `EXPIRE` enables natural timeout detection

**Negative**:
- **Non-durable by default**: Redis is in-memory; persistent data requires SQLite/PostgreSQL (outbox, orders, configuration)
- **Memory-bound**: Total cache limited to 8GB maxmemory; eviction under pressure loses less-recently-used keys
- **Single-threaded**: Long-running commands block all other operations
- **No query language**: Complex queries or joins require application-level logic
- **Keyspace visibility**: No schema enforcement — key naming discipline is critical

**Mitigations**:
- RDB + AOF persistence enabled (appendfsync everysec) for crash recovery
- Max memory set to 8GB with `allkeys-lru` eviction policy
- Every key pattern documented with TTL matrix (see `05_reference/standards/redis-key-conventions.md`)
- Watchdog alerts at 75% memory usage; safe mode at 87%
- Key naming convention: `service:entity:identifier` (e.g., `robot:connection:KUKA-001`)
- Redis 7 `shutdown` saves RDB automatically for clean restarts

## Key Patterns

| Key Pattern | Type | TTL | Purpose |
|-------------|------|-----|---------|
| `robot:connection:{id}` | Hash | 300s | Connection state + last heartbeat |
| `robot:state:{id}` | Hash | 3600s | Last known state (position, battery) |
| `mqtt:seq:{topic}` | String | 86400s | Monotonic MQTT sequence number |
| `session:robot:{id}` | String | 3600s | Robot session data |
| `inventory:{location}` | String | 300s | Cached inventory snapshot |
| `sap:csrf_token` | String | 1500s | SAP CSRF token |
| `orders:queue` | Sorted Set | — | Order priority queue (no TTL, managed by app) |
| `nodered:*` | Varies | Varies | Node-RED externalized state |
