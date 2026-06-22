---
name: understand-anything
description: Deep codebase understanding through knowledge graph analysis. Maps relationships between modules, functions, data flows, and architectural patterns to provide comprehensive system comprehension.
---

# Understand Anything - Knowledge Graph Analysis

## Overview

This skill provides deep understanding of complex codebases by building knowledge graphs that map relationships between components, trace data flows, and identify architectural patterns.

## When to Use

Use this skill when:
- Onboarding to a new codebase
- Understanding complex system architecture
- Tracing data flow across modules
- Identifying dependencies and coupling
- Analyzing impact of changes
- Finding entry points for debugging

## Core Capabilities

1. **Module Mapping**: Discover and catalog all modules/packages
2. **Dependency Graph**: Map imports, exports, and dependencies
3. **Data Flow Analysis**: Trace how data moves through the system
4. **Call Graph**: Map function/method invocations
5. **Architecture Patterns**: Identify MVC, layered, microservices, etc.
6. **Entry Points**: Find main execution paths and API endpoints

## Analysis Process

1. **Structural Scan**: Read directory structure and configuration files
2. **Import Analysis**: Parse imports to build dependency graph
3. **Function Mapping**: Identify public APIs and internal functions
4. **Data Tracing**: Follow data from input to output
5. **Pattern Recognition**: Identify architectural patterns and conventions

## Output Format

Generates comprehensive understanding including:
- System architecture diagram (Mermaid)
- Module dependency graph
- Key entry points and data flows
- Architectural patterns identified
- Recommendations for navigation

## Quick Start

```bash
# Start with high-level structure
ls -la
cat package.json  # or equivalent

# Build understanding incrementally
1. Read README and documentation
2. Scan directory structure
3. Identify entry points
4. Trace major data flows
5. Map core domain logic
```

## Tips

- Start broad, then dive deep into specific areas
- Follow the data - it reveals the real architecture
- Look for patterns, not just individual files
- Document as you learn - build your own knowledge graph
