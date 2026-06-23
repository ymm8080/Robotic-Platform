# ADR-005: Watchdog for Auto-Recovery

**Status**: Accepted (v3.4)

**Date**: 2026-06-02

## Context

The robot dispatch platform runs 24/7 in a production warehouse environment. Failures are inevitable and can occur at any hour. The platform must self-heal without requiring human intervention, especially outside business hours.

Key failure scenarios:
- Service crash (process dies, OOM killed)
- SAP connection loss (network, credential expiry, SAP maintenance)
- Redis memory exhaustion (key leak, excessive TTL)
- MQTT broker failure (broker crash, network partition)
- Resource exhaustion (CPU, memory on host)
- Cascading failure (one service overload triggers others)

## Decision

Implement a dedicated **Watchdog service** (Python) that continuously monitors all platform services and executes auto-recovery procedures.

Architecture:
1. Watchdog polls health endpoints on all services every 10s
2. Maintains service state in Redis (shared with other services)
3. Applies configurable thresholds to determine "healthy" vs "degraded" vs "critical"
4. Executes recovery actions: restart, throttle, safe mode, notify
5. Notifies operators via Feishu/WeCom when human intervention is required

## Consequences

**Positive**:
- **Self-healing**: Common failures (OOM crash, SAP timeout) are recovered automatically without operator
- **Safe mode**: When multiple services degrade, Watchdog sets a global "safe mode" flag in Redis — Node-RED throttles dispatch rates, preventing cascading overload
- **Centralized health view**: Single source of truth for system health across all services
- **Operator notification**: Feishu/WeCom alerts ensure operators know when human intervention is needed
- **Metrics export**: Health data available for Prometheus/Grafana integration

**Negative**:
- **Watchdog itself can fail**: Single point of failure in the recovery system (mitigated by Docker restart policy: `always`)
- **False positives**: Aggressive thresholds could trigger unnecessary recovery actions (mitigated by hysteresis: 3 consecutive failures before action)
- **Safe mode complexity**: Entering/exiting safe mode requires coordinated behavior across all services — must be tested thoroughly
- **Notification fatigue**: Too many alerts lead to ignored notifications (mitigated by severity-based alert routing)

**Mitigations**:
- Docker restart policy `always` on Watchdog container
- Watchdog monitors itself via `/health` endpoint
- Hysteresis: 3 consecutive check failures before declaring a service unhealthy
- Configurable thresholds loaded from `watchdog/config.yaml` — no code change needed
- Alert severity: WARNING (notification only) → CRITICAL (auto-recovery) → FATAL (human required)
- Notification rate limiting: max 1 alert per service per 5 minutes

## Thresholds

| Service | Warning | Critical | Action |
|---------|---------|----------|--------|
| Node-RED CPU | >70% | >85% | Throttle |
| Node-RED Memory | >512MB | >768MB | Safe mode |
| Node-RED Checkpoint | >2000 | >5000 | Safe mode |
| SAP Bridge Error Rate | >5% | >15% | Degrade |
| Redis Memory | >6GB (75%) | >7GB (87%) | Safe mode |
| System CPU | >80% | >90% | Notify |

## Recovery Actions

1. **Restart**: Docker restart of unhealthy container (up to 3 attempts)
2. **Throttle**: Reduce message rate in Node-RED (set `throttle:active` in Redis)
3. **Safe mode**: Global slowdown — all dispatch paused, only monitoring active
4. **Notify**: Feishu/WeCom message to on-call operator
5. **Escalate**: If recovery fails 3 times → FATAL alert, keep service down for human intervention
