---
name: freeze
description: Restrict file edits to a specific directory for the session. Prevents accidental changes to critical system areas.
---

# Freeze

## Purpose

Lock the AI agent to work ONLY within specified directories during a session. Prevents accidental modifications to:
- System files
- Dependencies (node_modules, vendor/)
- Configuration you don't want touched
- Unrelated parts of the codebase

## When to Use

✅ **Focused refactoring** - "Only touch files in src/auth/"  
✅ **Legacy code work** - "Don't modify the old payment system"  
✅ **Multi-tenant codebase** - "Work only on brand-specific code"  
✅ **Safe experimentation** - "Changes only in experiments/"  

## Usage

### In Cursor/Qoder
```
/freeze src/feature-x
```

This restricts all file operations to `src/feature-x/` and its subdirectories.

### What's Blocked
- Edits outside the frozen directory
- New files outside the frozen directory
- Deletes outside the frozen directory

### What's Allowed
- Reading any file in the project (for context)
- Imports from anywhere (no runtime restrictions)
- Git operations

## Unfreeze

```
/unfreeze
```

Removes the directory restriction.

## Examples

### Example 1: Feature Development
```
User: "/freeze src/new-dispatch-module"

Agent can:
✅ Edit src/new-dispatch-module/*.ts
✅ Create src/new-dispatch-module/helpers/*.ts
✅ Read src/common/types.ts (for context)

Agent cannot:
❌ Edit src/old-dispatch/ (outside freeze zone)
❌ Modify package.json (outside freeze zone)
```

### Example 2: Bug Fix Isolation
```
User: "/freeze src/robot-vda5050"

Context: Fix a bug in VDA5050 message parsing without touching SAP integration

Agent works ONLY in:
- src/robot-vda5050/
- src/robot-vda5050/parsers/
- src/robot-vda5050/validators/

Cannot touch:
- src/sap-integration/
- src/api/
- tests/e2e/
```

## Safety Benefits

1. **Prevents scope creep** - Agent stays focused
2. **Protects stable code** - No accidental regressions
3. **Clear boundaries** - Both human and AI know the workspace
4. **Audit trail** - All changes are in one place

## Best Practices

1. **Be specific** - `/freeze src/auth` not `/freeze src`
2. **Include tests** - `/freeze src/feature tests/feature`
3. **Unfreeze when done** - Remove restrictions after task
4. **Combine with careful skill** - For extra safety on critical code

## Integration with Other Skills

```
/freeze src/payments
Apply the "careful" skill
Now implement the fix
```

This ensures:
- Changes only in payments/
- Double-checked before commit
- No side effects elsewhere
