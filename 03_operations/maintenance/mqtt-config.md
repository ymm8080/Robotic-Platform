# MQTT Configuration Reference

> **Location:** `03_operations/maintenance/mqtt-config.md`
> **Last Updated:** 2026-06-22

## Broker Config

| Setting | Value | File |
|---------|-------|------|
| Image | eclipse-mosquitto:2 | docker-compose.yml |
| Port (MQTT) | 1883 (loopback) | docker-compose.yml |
| Port (WS) | 9001 (loopback) | docker-compose.yml |
| Node-RED reconnect | 15000ms (15s) | nodered/settings.js |
| Keep Alive | 60s | mosquitto.conf |
| Clean Session | false (connection topic) | mosquitto.conf |

## Topic Hierarchy (VDA5050)

```
uagv/v2/{manufacturer}/{serialNumber}/{messageType}
```

| Message Type | QoS | Retain | Purpose |
|-------------|-----|--------|---------|
| `connection` | 1 | true | Connection state (ONLINE/OFFLINE) |
| `state` | 0 | false | Robot position, battery, errors |
| `order` | 0 | false | Master → Robot route commands |
| `instantActions` | 0 | false | Cancel, pause, resume |
| `visualization` | 0 | false | High-freq position for UI |
| `factsheet` | 1 | true | Robot capabilities |

## LWT (Last Will & Testament)

Configured on all robot MQTT connections:

| Setting | Value |
|---------|-------|
| Topic | `vda5050/{manufacturer}/{serialNumber}/connection` |
| Payload | `{"state":"DISCONNECTED","timestamp":"<ISO8601>"}` |
| QoS | 1 |
| Retain | true |

When a robot disconnects unexpectedly, the broker publishes LWT automatically so the platform sees `DISCONNECTED` immediately.

## Mosquitto Config

```
listener 1883
allow_anonymous false
password_file /etc/mosquitto/passwd
max_inflight_messages 20
autosave_interval 900
persistence true
persistence_location /var/lib/mosquitto/
```

## Verification Commands

```bash
# Test connection
mosquitto_sub -t "vda5050/+/+/connection" -v

# Test publish
mosquitto_pub -t "vda5050/KUKA/KMR-001/state" -m '{...}'

# Monitor all robot traffic
mosquitto_sub -t "vda5050/+/+/#" -v
```
