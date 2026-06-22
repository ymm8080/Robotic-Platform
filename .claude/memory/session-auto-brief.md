---
name: session-auto-brief
description: Startup hook automatically displays last session summary via show-session-brief.ps1
metadata: 
  node_type: memory
  type: reference
  originSessionId: fa63a679-26f2-437c-b8de-3a258523613b
---

SessionStart hook in `.claude/settings.json` now runs `scripts/show-session-brief.ps1` first. This reads `SESSION_STATUS.md` (written at last Stop event by `scripts/update-session-status.ps1`) and prints a visible summary to the terminal.

**Flow:**
1. Session ends → Stop hook → `update-session-status.ps1` reads transcript and writes `SESSION_STATUS.md`
2. Next session starts → SessionStart hook → `show-session-brief.ps1` reads `SESSION_STATUS.md` and prints it

`update-session-status.ps1` also improved to parse real transcript data (user messages, file changes, topics) instead of hardcoded template.

Related: [[session-persistence-clarified]]
