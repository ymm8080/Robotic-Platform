---
name: grill-with-docs
description: Run a grilling session that updates documentation inline. Ensures docs stay synchronized with implementation decisions.
---

# Grill With Docs

Before implementing any significant change, ask clarifying questions AND update documentation simultaneously.

## Process

### 1. Clarify Requirements

Ask the same questions as `grill-me`:
1. **What is the actual problem being solved?** (Not what the user _says_ they want)
2. **What are the edge cases?** (What could go wrong?)
3. **Is there a simpler approach?** (Are we over-engineering?)
4. **What are the consequences?** (Performance, security, maintainability)

### 2. Document Decisions Inline

For every decision made during the grilling session:

**Update relevant files:**
- ADR (Architecture Decision Records) in `10_adr/`
- Component documentation in `01_architecture/components/`
- Runbooks in `03_operations/runbooks/`
- README files in affected directories

**Format:**
```markdown
## Decision: [Title]
- **Date**: YYYY-MM-DD
- **Context**: Why this decision was needed
- **Decision**: What we decided
- **Consequences**: What this means going forward
- **Alternatives Considered**: What else we looked at
```

### 3. Verify Documentation Completeness

Before starting implementation, verify:
- [ ] All decisions documented in ADR format
- [ ] Component docs updated with new interfaces
- [ ] Runbooks updated with new operational procedures
- [ ] Architecture diagrams updated if structure changed
- [ ] API documentation updated if endpoints changed

## SAP EWM Context

For SAP EWM → Robot Dispatch Platform decisions:
- Document VDA5050 message format changes in `01_architecture/components/`
- Update SAP OData integration patterns in `05_reference/sap/`
- Record robot fleet management decisions in `10_adr/`
- Update troubleshooting procedures in `07_troubleshooting/`

## When to Use

- Any architectural decision
- New API endpoint or service integration
- Changes to VDA5050 message handling
- Modifications to SAP EWM integration patterns
- New robot fleet management features
- Security or authentication changes

## Anti-Patterns

❌ **Don't** implement first and document later (it never happens)  
❌ **Don't** document in isolation without team review  
❌ **Don't** create separate doc tasks - update inline during grilling  

✅ **Do** treat documentation as part of the implementation  
✅ **Do** link ADRs to related code changes  
✅ **Do** update runbooks before deploying to production
