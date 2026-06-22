# MQTT Last Will & Testament (LWT) Configuration

**Last Updated**: 2026-06-21

## Purpose
Detect unexpected robot disconnections. When a robot's MQTT connection drops without a graceful DISCONNECT, the broker publishes its LWT message automatically.

## Configuration

| Setting | Value |
|---------|-------|
| Topic | `vda5050/{manufacturer}/{serialNumber}/connection` |
| Payload | `{"state":"DISCONNECTED","timestamp":"<ISO8601>"}` |
| QoS | 1 (at least once) |
| Retain | true (so subscribers instantly see current state) |

## Implementation

### In sap-bridge (Python)
```python
client.will_set(
    topic=f"vda5050/{manufacturer}/{serialNumber}/connection",
    payload=json.dumps({"state": "DISCONNECTED", "timestamp": iso_now()}),
    qos=1,
    retain=True,
)
```

### In Node-RED
Set on the MQTT broker config node:
- **Will Topic**: `vda5050/{manufacturer}/{serialNumber}/connection`
- **Will Payload**: `{"state":"DISCONNECTED","timestamp":"${timestamp}"}`
- **Will QoS**: 1
- **Will Retain**: true

## Verification

```bash
# Subscribe to all connection events
mosquitto_sub -t "vda5050/+/+/connection" -v

# Kill a robot simulator → expect DISCONNECTED LWT within 30s
mosquitto_pub -t "vda5050/KUKA/KMR-001/connection" -m '{"state":"DISCONNECTED"}' -r
```
