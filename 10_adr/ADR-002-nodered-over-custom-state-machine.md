# ADR-002: Node-RED over Custom State Machine for Dispatch Orchestration

**Status**: Accepted (v3.4)

**Date**: 2026-06-02

## Context

The platform needs an orchestration engine to manage robot dispatch workflows: receive SAP warehouse tasks, map to VDA5050 orders, monitor execution, handle errors and retries.

Options considered: Custom state machine (Python/TypeScript), Apache NiFi, Node-RED.

## Decision

Use **Node-RED 3.1.9** as the visual orchestration engine.

Rationale:

- **Operations team autonomy**: The on-site operations team can modify dispatch flows visually without writing code — critical for a manufacturing environment where IT support may not be immediately available
- **Built-in MQTT integration**: Native MQTT in/out nodes with QoS support, zero additional code
- **Rapid prototyping**: Flow-based programming enables faster iteration on dispatch logic than a custom state machine
- **Ecosystem**: 5,000+ community nodes cover HTTP, Redis, SQLite, schedule, and alert nodes needed by the platform
- **Low learning curve**: Operations staff with basic automation experience can read and modify flows

## Consequences

**Positive**:
- Dispatch logic is visual and auditable — no hidden code paths
- Flows can be modified at runtime (no redeploy for logic changes)
- Built-in dashboard UI for monitoring flow execution
- Git-trackable flow exports (JSON format) for version control

**Negative**:
- Performance ceiling: Node-RED is single-threaded; high-throughput scenarios (>500 msg/s) require horizontal partitioning
- Large in-memory context data (>1MB) must be externalized to Redis to avoid OOM
- Error handling is per-node — missing error handlers easily cause silent failures (mitigated by audit rules in `010-nodered-core.mdc`)
- Flow complexity grows with scale; poorly organized flows become unmaintainable

**Mitigations**:
- State externalization: All context data >100KB stored in Redis, not Node-RED memory
- Mandatory error handlers: Every flow must have a catch-all handler (enforced by `010-nodered-core.mdc`)
- Flow versioning: Auto-export flows to `nodered/flows/` on startup
- Memory monitoring: Watchdog alerts when Node-RED memory exceeds 512MB
- Subflow library: Reusable patterns extracted to `nodered/subflows/` for consistency

## Compliance

- Node-RED 3.1.9 LTS
- Flows exported as JSON, tracked in git
- No `eval()` or dynamic function nodes in production flows
