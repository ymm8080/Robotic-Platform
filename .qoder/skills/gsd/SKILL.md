---
name: gsd
description: Get Shit Done (GSD) - A comprehensive project management system for solo developers using AI agents. Provides phased project management, milestone tracking, checkpoint protocols, and state management.
---

# GSD - Get Shit Done

## Overview

GSD is a comprehensive project management framework designed for solo developers working with AI agents. It provides structured workflows for project initialization, phase planning, milestone tracking, and execution with atomic commits.

## When to Use

Use this skill when:
- Starting a new project with structured phases
- Planning implementation with detailed phase breakdowns
- Tracking milestone progress and checkpoints
- Managing complex multi-step development work
- Need verification before completion claims

## Core Commands

- `/gsd:new-project` - Initialize a new GSD project with domain research
- `/gsd:plan-phase` - Create detailed execution plan for a phase
- `/gsd:execute-phase` - Execute a phase with atomic commits
- `/gsd:verify-phase` - Verify phase completion and goal achievement
- `/gsd:complete-milestone` - Complete a milestone with integration checks
- `/gsd:create-checkpoint` - Create phase checkpoint for approval
- `/gsd:debug` - Systematic debugging with root cause investigation

## Key Features

1. **Phased Execution**: Break work into discoverable, planable, executable phases
2. **Checkpoint Protocol**: Save state at phase boundaries for user approval
3. **Verification-First**: Verify deliverables before claiming completion
4. **Atomic Commits**: Each change is committed separately for easy rollback
5. **State Management**: Track project state across sessions

## Workflow

1. **New Project** → Research domain and requirements
2. **Plan Phase** → Create detailed task breakdown with dependencies
3. **Execute Phase** → Implement tasks with atomic commits
4. **Verify Phase** → Goal-backward verification of deliverables
5. **Complete Milestone** → Integration checks and system-wide verification

## Installation Note

**Full GSD CLI installed** - Version 1.5.0-rc.5
- Source: https://github.com/open-gsd/gsd-core
- CLI Tools: `gsd-core`, `gsd-tools`, `gsd_run`
- Location: npm global (via npm link)

**Available GSD Commands:**
- `gsd-tools phase` - Phase management (add, insert, remove, complete)
- `gsd-tools milestone` - Milestone tracking
- `gsd-tools state` - Project state management
- `gsd-tools config` - Configuration management
- `gsd-tools progress` - Progress reporting
- `gsd-tools verify` - Verification and validation
- `gsd-tools template` - Template generation
- `gsd-tools workstream` - Workstream management
- `gsd-tools worktree` - Git worktree management
- And 50+ more commands (run `gsd-tools` for full list)
