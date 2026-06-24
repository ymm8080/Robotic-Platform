# Network Policy — Least Privilege per Service

> **Purpose:** Document the network access requirements for each service, ensuring least-privilege connectivity.
> **Ties to:** `01_architecture/diagrams/network-topology.md`, `docker-compose.yml`

## Service Network Matrix

```
Service          Exposed Ports     Internal Ports     Can Talk To           Inbound From
─────────────────────────────────────────────────────────────────────────────────────────────
Node-RED         :1880 (admin)     :1880              Redis, SAP Bridge,    Operator LAN
                                                    MQTT, Docker Proxy
Redis            :6379 (loopback)  :6379              —                     Node-RED, SAP Bridge
SAP Bridge       —                 :8000              Redis, SAP EWM/SAP    Node-RED
                                                    WM (external)
MQTT Broker      :1883, :9001      :1883, 9001        —                     Robots (external),
                                                                              Node-RED, SAP Bridge
Watchdog         :9090 (loopback)  :9090              Redis, Docker Proxy,   Operator LAN
                                                    Node-RED, SAP Bridge,
                                                    MQTT
Docker Proxy     :2375 (loopback)  :2375              Docker daemon         Watchdog only
Nginx Rescue     :8080             :80                —                      Operator LAN
Dify API         :5001 (loopback)  :5001              Redis, PostgreSQL     Node-RED
PostgreSQL       :5432 (loopback)  :5432              —                     SAP Bridge, Dify
```

## Firewall Rules

### External Access (Host Firewall)

| Direction | Source | Destination | Port | Protocol | Purpose | Rule |
|-----------|--------|-------------|------|----------|---------|------|
| Inbound | Operator LAN | Node-RED | 1880 | TCP | Admin UI | ALLOW |
| Inbound | Robot Fleet | MQTT Broker | 1883 | TCP | VDA5050 | ALLOW |
| Inbound | Robot Fleet | MQTT Broker | 9001 | TCP | VDA5050 WS | ALLOW |
| Inbound | Operator LAN | Nginx Rescue | 8080 | TCP | Monitoring | ALLOW |
| Inbound | Operator LAN | Watchdog | 9090 | TCP | Admin API | ALLOW |
| Inbound | — | Redis | 6379 | TCP | — | DENY (loopback) |
| Inbound | — | SAP Bridge | 8000 | TCP | — | DENY (internal) |
| Outbound | SAP Bridge | SAP EWM Server | 443 | TCP | OData | ALLOW |
| Outbound | SAP Bridge | SAP WM Server | 3300 | TCP | RFC (pyrfc) | ALLOW |
| All | — | — | — | — | Everything else | DENY |

### Internal Network (Docker Compose)

All services are on `internal` network. Network is `internal: false` to allow port mapping.

## Security Recommendations

1. **Move to separate networks** per security tier:
   ```
   frontend_net:  Nginx, Dashboard  (public-facing)
   control_net:   Node-RED, API     (operator access)
   backend_net:   SAP Bridge, DB    (internal only)
   robot_net:     MQTT              (robot-facing, isolated)
   ```

2. **Implement MQTT TLS** for all robot-to-broker communication (see `mqtt/mosquitto-tls.conf`)

3. **Rotate secrets monthly** (see `secrets-rotation.md`)

4. **Enable MQTT ACLs** for topic-level authorization

## Verification

```bash
# Check no service exposes unnecessary ports
docker compose ps --format "table {{.Names}}\t{{.Ports}}"

# Verify internal-only services are not externally reachable
curl -sf http://localhost:8000/health && echo "SAP Bridge exposed!" || echo "SAP Bridge internal-only ✓"
curl -sf http://localhost:6379/ping && echo "Redis exposed!" || echo "Redis internal-only ✓"
```
