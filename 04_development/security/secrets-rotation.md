# Secrets Rotation Schedule

> **Purpose:** Ensure all credentials and secrets are rotated on a regular schedule to maintain security compliance.
> **Responsible:** Platform Ops Team

## Rotation Matrix

| Secret | Location | Rotation Interval | Last Rotated | Next Due | Method |
|--------|----------|-------------------|-------------|----------|--------|
| SAP Password | `secrets/sap_password.txt` | Monthly (30 days) | — | — | Manual update via SAP GUI + Docker secret restart |
| MQTT Passwords | `mqtt/passwd` | Quarterly (90 days) | — | — | `mosquitto_passwd -b passwd <user> <new-pwd>` |
| Grafana Admin | `GF_SECURITY_ADMIN_PASSWORD` env | Quarterly (90 days) | — | — | Update `.env` + `docker compose restart grafana` |
| Dify DB Password | `DIFY_DB_PASSWORD` in `.env` | Quarterly (90 days) | — | — | Update `.env` + restart Dify |
| API Keys (Feishu, WeCom) | `.env` variables | Bi-annual (180 days) | — | — | Regenerate in admin console + update `.env` |
| TLS Certificates | `mqtt/certs/` | Annual (365 days) | — | — | Run `scripts/generate-mqtt-certs.sh` |
| SSH Keys (deploy) | CI/CD secrets | Annual (365 days) | — | — | Generate new key pair, update GitHub secrets |

## Procedure

### SAP Password Rotation (Monthly)
```bash
# 1. Update password in SAP GUI
# 2. Write to secrets file
echo -n 'new-sap-password' > secrets/sap_password.txt
# 3. Restart sap-bridge to pick up new secret
docker compose restart sap-bridge
# 4. Verify connection
curl -f http://localhost:8000/api/v1/sap/health
```

### MQTT Password Rotation (Quarterly)
```bash
# 1. Generate new password
mosquitto_passwd -b mqtt/passwd robot-platform '<new-password>'
# 2. Restart MQTT
docker compose restart mqtt
# 3. Verify MQTT connectivity
mosquitto_pub -t "healthcheck" -m "test" -r
```

### TLS Certificate Rotation (Annual)
```bash
# 1. Generate new certs
bash scripts/generate-mqtt-certs.sh
# 2. Replace mosquitto.conf with mosquitto-tls.conf
# 3. Mount certs volume (add to docker-compose.yml)
# 4. Restart MQTT
docker compose restart mqtt
# 5. Verify TLS connection
mosquitto_sub -h localhost -p 8883 --cafile mqtt/certs/ca.crt -t "vda5050/+/+/connection" -v
```

## Monitoring

- Watchdog alert: `SecretExpiryWarning` — 14 days before rotation due
- Check remaining days:
  ```bash
  NEXT_ROTATION=$(date -d "2026-07-24" +%s)  # SAP password next due
  DAYS_LEFT=$(( (NEXT_ROTATION - $(date +%s)) / 86400 ))
  echo "SAP password expires in $DAYS_LEFT days"
  ```

## Compliance

- Audit log must record every password rotation: who, when, which secret
- Rotations outside schedule must be documented with reason
- Emergency rotation: < 1 hour from decision to completion
- Use Docker Secrets (not env vars) for all credentials where possible

## References

- Docker Secrets: `docs/secrets-management.md`
- MQTT TLS: `mqtt/mosquitto-tls.conf`
- Cert generation: `scripts/generate-mqtt-certs.sh`
