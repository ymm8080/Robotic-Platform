---
name: llm-wiki
description: Personal knowledge base in Obsidian format. Build a searchable wiki of project decisions, patterns, and solutions.
---

# LLM Wiki - Personal Knowledge Base

Build and maintain a personal knowledge base in Obsidian format for the SAP EWM → Robot Dispatch Platform project.

## Wiki Structure

```
00_inbox/           # Quick notes, unprocessed ideas
01_architecture/    # System design, ADRs, diagrams
02_deployment/      # Deploy guides, environment configs
03_operations/      # Runbooks, monitoring, alerts
04_development/     # API docs, coding standards
05_reference/       # SAP docs, VDA5050 protocol specs
06_meetings/        # Meeting notes, decisions
07_troubleshooting/ # Known issues, solutions, debugging guides
```

## Note Templates

### Architecture Decision Record (ADR)

```markdown
---
id: ADR-XXX
status: accepted
date: YYYY-MM-DD
tags: [architecture, decision, sap-ewm]
---

# ADR-XXX: [Title]

## Context
[What is the issue that we're seeing?]

## Decision
[What is the change that we're proposing?]

## Consequences
[What becomes easier or more difficult to do because of this change?]

## Alternatives Considered
[What other approaches did we consider?]
```

### Troubleshooting Guide

```markdown
---
issue: [Brief description]
severity: [critical/high/medium/low]
component: [affected component]
tags: [troubleshooting, bug, fix]
---

# [Issue Title]

## Symptoms
- [What does the problem look like?]

## Root Cause
[What is causing the issue?]

## Solution
[How to fix it]

## Prevention
[How to avoid this in the future]

## Related Issues
- [Link to related troubleshooting docs]
```

### Pattern Documentation

```markdown
---
pattern: [Pattern name]
category: [design/architectural/behavioral]
tags: [pattern, best-practice]
---

# [Pattern Name]

## Intent
[What does this pattern solve?]

## When to Use
[In what situations is this pattern applicable?]

## Implementation
[How is this pattern implemented in our system?]

## Examples
[Code examples from the codebase]

## Related Patterns
- [Link to related patterns]
```

## Knowledge Capture Workflow

### 1. Capture (During Work)
- Quick notes in `00_inbox/`
- Tag with relevant topics
- Don't worry about format yet

### 2. Process (End of Session)
- Move notes from inbox to appropriate folders
- Add proper frontmatter and tags
- Link to related notes

### 3. Connect (Weekly Review)
- Add bidirectional links between related notes
- Create MOC (Map of Content) files
- Identify emerging patterns

## SAP EWM Wiki Topics

### Must-Document Topics
- VDA5050 state machine transitions
- SAP OData API integration patterns
- Robot fleet management logic
- MQTT message routing
- Order dispatch workflows
- Error handling strategies
- Security/authentication flows
- Database schema decisions

## Obsidian Plugins

### Recommended Plugins
- **Dataview**: Query your notes
- **Templater**: Auto-generate note templates
- **Calendar**: Link notes to dates
- **Tag Wrangler**: Manage tags efficiently
- **Obsidian Git**: Version control your wiki

## Best Practices

✅ **Do:**
- Write notes in your own words
- Link heavily between related notes
- Use tags consistently
- Review and update regularly
- Include code examples
- Document WHY, not just WHAT

❌ **Don't:**
- Copy-paste documentation without context
- Leave notes untagged
- Wait too long to process inbox notes
- Over-engineer the structure
- Forget to link back to source code

## Search & Retrieval

### Common Queries
```
tag:#troubleshooting AND tag:#sap-ewm
file:"ADR" AND status:"accepted"
link:[[VDA5050_State_Machine]]
```

## Maintenance

### Daily
- Capture quick notes in inbox
- Tag new information

### Weekly
- Process inbox to proper folders
- Add bidirectional links
- Update stale notes

### Monthly
- Review ADR statuses
- Clean up unused tags
- Identify knowledge gaps
- Update Maps of Content
