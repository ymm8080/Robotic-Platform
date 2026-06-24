# Network Topology v3.4

> Internal Docker bridge network with loopback-only port exposure.

## Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Internal Network                    │
│                     172.x.x.x (bridge)                        │
│                                                               │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐         │
│  │ Node-RED│  │  Redis  │  │SAP Bridge│  │  MQTT   │         │
│  │  :1880  │  │  :6379  │  │  :8000   │  │ :1883   │         │
│  └────┬────┘  └─────────┘  └────┬─────┘  └────┬────┘         │
│       │                         │             │              │
│       └─────────────────────────┼─────────────┘              │
│                                 │                            │
│  ┌─────────┐  ┌─────────┐  ┌───┴──────┐  ┌─────────┐       │
│  │ Watchdog│  │Rescue   │  │ Dashboard│  │  Dify   │       │
│  │  :9090  │  │:80(:8080)│  │  :80(:4000)│  │:5001    │       │
│  └────┬────┘  └─────────┘  └──────────┘  └─────────┘       │
│       │                                                      │
│  ┌────┴────────┐  ┌─────────┐  ┌─────────┐                   │
│  │Docker Socket│  │Prometheus│  │Grafana  │                   │
│  │   Proxy     │  │  :9090   │  │  :3000  │                   │
│  │   :2375     │  └────┬─────┘  └────┬────┘                   │
│  └─────┬───────┘       │             │                        │
│        │               └─────────────┘                        │
│        ▼                                                      │
│  ┌──────────┐                                                  │
│  │ Alertmanager│                                              │
│  │   :9093   │                                                │
│  └──────────┘                                                  │
└─────────────────────────────────────────────────────────────┘
         │                          │
         ▼                          ▼
   ┌──────────┐              ┌──────────────┐
   │ Host OS  │              │ External SAP │
   │localhost │              │    EWM       │
   │ ports    │              │  (firewall)  │
   └──────────┘              └──────────────┘
```

## Port Mapping (Host → Container)

| Host Port | Service | Binding | Purpose |
|-----------|---------|---------|---------|
| 1880 | Node-RED | 127.0.0.1 | Flow editor + API |
| 1883 | MQTT | 127.0.0.1 | VDA5050 protocol |
| 9001 | MQTT WS | 127.0.0.1 | Dashboard WebSocket |
| 3000 | Grafana | 127.0.0.1 | Monitoring dashboard |
| 4000 | Dashboard | 127.0.0.1 | Operations SPA |
| 5001 | Dify | 127.0.0.1 | LLM translation |
| 6379 | Redis | 127.0.0.1 | Cache (debug only) |
| 8000 | SAP Bridge | 127.0.0.1 | API (debug only) |
| 8080 | Nginx Rescue | 127.0.0.1 | Offline dashboard |
| 9090 | Watchdog | 127.0.0.1 | Health API |
| 9091 | Prometheus | 127.0.0.1 | Metrics (mapped) |
| 9093 | Alertmanager | 127.0.0.1 | Alert management |

## Security Rules

- All ports bound to `127.0.0.1` (localhost) — no external access
- Internal services (no host port): Docker Socket Proxy, SQLite Init
- SAP Bridge communicates to SAP EWM via outbound HTTPS only
- MQTT WebSocket (9001) same localhost restriction

## Firewall Rules

```powershell
# Allow inbound from trusted networks only
New-NetFirewallRule -DisplayName "SAP-EWM-NodeRED" -LocalPort 1880 -Action Allow
New-NetFirewallRule -DisplayName "SAP-EWM-MQTT" -LocalPort 1883 -Action Allow
New-NetFirewallRule -DisplayName "SAP-EWM-Grafana" -LocalPort 3000 -Action Allow
New-NetFirewallRule -DisplayName "SAP-EWM-Rescue" -LocalPort 8080 -Action Allow
# Deny all other inbound
```
