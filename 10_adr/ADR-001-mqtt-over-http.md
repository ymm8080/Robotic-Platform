# ADR-001: MQTT over HTTP Polling for Robot Communication

**Status**: Accepted (v3.4)

**Date**: 2026-06-02

## Context

The platform needs to communicate with multiple brands of robots (KUKA KMR iiwa, MiR250, OTTO 1500) on the production floor. The communication protocol must support:

- Real-time state updates (position, battery, errors) from dozens of robots simultaneously
- Bidirectional command/response patterns
- Reliable message delivery with ordering guarantees
- Multiple robot brands adhering to VDA5050 specification

Options considered: HTTP polling, WebSocket, MQTT.

## Decision

Use **MQTT** (Mosquitto broker) as the primary robot communication protocol.

Rationale:

- **VDA5050 native**: The VDA5050 specification uses MQTT as its standard transport layer — any deviation breaks spec compliance
- **Publish/subscribe**: Robots publish state independently; subscribers (Node-RED, Watchdog, Dashboard) receive updates simultaneously without polling overhead
- **QoS levels**: MQTT QoS 1 ensures at-least-once delivery, critical for order commands
- **Last-Will-Testament**: MQTT LWT provides automatic DISCONNECTED detection when a robot drops off the network
- **Low latency**: Sub-100ms message delivery vs. HTTP polling latency (minimum poll interval creates a trade-off between freshness and load)

## Consequences

**Positive**:
- Real-time robot state updates without polling overhead
- Standardized topic hierarchy per VDA5050: `vda5050/{manufacturer}/{serialNumber}/...`
- Built-in connection state tracking via LWT
- Scalable: broker handles 100+ robot topics without client-side changes

**Negative**:
- Requires persistent MQTT connections from all consumers (Node-RED, SAP Bridge, Watchdog)
- Message ordering requires application-level sequence numbers (MQTT QoS > 0 may reorder)
- Broker becomes a single point of failure (mitigated by Docker restart policy + Watchdog health checks)
- WebSocket bridge needed for browser-based dashboard access

**Mitigations**:
- All publishers use QoS 1 with monotonically increasing `sequenceNumber` per topic
- `clean_session=false` + persistent clientId for durable subscriptions
- Watchdog monitors broker health; Docker auto-restart on crash
- MQTT WebSocket on port 9001 for browser clients

## Compliance

- VDA5050 v2.0.0 (primary), v1.1.0 (MiR fallback)
- Topic structure: `vda5050/{manufacturer}/{serialNumber}/{type}`
