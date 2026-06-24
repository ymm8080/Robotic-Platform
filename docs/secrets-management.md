# Secrets Management Guide v3.4

> Approved locations and procedures for all sensitive credentials.

## Approved Secret Locations

| Secret | Location | Mechanism | Git Status |
|--------|----------|-----------|------------|
| SAP Password | `secrets/sap_password.txt` | Docker Secrets → /run/secrets/sap_password | `.gitignore` |
| Dify DB Password | `.env` → `DIFY_DB_PASSWORD` | Environment variable | `.gitignore` |
| Feishu Webhook | `.env` → `FEISHU_WEBHOOK_URL` | Environment variable | `.gitignore` |
| WeCom Webhook | `.env` → `WECOM_CORP_ID` etc. | Environment variable | `.gitignore` |
| Grafana Password | `.env` → `GRAFANA_ADMIN_PASSWORD` | Environment variable | `.gitignore` |

## Verification

```bash
grep -rn "password\|secret\|PASSWORD\|SECRET" \
  --include="*.{yml,yaml,js,ts,py,json,env,txt,md,conf}" \
  --exclude-dir={.git,node_modules,secrets,__pycache__} .
```

## Policies

1. **Never commit real secrets** — all secrets in `.gitignore`
2. **Use Docker Secrets** for file-based secrets (SAP password)
3. **Use .env** for API URLs/tokens (Feishu, WeCom)
4. **Rotate SAP password monthly** — update `secrets/sap_password.txt` + restart sap-bridge
5. **No secrets in Dockerfiles** — volumes and env vars only
6. **No secrets in MQTT payloads** — VDA5050 metadata only
