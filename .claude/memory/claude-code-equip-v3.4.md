---
name: claude-code-equip-v3-4
description: "Equipped project for Claude Code by populating domain skills, fixing gaps, and syncing reference docs"
metadata: 
  node_type: memory
  type: project
  originSessionId: f002e0a4-028a-452f-8a4c-b5f24a0b9e34
---

Equipped the project for Claude Code (not Cursor) as the primary IDE. This involved:

1. **Domain skills created in `.claude/skills/`** (22 files across 3 subdirs):
   - `architecture/` (5): VDA5050 adapter, event-driven outbox, Node-RED data boundary, human-loop notification matrix, compliance checklist
   - `implementation/` (10): lowcode patterns, debug interpretation, flow integrity check, schema migration, firmware OTA, data masking, LLM noise reduction, physical-digital friction, language boundary contract, API deviation tracking
   - `operations/` (7): rescue dashboard, docker infra patterns, notification traffic control, degradation drill SOP, cost budget sentinel, implementation roadmap, Node-RED git workflow

2. **Reference docs copied** from CURSOR 3.4 DOCS into `docs/` (7 files: 48h-checklist, architecture manifest, deploy guide, 3 appendices, checklist additions)

3. **Gaps fixed against v3.4 design**:
   - `.env` created from template
   - `secrets/sap_password.txt` created (placeholder)
   - `nodered/flows.json` created (4 tabs, 22 nodes)
   - `dify/.env` created (offline mode)
   - `settings.js` hardened: Git block for non-repo, expanded IP whitelist, password complexity
   - `init.sql` triggers protecting 180-day audit logs
   - `watchdog.py` enhanced: NTP drift detection, WeCom alert fallback
   - `crontab.example` for backup/cleanup scheduling
   - `.claude/mcp.json` cleaned (removed duplicates, 8 organized entries)

4. **Cursor artifacts removed** from `.cursor/skills/` (domain skills belong in `.claude/`)

**Why:** Project was originally designed for Cursor (`.cursor/` configs) but primary IDE is Claude Code (`.claude/` configs).

**How to apply:** Run `docker-compose up -d` after filling real credentials in `.env` and `secrets/sap_password.txt`.
