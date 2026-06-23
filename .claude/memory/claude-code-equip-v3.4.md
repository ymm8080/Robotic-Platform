---
name: claude-code-equip-v3-4
description: "Equipped project for Claude Code by populating domain skills, fixing gaps, and syncing reference docs"
metadata: 
  node_type: memory
  type: project
  originSessionId: f002e0a4-028a-452f-8a4c-b5f24a0b9e34
---

Equipped the project for Claude Code (not Cursor) as the primary IDE. This involved:

1. **Domain skills created in `.claude/skills/`** — 22 files created, then 15 absorbed into rules/memory, 7 retained as skills:
   - `architecture/` (2 retained): vda-5050-adapter-design (strategy pattern), node-red-data-boundary (throttling thresholds)
   - `implementation/` (2 retained): robot-firmware-ota (OTA control flow), schema-migration-automation (migration steps)
   - `operations/` (3 retained): degradation-drill-sop (3/7/14 drills), nodered-git-workflow (branch strategy), rescue-dashboard (degradation recovery)

   **15 absorbed into rules/memory** (skills files deleted, content lives in rules that auto-load):
   - `010-nodered-core.mdc` → language-boundary, flow-integrity, LLM-noise, lowcode-patterns, data-masking
   - `030-robot-device.mdc` → physical-digital-friction, robot-api-deviation-tracking
   - `060-db-and-outbox.mdc` → event-driven-outbox
   - `080-enterprise-policies.mdc` → notification-matrix, compliance-checklist, notification-traffic-control
   - `090-operational-limits.mdc` → node-red-data-boundary (merged), cost-budget-sentinel, docker-infra-patterns
   - `memory/` → nodered-debug-interpretation, implementation-roadmap, rescue-dashboard

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
