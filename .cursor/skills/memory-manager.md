---
name: memory-manager
description: Manage AI memory systems - read, write, update, and prune cross-session memories. Works with Cursor, Qoder, and other AI assistants. Use when maintaining MEMORY.md, updating PROJECT_CONTEXT.md, or optimizing AI context for future sessions.
---

# Memory Manager

Manage persistent AI memory across sessions for the SAP EWM Robot Dispatch Platform.

## When to Use

- After completing significant work (new feature, bug fix, architecture decision)
- When discovering patterns, pitfalls, or workflows worth remembering
- At session end to capture learnings
- During weekly/monthly memory maintenance
- When user says "remember this", "update memory", "save this pattern"

## Memory Files

### PROJECT_CONTEXT.md (Project Context)
**Location**: Root of workspace  
**Purpose**: Current project state, architecture, active decisions  
**Size**: ~8KB (under 16K token limit)  
**Update Frequency**: When architecture changes
**Note**: Formerly CLAUDE.md, renamed to be IDE-agnostic

**Sections to Maintain**:
- System Architecture (components, directories)
- Critical Protocols (VDA5050, SAP integration)
- Development Standards
- Key Decisions (summary, link to ADRs)
- Active Development Areas
- Quick Reference (ports, commands)
- Anti-Patterns

### MEMORY.md (Cross-Session Memory)
**Location**: Root of workspace  
**Purpose**: Patterns, pitfalls, decisions, workflows, context  
**Size**: ~12KB (designed for efficient loading)  
**Update Frequency**: Every session with significant learnings

**Sections to Maintain**:
- Patterns (proven solutions with code examples)
- Pitfalls (mistakes with workarounds)
- Decisions (why we chose X over Y)
- Workflows (step-by-step procedures)
- Context (environment-specific knowledge)
- Session History (recent work summary)

## Operations

### Read Memory (Session Start)

```powershell
# Load project context
Get-Content PROJECT_CONTEXT.md

# Load cross-session memory
Get-Content MEMORY.md

# Check last update timestamp
(Get-Item MEMORY.md).LastWriteTime
```

**What to Look For**:
- Active patterns relevant to current task
- Recent pitfalls to avoid
- Current workflows to follow
- Environment context (versions, limits)

### Write Memory (Session End)

**Step 1: Identify What to Remember**

Ask yourself:
- Did I discover a non-obvious bug with a workaround? → Add to Pitfalls
- Did I find a solution that works reliably? → Add to Patterns
- Did I make an architecture decision with trade-offs? → Add to Decisions
- Did I repeat the same task 3+ times? → Add to Workflows
- Did environment context change? → Update Context

**Step 2: Format the Entry**

#### Pattern Format
```markdown
### Pattern XXX: [Title]
**Discovered**: YYYY-MM-DD  
**Applies To**: [Scope]  
**Pattern**: [One-line description]

```typescript
// WRONG: The bad approach
[code example]

// CORRECT: The proven solution
[code example]
```

**Why**: [Rationale]  
**Trade-off**: [What you gain vs what you sacrifice]
```

#### Pitfall Format
```markdown
### Pitfall XXX: [Title]
**Date**: YYYY-MM-DD  
**Symptom**: [What went wrong]  
**Root Cause**: [Why it happened]  
**Fix**: [How to solve it]

```[language]
[code showing fix]
```

**Lesson**: [Key takeaway]  
**Prevention**: [How to avoid in future]
```

#### Decision Format
```markdown
### Decision XXX: [Title]
**Date**: YYYY-MM-DD  
**ADR**: [ADR-XXX or "Pending"]  
**Decision**: [What we chose]  
**Why**: 
- [Reason 1]
- [Reason 2]

**Trade-offs**:
- ✅ Pro: [Benefit]
- ❌ Con: [Cost]

**Alternatives Considered**:
- [Option A] (rejected: [reason])
- [Option B] (rejected: [reason])
```

#### Workflow Format
```markdown
### Workflow XXX: [Title]
**Date**: YYYY-MM-DD  
**Trigger**: [When to use]  
**Steps**:
1. [Step 1 with commands if applicable]
2. [Step 2]
3. [Step 3]

**Verification**:
```bash
[Commands to verify success]
```

**Estimated Time**: [Duration]
```

**Step 3: Insert into MEMORY.md**

Use the `SearchReplace` tool to add entries in the appropriate section:
- Patterns → After existing patterns (increment number)
- Pitfalls → After existing pitfalls (increment number)
- Decisions → After existing decisions (increment number)
- Workflows → After existing workflows (increment number)
- Context → Update relevant subsection
- Session History → Add to top of list (newest first)

**Step 4: Update PROJECT_CONTEXT.md if Architecture Changed**

If you made architecture changes, update PROJECT_CONTEXT.md:
- New microservices
- Changed protocols
- Updated ports
- New development standards

**Step 5: Verify Update**

```powershell
# Verify file was updated
(Get-Item MEMORY.md).LastWriteTime

# Verify content (spot check)
Select-String -Path MEMORY.md -Pattern "Pattern XXX|Pitfall XXX"
```

### Prune Memory (Monthly Review)

**Step 1: Identify Candidates for Deletion**

Look for entries that are:
- Superseded by newer patterns
- Workarounds for bugs that are now fixed
- Decisions reversed by later ADRs
- Context for decommissioned services
- Older than 90 days with no recent references

**Step 2: Review Each Candidate**

```markdown
For each entry, ask:
1. Is this still true? (Check against current codebase)
2. Is this still relevant? (Check against active development areas)
3. Has this been referenced in the last 90 days?
4. Is there a newer entry that supersedes this?

If any answer is NO, mark for deletion.
```

**Step 3: Remove Obsolete Entries**

Use `SearchReplace` to delete obsolete entries. Keep the numbering sequential (don't leave gaps).

**Step 4: Update Review Date**

Update the "Last Updated" and "Next Review" dates at top of MEMORY.md.

## Memory Optimization

### Token Efficiency

Design memory for AI consumption (all assistants):
- ✅ Use code examples over prose
- ✅ Use bullet points over paragraphs
- ✅ Include verification commands
- ✅ Date-stamp all entries
- ❌ Avoid long narratives
- ❌ Avoid duplicate information
- ❌ Avoid outdated context

### Memory Hierarchy

**Tier 1: Always Load** (PROJECT_CONTEXT.md)
- Current architecture
- Active decisions
- Critical protocols
- Verification rules

**Tier 2: Load When Relevant** (MEMORY.md sections)
- Patterns (when implementing similar features)
- Pitfalls (when working in affected areas)
- Workflows (when trigger conditions match)

**Tier 3: Search On Demand** (Full MEMORY.md)
- Session history
- Older decisions
- Environment context

### Context Window Management

Total memory budget: **32K tokens** (25% of 128K context)
- PROJECT_CONTEXT.md: ~8K tokens
- MEMORY.md: ~12K tokens
- Active session: ~12K tokens reserved

If memory grows beyond budget:
1. Prune entries older than 90 days
2. Condense multiple related entries into one
3. Move detailed examples to separate reference files
4. Keep only summaries in MEMORY.md

## SAP EWM Context

### What to Remember for This Project

**VDA5050 Protocol**:
- State machine variations by robot brand
- Topic hierarchy conventions
- Message ordering requirements
- Action execution patterns

**SAP Integration**:
- OData rate limits (use 80/min, not 100)
- Outbox pattern for reliability
- Authentication requirements
- Known SAP quirks

**Infrastructure**:
- Service ports and dependencies
- Memory limits (Redis 8GB, Node-RED 2GB)
- Connection limits (MQTT 1000 concurrent)
- Backup schedules

**Team Practices**:
- Dual IDE synchronization (Cursor + Qoder)
- Verification before completion
- Compressed communication
- ADR requirement for changes

## Verification

After any memory operation:

```powershell
# 1. File exists
Test-Path PROJECT_CONTEXT.md
Test-Path MEMORY.md

# 2. Content is valid (not corrupted)
Get-Content PROJECT_CONTEXT.md | Select-String "SAP EWM"
Get-Content MEMORY.md | Select-String "Patterns|Pitfalls|Decisions"

# 3. File sizes are reasonable
(Get-Item PROJECT_CONTEXT.md).Length  # Should be < 16KB
(Get-Item MEMORY.md).Length  # Should be < 32KB

# 4. Both IDEs can read (if applicable)
# Memory files are IDE-agnostic, but verify if IDE-specific configs change
```

## Anti-Patterns

❌ **Don't** write memory entries without code examples  
❌ **Don't** duplicate information already in ADRs  
❌ **Don't** keep workarounds for fixed bugs  
❌ **Don't** exceed token budget without pruning  
❌ **Don't** write prose when code examples work  
❌ **Don't** forget to date-stamp entries  
❌ **Don't** update one file without checking the other  

## Examples

### Example: Remembering a New Pattern

```markdown
User: "I just figured out how to handle KUKA robot lifting actions"

AI (at session end):

"I'll add this to MEMORY.md as a new pattern.

[SearchReplace operation to insert Pattern 004 in MEMORY.md]

Verification:
- File updated: $(Get-Item MEMORY.md).LastWriteTime
- Pattern added: Pattern 004: KUKA Lifting Action Handler
- Applies to: Multi-brand robot dispatch

Saved to memory for future sessions."
```

### Example: Updating After Architecture Change

```markdown
User: "We're adding RabbitMQ alongside MQTT"

AI:

"I'll update PROJECT_CONTEXT.md to reflect the new architecture.

[SearchReplace operation to update Core Components section]

Verification:
- PROJECT_CONTEXT.md updated with RabbitMQ component
- Port 5672 added to Quick Reference
- Anti-pattern added: Don't bypass MQTT for VDA5050

Project context updated for future sessions."
```

## Quick Commands

```powershell
# Read current memory
Get-Content PROJECT_CONTEXT.md -Head 50
Get-Content MEMORY.md -Head 100

# Check last updates
(Get-Item PROJECT_CONTEXT.md).LastWriteTime
(Get-Item MEMORY.md).LastWriteTime

# Count entries
Select-String -Path MEMORY.md -Pattern "^### Pattern" | Measure-Object
Select-String -Path MEMORY.md -Pattern "^### Pitfall" | Measure-Object
Select-String -Path MEMORY.md -Pattern "^### Decision" | Measure-Object
Select-String -Path MEMORY.md -Pattern "^### Workflow" | Measure-Object

# Search for specific topic
Select-String -Path MEMORY.md -Pattern "VDA5050|SAP|Redis" -AllMatches
```

## Token Efficiency Note

Memory management costs ~200 tokens per session but saves 500-1000 tokens per rediscovered solution. This is a 2.5-5x efficiency gain.
