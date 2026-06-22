---
name: headroom
description: Strategic code review and architectural analysis skill. Provides high-level perspective on code quality, design patterns, technical debt, and improvement opportunities with focus on maintainability and scalability.
---

# Headroom - Strategic Code Review

## Overview

Headroom provides strategic, high-level code review and architectural analysis that goes beyond syntax and style. It focuses on design patterns, maintainability, scalability, and long-term code health.

## When to Use

Use this skill when:
- Reviewing pull requests for architectural impact
- Assessing technical debt in existing codebase
- Planning refactoring initiatives
- Evaluating design decisions before implementation
- Onboarding to understand code quality standards
- Preparing codebase for scaling

## Review Dimensions

### 1. **Architecture & Design**
- Separation of concerns
- Dependency injection and inversion
- Module boundaries and cohesion
- Design pattern usage (and misuse)
- Scalability considerations

### 2. **Maintainability**
- Code readability and clarity
- Function/method complexity
- Naming conventions and consistency
- Documentation quality
- Test coverage and quality

### 3. **Performance & Scalability**
- Algorithm efficiency (Big O)
- Memory usage patterns
- Database query optimization
- Caching strategy
- Concurrency handling

### 4. **Security**
- Input validation
- Authentication/authorization
- Data exposure risks
- Dependency vulnerabilities
- Secure coding practices

### 5. **Developer Experience**
- API design clarity
- Error handling consistency
- Debugging support
- Build/development workflow
- Documentation accessibility

## Analysis Process

1. **Context Gathering**
   - Read project documentation
   - Understand business requirements
   - Identify key stakeholders
   - Review existing patterns

2. **Structural Analysis**
   - Map module relationships
   - Identify architectural patterns
   - Assess dependency graphs
   - Locate coupling points

3. **Quality Assessment**
   - Run static analysis tools
   - Check test coverage
   - Review error handling
   - Evaluate documentation

4. **Strategic Recommendations**
   - Prioritize by impact
   - Consider implementation effort
   - Provide concrete examples
   - Suggest incremental improvements

## Output Format

Generates comprehensive review including:
- Executive summary (1-2 paragraphs)
- Strengths identified
- Critical issues (must fix)
- Recommendations (should fix)
- Suggestions (nice to have)
- Refactoring roadmap (if applicable)

## Quick Assessment Checklist

```
□ Architecture follows documented patterns
□ New modules have clear responsibilities
□ Dependencies are explicit and minimal
□ Error handling is consistent
□ Tests cover happy path and edge cases
□ Documentation updated with changes
□ Performance impact considered
□ Security implications reviewed
□ API changes are backward compatible
□ Code follows project conventions
```

## Best Practices

- **Think long-term**: Consider how changes affect future development
- **Balance ideals with reality**: Perfect is the enemy of good
- **Provide context**: Explain why, not just what
- **Suggest incremental steps**: Big rewrites rarely succeed
- **Acknowledge trade-offs**: Every decision has pros and cons
- **Focus on impact**: Prioritize changes that matter most

## Strategic Questions

When reviewing code, always ask:
1. Will this make future changes easier or harder?
2. Is the complexity justified by the benefit?
3. Can a new developer understand this in 5 minutes?
4. What happens when this needs to scale 10x?
5. Where will this break first under stress?
