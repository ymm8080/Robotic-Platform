---
name: reference-monitoring
description: REFERENCE directory change detection added to daily brief
metadata: 
  node_type: memory
  type: reference
  originSessionId: 055e432b-34d3-4fbe-941a-1335b73670b8
---

# REFERENCE Directory Change Detection

The `append-today-brief.ps1` script now monitors `D:/EWM ROBOT/REFERENCE/` for new/modified/deleted files.

**How it works:**
- Takes a filesystem snapshot (mtime + size) of all files in REFERENCE at each brief generation.
- Stores the snapshot in `.claude/reference-snapshot.json` (JSON array of `{path, mtime, size}`).
- Compares current state vs stored snapshot to detect:
  - New files (not in snapshot) → listed as CREATE
  - Modified files (mtime/size changed) → listed as MODIFY
  - Deleted files (in snapshot but gone) → listed as DELETE
- First run establishes baseline silently (no "new" entries).

**Brief output:**
- Overview table: Row "参考文档变更" (area key E).
- Detail section: Dedicated `## 参考文档变更` table after Phase sections.
- REFERENCE entries are excluded from PLAN.md phase grouping (they're external docs, not project work products).

**Script location:** `scripts/append-today-brief.ps1`
**Snapshot:** `.claude/reference-snapshot.json`

**Why:** REFERENCE directory holds project-critical VDA5050/SAP/robot specs outside the git repo — changes there are as important as in-repo changes for daily tracking.

**How to apply:** Snapshot is auto-managed. To force a fresh baseline, delete `.claude/reference-snapshot.json`.
