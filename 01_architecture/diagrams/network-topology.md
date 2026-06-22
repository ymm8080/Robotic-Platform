# Network Topology

**Date**: 2026-06-21

## Architecture

```
                            Host Machine (Windows)
  ╔═══════════════════════════════════════════════════════════╗
  ║                    Docker Bridge Network                   ║
  ║                   172.x.x.x (internal)                    ║
  ║                                                           ║
  ║  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ║
  ║  │  Redis   │  │ SAP Br.  │  │Docker P. │  │ SQL Init │  ║
  ║  │  :6379   │  │  :8000   │  │  :2375   │  │(once)    │  ║
  ║  │ loopback │  │ (no port)│  │ (int.)   │  │ (no port)│  ║
  ║  └────┬─────┘  └──────────┘  └────┬─────┘  └──────────┘  ║
  ║       │              │            │                       ║
  ║  ┌────┴──────────────┴────────────┴──────────────────┐    ║
  ║  │               Docker internal network              │    ║
  ║  └───────────────────────────────────────────────────┘    ║
  ║       │              │            │                       ║
  ║  ┌────┴─────┐  ┌────┴─────┐  ┌───┴────────┐             ║
  ║  │ Node-RED │  │  MQTT    │  │  Watchdog  │             ║
  ║  │  :1880   │  │  :1883   │  │  :9090     │             ║
  ║  │ ALL net  │  │ loopback │  │  loopback  │             ║
  ║  └──────────┘  └──────────┘  └────────────┘             ║
  ║       │                                                 ║
  ║  ┌────┴──────────┐                                      ║
  ║  │ Nginx Rescue  │                                      ║
  ║  │  :8080        │                                      ║
  ║  │  ALL net      │                                      ║
  ║  └───────────────┘                                      ║
  ╚═══════════════════════════════════════════════════════════╝
```

## Port Exposure Audit

| Service | Port | Binding | Exposed To | Risk |
|---------|------|---------|------------|------|
| Node-RED | 1880 | **0.0.0.0** | All interfaces | ⚠️ Should be `127.0.0.1` or restricted |
| Redis | 6379 | `127.0.0.1` | Localhost only | ✅ Secure |
| SAP Bridge | 8000 | No port map | Docker internal only | ✅ Secure |
| Dify | 5001 | `127.0.0.1` | Localhost only | ✅ Secure |
| MQTT | 1883 | `127.0.0.1` | Localhost only | ✅ Secure |
| MQTT WS | 9001 | `127.0.0.1` | Localhost only | ✅ Secure |
| Nginx Rescue | 8080 | **0.0.0.0** | All interfaces | ⚠️ Should be `127.0.0.1` or restricted |
| Watchdog | 9090 | `127.0.0.1` | Localhost only | ✅ Secure |

## ⚠️ Findings

### Issue 1: Node-RED binds all interfaces
`docker-compose.yml` line 18: `- "${NODE_RED_EXTERNAL_PORT:-1880}:1880"`
- No `127.0.0.1` prefix → accessible from any device on the network
- **Fix**: Change to `"127.0.0.1:${NODE_RED_EXTERNAL_PORT:-1880}:1880"` if ops team accesses via localhost only
- **If ops need remote access**: Add firewall rule restricting to ops IP range

### Issue 2: Nginx Rescue binds all interfaces  
`docker-compose.yml` line 285: `- "8080:80"`
- Same issue — dashboard accessible from any network device
- **Fix**: Change to `"127.0.0.1:8080:80"` or restrict with firewall

### Issue 3: Network `internal: false`
`docker-compose.yml` line 509: `internal: false`
- This is intentional (allows port mapping to host), but worth documenting why
- The `internal: false` means containers can reach each other AND the host
- With `internal: true`, port mapping still works but inter-container traffic is isolated

## Recommendations

1. Add `127.0.0.1:` prefix to Node-RED and Nginx port mappings
2. If remote access needed, add explicit `iptables`/Windows Firewall rules
3. Document whitelist IP ranges in `05_reference/network/firewall-rules.md`
4. Consider setting `internal: true` if inter-container isolation needed
