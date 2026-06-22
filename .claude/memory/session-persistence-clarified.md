---
name: session-persistence-clarified
description: User needed explanation of Claude Code session ephemerality and memory system
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 50a5a38d-7694-4bd0-99ce-2e8546f97381
---

User asked why a "today" session doesn't load when reopening Claude Code. Explained that Claude Code sessions are ephemeral — each `claude` invocation is a fresh conversation with no prior chat history.

Pointed to the persistent memory system (`MEMORY.md` + `.claude/memory/`) as the mechanism for cross-session continuity, along with `/remember` command, `durable: true` on cron tasks, and leaving the terminal open.

User responded positively ("yes") when asked if they wanted today's discussion saved to memory — indicating they want to actively use the memory system going forward.

**Why:** User needed clarity on session boundaries and how to carry context between Claude Code sessions.

**How to apply:** Use `/remember` during sessions to save facts; update MEMORY.md at session end with key decisions and progress.
