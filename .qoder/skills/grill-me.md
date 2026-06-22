---
name: grill-me
description: Ask probing questions before implementing to ensure you understand the problem correctly. Prevents misinterpretation and wasted effort.
---

# Grill Me

Before implementing any significant change, ask yourself:

1. **What is the actual problem being solved?** (Not what the user _says_ they want)
2. **What are the edge cases?** (What could go wrong?)
3. **Is there a simpler approach?** (Are we over-engineering?)
4. **What are the consequences?** (Performance, security, maintainability)

## When to Use

- Before writing new features
- Before refactoring existing code
- When requirements are unclear
- When the user's request seems unusual

## Process

1. Read the request carefully
2. Identify assumptions
3. Ask clarifying questions
4. Propose alternatives if appropriate
5. Wait for user confirmation before proceeding

## Examples

❌ **Bad**: User says "add a button" → You add a button without asking what it should do.

✅ **Good**: User says "add a button" → You ask: "What should happen when clicked? Who can see it? What data does it need?"
