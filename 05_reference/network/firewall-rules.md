# Firewall Rules

**Last Updated**: 2026-06-21

## Host Firewall (Windows)

### Required Open Ports

| Port | Protocol | Service | Source IP | Purpose |
|------|----------|---------|-----------|---------|
| 1880 | TCP | Node-RED | Ops LAN (10.x.x.x) | Orchestration UI |
| 8080 | TCP | Nginx Rescue | Ops LAN (10.x.x.x) | Offline dashboard |
| 1883 | TCP | MQTT | Robot VLAN | VDA5050 messages |
| 9001 | TCP | MQTT WS | Robot VLAN | MQTT WebSocket |

### All Other Ports
- Redis (6379) — localhost only
- SAP Bridge (8000) — Docker internal only
- Watchdog (9090) — localhost only
- Dify (5001) — localhost only

### Windows Firewall Commands
```powershell
# Allow Node-RED from ops subnet
New-NetFirewallRule -DisplayName "Node-RED Ops Access" `
  -Direction Inbound -Protocol TCP -LocalPort 1880 `
  -RemoteAddress "10.0.0.0/8" -Action Allow

# Allow Nginx Rescue from ops subnet
New-NetFirewallRule -DisplayName "Nginx Rescue Ops Access" `
  -Direction Inbound -Protocol TCP -LocalPort 8080 `
  -RemoteAddress "10.0.0.0/8" -Action Allow

# Block everything else by default
# (Already handled by 127.0.0.1 bindings in docker-compose)
```
