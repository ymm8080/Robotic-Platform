# ADR-003: Outbox Pattern for SAP EWM Synchronization

**Status**: Accepted (v3.4)

**Date**: 2026-06-02

## Context

The platform must synchronize robot dispatch events (order completions, state changes, inventory movements) back to SAP EWM. SAP imposes:

- Rate limiting: ~100 requests/minute (safe limit: 80/min)
- Variable latency: OData responses can take 2-30s depending on SAP load
- Occasional downtime: Planned maintenance windows, network interruptions
- No built-in retry: Failed requests return errors that must be handled by the caller

Direct synchronous calls risk data loss during SAP unavailability or rate limit backpressure.

## Decision

Use the **Outbox Pattern** for all SAP write operations.

Pattern flow:
1. Application writes to local SQLite (atomic transaction)
2. Outbox INSERT in the same transaction
3. Async worker picks up pending outbox rows
4. Worker calls SAP with exponential backoff on failure
5. On success: mark outbox row as `completed`
6. On max retries exhausted: move to `deadletter` and alert

## Consequences

**Positive**:
- **Guaranteed eventual consistency**: SAP writes survive crashes — if the app dies after the DB write but before the SAP call, the outbox worker picks it up on restart
- **Rate limiting decoupled**: Outbox worker queues requests at a controlled rate (max 80/min), independent of application request volume
- **Backpressure isolation**: SAP slowness/downtime does not block the application — writes queue in outbox
- **Audit trail**: Every SAP write is logged in the outbox table with timestamps, retry count, and error context
- **Idempotency**: Outbox rows carry unique IDs; SAP can deduplicate on its side

**Negative**:
- **Eventual ≠ immediate**: There is a window (typically 1-5s, up to 60s under retry) between application write and SAP confirmation
- **Deadletter management**: Items that exhaust retries require manual review and reprocessing
- **Storage growth**: Outbox table grows with write volume; requires periodic archiving or cleanup
- **Monitoring overhead**: Must monitor outbox backlog depth, deadletter count, and processing latency

**Mitigations**:
- Watchdog alerts on outbox backlog > 100 items
- Deadletter items surfaced via API for manual retry
- Outbox archival job runs weekly (configurable)
- Outbox status exposed on `/health` endpoint

## Compliance

- Outbox table in SQLite: `CREATE TABLE outbox (id, target, payload, status, retry_count, error, created_at, updated_at)`
- Status values: `pending` → `processing` → `completed` | `deadletter`
- Max retries: 5
- Backoff schedule: 1s, 2s, 4s, 8s, 16s, 60s (cap)
- All SAP writes go through outbox — no direct synchronous SAP calls outside read operations
