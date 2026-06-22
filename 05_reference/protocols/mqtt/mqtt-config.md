# MQTT Configuration Reference

**Last Updated**: 2026-06-21

## Broker Config

| Setting | Value | File |
|---------|-------|------|
| Image | eclipse-mosquitto:2 | docker-compose.yml |
| Port (MQTT) | 1883 (loopback) | docker-compose.yml |
| Port (WS) | 9001 (loopback) | docker-compose.yml |
| Node-RED reconnect | 15000ms (15s) | nodered/settings.js |

## Topic Hierarchy (VDA5050)

```
vda5050/{manufacturer}/{serialNumber}/connection    # LWT + heartbeat
vda5050/{manufacturer}/{serialNumber}/state         # Robot state reports
vda5050/{manufacturer}/{serialNumber}/order         # Orders to robots
vda5050/{manufacturer}/{serialNumber}/instantActions  # Urgent commands
vda5050/{manufacturer}/{serialNumber}/visualization   # Optional viz data
```

## Required Settings

### QoS
- **All publishers**: QoS 1 (at least once delivery)
- **Why**: QoS 0 can lose messages under load; QoS 2 is unnecessary overhead

### Sequence Numbers
- Every VDA5050 message must include `sequenceNumber` (monotonically increasing per topic)
- Prevent out-of-order processing on subscribers
- Sequence number per unique topic path, stored in Redis via `INCR`

### Last Will & Testament
- Topic: `vda5050/{manufacturer}/{serialNumber}/connection`
- Payload: `{"state":"DISCONNECTED","timestamp":"<ISO8601>"}`
- Retain: true
- QoS: 1

## Node-RED MQTT Nodes

All MQTT output nodes in Node-RED flows must:
1. Set QoS = 1
2. Generate sequenceNumber before publish (use Redis INCR per topic)
3. Handle broker reconnect (auto, configured at 15s interval)
4. Log publish errors to Node-RED console

## Client IDs

Each MQTT client must use a unique, persistent `clientId` for session persistence:
- Node-RED: `robot-platform-nodered`
- SAP Bridge: `robot-platform-sap-bridge` (future)
- Watchdog: `robot-platform-watchdog`
- Robot simulators: `sim-{brand}-{serialNumber}`
