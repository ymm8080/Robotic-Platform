# ADR-007: v5.0 Core Platform Modules

**Status**: Proposed
**Date**: 2026-07-08
**Supersedes**: none (extends v4.1 VDA5050 platform, does not replace)

## Context

The v5.0 design (`Reference/Design - Core/01_架构白皮书_v5.0.md`) specifies a
fixed-lane + traffic-light scheduling architecture ("降维打击") layered as:
infrastructure → governance → application → core-scheduling → platform-services
→ adapter → physical. The existing repo is the v4.1 VDA5050 platform
(MQTT / Node-RED / sap-bridge). We need to land the v5.0 core functions
without a flag-day cutover.

## Decision

Introduce a new `core/` Python package implementing the v5.0 whitepaper's
core functions as discrete, testable modules — one per whitepaper layer /
core function (see `core/README.md` for the full map).

Principles applied:

1. **降维打击**: traffic-light FSM replaces dynamic replanning / elastic
   time-window negotiation. `TrafficLightController` is a deterministic
   fixed-cycle machine, not an Open-RMF negotiation.
2. **影子状态机是底线**: `ShadowStateMachine` independently tracks expected
   robot state; discrepancies → WORM. Circuit breaker trips after 3 SCS
   timeouts → hardcoded retreat (硬编码后退).
3. **双轨制安全距离**: dynamic formula `S = V·K_brake + RTT·V + C_static`
   with a non-overridable 1.5 m legal hard floor (`SafetyConfig.hard_floor`,
   GB/T 10827.1-2014).
4. **零信任治理**: `ReputationEngine` defaults unknown robots to 0.5;
   `EconomicModel` cost term (γ) is wired but disabled (γ=0) until 3 months
   of telemetry — interface reserved (灰犀牛 #14).
5. **因果存证**: `WormBlackbox` is append-only, hash-chained, 24h-rotated;
   `VersionRouter` provides N-1 compatibility to the v4.1 fabric.
6. **No wall-clock**: schedulers/liveness take an injected monotonic `now`,
   making the core deterministic and unit-testable without time mocks.

## Consequences

- **+** Every whitepaper core function has a home; each module is small,
  singly-responsibility, and unit-tested.
- **+** v4.1 and v5.0 coexist via the version router; rollout is incremental.
- **−** Transport (DDS), the platform tick loop, and dashboard wiring are
  out of scope here — they are the next milestone (阶段一 Exit Criteria).
- **−** TaskAllocator is greedy, not optimal — by design (whitepaper trades
  optimality for deterministic fixed-lane scheduling).

## Open items (技术债务登记簿, 附录A.2 style)

| Item | Reason | Upgrade trigger |
|---|---|---|
| NTP instead of PTP | budget | extend to dynamic collision avoidance |
| γ=0 economic model | needs telemetry | 3 months of run data |
| Greedy allocator | MVP | starvation / throughput SLA miss |
| DDS transport not wired | this milestone | 阶段一 survival exit |

## References

- `Reference/Design - Core/01_架构白皮书_v5.0.md`
- `Reference/Design - Core/02_Function_Spec_v5.0.md`
- `Reference/Design - Core/03_Runbook_v5.0.md`
- Open-RMF (scheduling patterns): https://github.com/open-rmf/rmf
