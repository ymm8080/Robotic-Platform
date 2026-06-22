---
name: llm-skill
description: LLM skill reference. Understand and apply AI skills effectively for development tasks.
---

# LLM Skills Reference

## What Are LLM Skills?

Skills are markdown files that teach AI assistants (Cursor, Qoder) how to perform specific tasks or follow particular methodologies. They provide structured guidance for consistent, high-quality output.

## Skill Structure

```markdown
---
name: skill-name
description: Brief description of what this skill does and when to use it
---

# Skill Name

## When to Use
[Specific scenarios where this skill applies]

## Process
[Step-by-step workflow]

## Examples
[Concrete examples from the project context]

## Anti-Patterns
[What NOT to do]

## Best Practices
[Key principles to follow]
```

## How Skills Work

### Activation Methods

1. **Automatic**: AI recognizes when to apply the skill based on context
2. **Manual**: Reference the skill in your prompt
   - "Use the `tdd` skill for this implementation"
   - "Follow the `diagnose` methodology"
3. **Slash Command**: Some IDEs support `/skill-name` commands

### Skill Categories

#### Workflow Skills
- `grill-me` - Ask clarifying questions before implementing
- `tdd` - Test-Driven Development workflow
- `diagnose` - Systematic debugging methodology
- `GSD` - Get Shit Done rapid development
- `Superpowers` - Comprehensive implementation checklist

#### Quality Skills
- `careful` - Double-check critical systems
- `guard` - Security-first mindset
- `grill-with-docs` - Grilling with inline documentation

#### Domain Skills
- `SAP_OData_Handler` - SAP EWM OData integration patterns
- `VDA5050_State_Machine` - Robot protocol state machine
- `dify-workflow` - Dify workflow DSL builder
- `Async_Retry_Tester` - Async retry pattern testing

#### Utility Skills
- `freeze` - Restrict file edits to specific directories
- `to-prd` - Generate Product Requirements Documents
- `prompt-engineering` - Write effective prompts
- `llm-models` - Choose the right LLM model
- `llm-wiki` - Build personal knowledge base

## Using Skills Effectively

### 1. Match Skill to Task

| Task Type | Recommended Skills |
|-----------|-------------------|
| New feature | grill-me → to-prd → Superpowers → tdd |
| Bug fix | diagnose → careful → tdd |
| Refactor | grill-me → guard → tdd |
| Debug complex issue | diagnose → careful |
| Rapid prototyping | GSD → careful |
| Security review | guard → careful |
| Architecture decision | grill-me → grill-with-docs |

### 2. Combine Skills

Skills are composable. Example workflow:

```
"Use grill-me to clarify requirements, then to-prd to document, then tdd to implement"
```

### 3. Reference in Context

When working on specific files:
```
"In [file.py], use the tdd skill to add tests for [function]"
```

### 4. IDE-Specific Usage

#### Cursor
- Skills in `.cursor/skills/`
- Reference: "Using the tdd skill from .cursor/skills/tdd.md"
- Some IDE versions support `/skill-name` slash commands

#### Qoder
- Skills in `.qoder/skills/`
- Reference: "Follow the diagnose methodology from .qoder/skills/diagnose.md"
- Skills automatically loaded when relevant

## Creating Custom Skills

### When to Create a Skill
- You repeat the same workflow frequently
- You need consistent quality standards
- You want to capture project-specific patterns
- You need to enforce specific methodologies

### Skill Creation Process

1. **Identify the Pattern**
   - What workflow/task needs standardization?
   - What are the key steps?
   - What are common mistakes to avoid?

2. **Draft the Skill**
   - Use the standard structure
   - Include project-specific examples
   - Define clear anti-patterns
   - Provide concrete workflows

3. **Test the Skill**
   - Use it in real scenarios
   - Does it improve consistency?
   - Are the instructions clear?
   - Does it catch common mistakes?

4. **Iterate**
   - Update based on usage
   - Add missing edge cases
   - Improve examples
   - Refine anti-patterns

## SAP EWM Skill Examples

### Custom SAP Skill Structure

```markdown
---
name: sap-ewm-integration
description: Guidelines for SAP EWM OData API integration
---

# SAP EWM Integration

## Authentication
- Use OAuth2 with service account
- Never hardcode credentials
- Rotate tokens every 24 hours

## OData Patterns
- Use $batch for bulk operations
- Implement exponential backoff
- Handle CSRF tokens properly

## Error Handling
- Log all SAP API errors
- Implement retry with circuit breaker
- Alert on repeated failures

## VDA5050 Integration
- Validate message schema before sending
- Track robot state transitions
- Handle timeout scenarios
```

## Best Practices

✅ **Do:**
- Keep skills focused and actionable
- Include project-specific examples
- Update skills when processes change
- Reference skills in conversations
- Combine skills for complex tasks
- Create skills for repeated workflows

❌ **Don't:**
- Make skills too generic
- Skip using skills when rushed
- Let skills become outdated
- Over-complicate the skill structure
- Duplicate knowledge across skills

## Skill Maintenance

### Monthly Review
- Are skills still relevant?
- Any missing edge cases?
- New patterns to capture?
- Examples still accurate?

### When to Update
- Process changes
- New best practices discovered
- Project architecture evolves
- Common mistakes identified

## Troubleshooting

### Skill Not Working
- Is the skill file valid markdown?
- Is the frontmatter correct?
- Is the skill in the right directory?
- Is the IDE configured to use skills?

### Skill Not Triggering Automatically
- Reference it explicitly in prompt
- Check if description matches your task
- Verify skill is in correct directory
