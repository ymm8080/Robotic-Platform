---
name: ewm-robot-project-root
description: D:/EWM ROBOT/ROBOTIC PLATFORM CODES/ is the permanent project root for the SAP EWM robot dispatch platform
metadata: 
  node_type: memory
  type: project
  project: ewm-robot-dispatch
  originSessionId: 919dca46-8394-49b3-bc9c-89c4d8a3cef6
---

**Project Root**: `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/`

The parent `D:/EWM ROBOT/` contains design docs and other files, but `ROBOTIC PLATFORM CODES/` is the actual codebase with `docker-compose.yml`, microservices (sap-bridge, watchdog, nodered, mqtt, redis), AI configs (.cursor/, .qoder/), and all source code.

Key paths (absolute, project-root-relative):
- `.claude/settings.json` — project-scoped config
- `PLAN.md` — full development plan (427 lines)
- `docker-compose.yml` — 9-service stack definition
- `PROJECT_CONTEXT.md` — system architecture overview
- `MEMORY.md` — cross-session patterns/pitfalls/workflows
- `AGENTS.md` — AI agent configuration rules

**Why**: Clear separation between design docs (parent folder) and runnable code (this folder). All tooling, git, and AI configs live under the codebase root.

**How to apply**: Always start sessions from `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/`. Reference all file paths relative to this root. The `.claude/settings.json` already records this.
