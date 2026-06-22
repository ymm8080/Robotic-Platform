---
name: docs-readme
description: Generate, update, and maintain comprehensive README files and project documentation. Creates clear, structured documentation that helps developers understand and contribute to projects.
---

# Docs/README Generator

## Overview

This skill helps you create, update, and maintain high-quality README files and project documentation that effectively communicates project purpose, setup, and usage.

## When to Use

Use this skill when:
- Creating a new project README from scratch
- Updating outdated documentation
- Improving documentation clarity and structure
- Generating API documentation
- Creating contribution guidelines
- Documenting project architecture

## README Structure

A comprehensive README should include:

1. **Project Title & Description**
   - Clear, concise project name
   - One-sentence description of purpose
   - Badge section (build status, version, license, etc.)

2. **Table of Contents**
   - Auto-generated for easy navigation
   - Reflects actual document structure

3. **Getting Started**
   - Prerequisites and requirements
   - Installation instructions
   - Quick start guide
   - Basic usage examples

4. **Documentation**
   - Feature documentation
   - API reference
   - Configuration options
   - Architecture overview

5. **Development**
   - How to contribute
   - Coding standards
   - Testing instructions
   - Development workflow

6. **Support & Community**
   - Issue templates
   - Contact information
   - Community links

## Best Practices

- **Keep it current**: Update README with every significant change
- **Use visuals**: Include diagrams, screenshots, and GIFs
- **Write for newcomers**: Assume no prior knowledge
- **Be specific**: Provide exact commands and examples
- **Link to details**: Keep README concise, link to detailed docs
- **Test examples**: Ensure all code examples actually work

## Generation Process

1. **Analyze Project**: Scan codebase for structure, dependencies, features
2. **Extract Information**: Read package.json, setup files, existing docs
3. **Identify Audience**: Determine primary users (developers, end-users, both)
4. **Generate Structure**: Create outline based on project type
5. **Fill Content**: Populate sections with accurate information
6. **Review & Refine**: Check accuracy, clarity, and completeness

## Quick Commands

```bash
# Analyze current project structure
find . -type f -name "*.md" | head -20
cat package.json | grep -A 5 "scripts"

# Check for documentation gaps
ls -la docs/ 2>/dev/null || echo "No docs directory"

# Generate basic structure
# Use this skill to create comprehensive README
```

## Documentation Maintenance

- Review README quarterly for accuracy
- Update when adding major features
- Test installation instructions regularly
- Keep examples synchronized with code changes
- Archive outdated sections instead of deleting
