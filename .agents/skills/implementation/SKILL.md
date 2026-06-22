---
name: implementation
description: Guide for implementing features, fixing bugs, and writing production code. Use when writing code, implementing specifications, fixing issues, or making changes to existing code.
---

# Implementation Guide

## Overview

This skill provides structured guidance for implementing code changes:
- Breaking down requirements into implementable tasks
- Writing clean, maintainable code
- Following best practices and conventions
- Testing and validating implementations

## When to Use

- Implementing new features from specifications
- Fixing bugs or issues
- Refactoring existing code
- Adding tests for functionality
- Making breaking changes or migrations

## Implementation Process

### 1. **Understand Requirements**
- Read the full specification or issue description
- Identify edge cases and error conditions
- Clarify ambiguous requirements
- Determine scope and boundaries

### 2. **Plan Implementation**
- Break into small, testable units
- Identify dependencies and order of operations
- Choose appropriate design patterns
- Consider backward compatibility

### 3. **Write Code**
- Follow existing code style and conventions
- Write self-documenting code with clear names
- Add comments for non-obvious logic
- Handle errors gracefully

### 4. **Test Thoroughly**
- Write unit tests for new functionality
- Test edge cases and error paths
- Verify integration with existing code
- Run full test suite before committing

## Code Quality Standards

### Naming Conventions
- Use descriptive, intention-revealing names
- Follow language-specific conventions
- Avoid abbreviations unless universally understood
- Be consistent across the codebase

### Structure
- Keep functions small and focused (single responsibility)
- Limit function length (<50 lines ideal)
- Group related code together
- Separate concerns clearly

### Error Handling
- Fail fast with clear error messages
- Handle expected errors gracefully
- Log unexpected errors with context
- Never swallow exceptions silently

## Best Practices

1. **Start with tests**: Write tests before or alongside code
2. **Small commits**: Commit logical units of work
3. **Review your own code**: Before requesting review, review it yourself
4. **Document changes**: Update relevant documentation
5. **Consider migration**: Plan for backward compatibility when needed

## Common Pitfalls

- Over-engineering simple solutions
- Ignoring error cases
- Hard-coding values that should be configurable
- Not considering performance implications
- Forgetting to update documentation
- Breaking existing functionality without migration path
