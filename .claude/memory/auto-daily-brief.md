---
name: auto-daily-brief
description: Claude Code auto-generates daily brief with per-file explanations on Stop
metadata: 
  node_type: memory
  type: project
  originSessionId: 90aeadd3-f4d9-4406-a91d-55a05559c7a3
---

# Auto Daily Brief Mechanism

**How it works:**
1. **During session** — Claude writes structured context to `.claude/today-session-context.json`
2. **On each Stop** — `append-today-brief.ps1` runs via Stop hook, reads context + transcript + git diff, compiles `D:\EWM ROBOT\daily-briefs\claude-code-today-brief-YYYYMMDD.md`
3. **Overwrites daily file** — each Stop regenerates the day's brief with all session data

**Key files:**
- `scripts/append-today-brief.ps1` — Main generator script
- `.claude/today-session-context.json` — Context staging file (written by Claude)
- `.claude/settings.json` — Stop hook configured to run the script
- `D:\EWM ROBOT\daily-briefs\claude-code-today-brief-YYYYMMDD.md` — Output

**Requirements for Claude** — During session, maintain `.claude/today-session-context.json` with this schema:

```json
{
  "phases": [
    {
      "name": "Phase A — 项目规划与基础设施",
      "timeRange": "18:28-18:57",
      "summary": "项目规划与基础设施（PLAN.md、架构文档、SAP Bridge 源码）",
      "fileCount": 25,
      "files": [".claude/settings.json", "sap-bridge/main.py"],
      "highlights": ["PLAN.md 完整开发计划 10 章节", "SAP Bridge 源码框架搭建"],
      "subSections": [
        {
          "title": "项目根配置",
          "timeRange": "18:28",
          "summary": "",
          "files": [".claude/settings.json"],
          "nextActions": ["配置 CI/CD 流水线"]
        },
        {
          "title": "SAP Bridge 源码",
          "timeRange": "18:55-18:57",
          "summary": "共 8 个文件",
          "files": ["sap-bridge/mqtt_publisher.py", "sap-bridge/main.py"],
          "nextActions": []
        }
      ],
      "nextActions": ["部署到测试环境"]
    }
  ],
  "files": {
    "relative/path/file.js": {
      "action": "CREATE|MODIFY|REWRITE|DELETE",
      "brief": "Short one-liner description",
      "purpose": "Why it exists",
      "detail": "Key changes made",
      "functions": [
        { "name": "functionName", "description": "what it does" }
      ]
    }
  },
  "requests": [
    { "title": "Task title", "detail": "What was done" }
  ],
  "leftovers": [],
  "nextActions": []
}
```

**Critical rules:**
- Always update `files` entries when creating/modifying files
- If writing reference docs to `D:\EWM ROBOT\Reference\05_reference\`, add a `requests` entry describing what was created so today's brief includes it
- Reference docs are NOT in git — brief relies on `today-session-context.json` to track them
- Group files into `phases` — each logical work chunk is one phase
- Update `statistics` at end of session (or periodically)
- Add `keyFiles` for files someone would want to quick-reference
- All paths use forward slashes `/` (script normalizes `\` → `/`)

**Why:** [[ewm-robot-project-root]] — User needs clear per-file, per-function documentation without manually mapping changes
