# Firewall Rules

> **Location:** `03_operations/deployment/firewall-rules.md`
> **Last Updated:** 2026-06-22

## Host Firewall (Windows)

### Required Open Ports

| Port | Protocol | Service | Source IP | Purpose |
|------|----------|---------|-----------|---------|
| 1880 | TCP | Node-RED | Ops LAN (10.x.x.x) | Orchestration UI |
| 8080 | TCP | Nginx Rescue | Ops LAN (10.x.x.x) | Offline dashboard |
| 1883 | TCP | MQTT | Robot VLAN | VDA5050 messages |
| 9001 | TCP | MQTT WS | Robot VLAN | MQTT WebSocket |
| 6379 | TCP | Redis | Localhost only | Cache/session |
| 5432 | TCP | PostgreSQL | Localhost only | SQLite not in use |

### Internal (Docker Network)

All inter-service communication uses Docker internal network — no host firewall rules needed:

| Service | Port | Access |
|---------|------|--------|
| SAP Bridge | 8000 | Internal only (no host mapping) |
| Watchdog | 9090 | Internal + Ops LAN |
| Dify API | 5001 | Internal only |

## Windows Firewall Commands

```powershell
# Open MQTT port for robot VLAN
New-NetFirewallRule -DisplayName "MQTT 1883" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow

# Open Node-RED for ops LAN only
New-NetFirewallRule -DisplayName "Node-RED 1880" -Direction Inbound -Protocol TCP -LocalPort 1880 -RemoteAddress 10.0.0.0/8 -Action Allow

# Verify rules
Get-NetFirewallRule | Where-Object { $_.DisplayName -match "MQTT|Node-RED|Rescue" } | Format-Table
```

## Security Notes

- **Never expose** Redis (6379), PostgreSQL (5432), or Docker Socket to host network
- MQTT port 1883 should be restricted to robot VLAN only
- Node-RED (1880) and Rescue Dashboard (8080) should be ops-LAN only
- Consider MQTT TLS (8883) for production deployments
