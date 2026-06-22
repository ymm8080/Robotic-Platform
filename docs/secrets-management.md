# Secrets Management

**Last Updated**: 2026-06-21

## Approved Secret Locations

| Secret | Storage | Load Path | Managed In |
|--------|---------|-----------|------------|
| SAP password | `secrets/sap_password.txt` | Docker Secret → `/run/secrets/sap_password` | `.env` → `docker-compose.yml` |
| Dify DB password | `.env` variable `DIFY_DB_PASSWORD` | Environment variable | `.env` |
| Feishu webhook | `.env` variables | Environment variable | `.env` |
| WeCom webhook | `.env` variables | Environment variable | `.env` |

## Rules

1. **Never** put passwords in source code files (`.ts`, `.py`, `.js`, `.yml` directly)
2. **Never** commit `secrets/` directory (blocked by `.gitignore`)
3. **Never** commit `.env` file (blocked by `.gitignore`)
4. **Always** use Docker Secrets for production credentials (mount at `/run/secrets/`)
5. **Always** copy `.env.example` to `.env` and fill real values — never edit `.env.example`

## Rotation

- SAP password: monthly (set calendar reminder)
- API tokens: when compromised or quarterly

## Verification

```bash
# Check no secrets in code
grep -rn "password\|secret" --include="*.{yml,ts,js,py,env}" \
  --exclude-dir={.git,node_modules,secrets} .

# Verify Docker secrets loaded
docker exec robot-platform-sap-bridge cat /run/secrets/sap_password
```
