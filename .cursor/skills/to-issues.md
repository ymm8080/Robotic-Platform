---
name: to-issues
description: Convert PRDs to GitHub/GitLab issues. Break down requirements into actionable development tasks.
---

# To Issues - PRD to Issue Converter

Convert Product Requirements Documents into structured, actionable GitHub/GitLab issues with proper labels, estimates, and dependencies.

## Process

### 1. Parse PRD Structure

Extract from PRD:
- User stories
- Functional requirements
- Non-functional requirements
- Technical specifications
- Edge cases
- Success metrics
- Dependencies & risks
- Rollout plan

### 2. Create Issue Hierarchy

```
EPIC: [Feature Name]
├── Story: [User Story 1]
│   ├── Task: [Implementation detail]
│   ├── Task: [Test coverage]
│   └── Task: [Documentation]
├── Story: [User Story 2]
│   ├── Task: [Implementation detail]
│   └── Task: [Integration test]
└── Story: [Technical requirement]
    ├── Task: [Database migration]
    ├── Task: [API endpoint]
    └── Task: [Performance optimization]
```

### 3. Issue Template

```markdown
## Summary
[2-3 sentence description]

## User Story
As a [role]
I want [capability]
So that [benefit]

## Acceptance Criteria
- [ ] Given [context], when [action], then [expected result]
- [ ] Given [context], when [action], then [expected result]

## Technical Details
- Component: [affected component]
- API: [endpoints involved]
- Database: [tables/queries]
- External: [SAP OData/MQTT/VDA5050]

## Implementation Notes
[Key technical considerations]

## Dependencies
- Blocks: [issue #]
- Blocked by: [issue #]
- Related: [issue #]

## Testing Strategy
- Unit tests: [what to test]
- Integration tests: [what to test]
- E2E tests: [what to test]

## Definition of Done
- [ ] Code implemented
- [ ] Unit tests passing
- [ ] Integration tests passing
- [ ] Documentation updated
- [ ] Code reviewed
- [ ] Deployed to staging
- [ ] Acceptance criteria met

## Estimate
- Complexity: [S/M/L/XL]
- Story points: [1/2/3/5/8/13]
- Confidence: [High/Medium/Low]

## Labels
`type:feature` `component:xyz` `priority:high` `sap-ewm` `vda5050`
```

### 4. Issue Categories

**Feature Issues**
- User-facing functionality
- New capabilities
- Workflow improvements

**Technical Issues**
- Infrastructure changes
- Database migrations
- API integrations
- Performance optimization

**Quality Issues**
- Test coverage gaps
- Refactoring needs
- Security improvements
- Monitoring/alerting

**Operations Issues**
- Deployment automation
- Runbook creation
- Monitoring setup
- Backup procedures

### 5. SAP EWM Issue Examples

**SAP Integration Issue**

```markdown
## Summary
Implement SAP EWM OData API adapter for order retrieval

## User Story
As the dispatch system
I want to fetch orders from SAP EWM via OData
So that I can assign them to available robots

## Acceptance Criteria
- [ ] Given valid order ID, when calling get_order(), then return Order object
- [ ] Given invalid order ID, when calling get_order(), then raise OrderNotFoundError
- [ ] Given SAP timeout, when calling get_order(), then retry 3 times with backoff
- [ ] All SAP responses cached for 5 minutes

## Technical Details
- Component: sap-integration
- API: SAP EWM /Orders OData endpoint
- Auth: OAuth2 with service account
- Retry: Exponential backoff 1s, 2s, 4s

## Dependencies
- Blocked by: #123 (SAP service account setup)
- Related: #145 (Order validation service)

## Testing Strategy
- Unit tests: Mock SAP client responses
- Integration tests: Test against SAP dev system
- Error scenarios: Timeout, auth failure, invalid response

## Labels
`type:feature` `component:sap-integration` `priority:high` `sap-ewm` `odata`
```

**VDA5050 Issue**

```markdown
## Summary
Implement VDA5050 state machine for robot command handling

## User Story
As the fleet manager
I want robots to follow VDA5050 state transitions
So that all brands behave consistently

## Acceptance Criteria
- [ ] Given robot in INITIALIZING state, when config received, then transition to IDLE
- [ ] Given robot in IDLE state, when order assigned, then transition to STARTING
- [ ] Given robot in RUNNING state, when error occurs, then transition to ERROR
- [ ] All state transitions logged and published via MQTT

## Technical Details
- Component: vda5050-state-machine
- Protocol: VDA5050 v2.0
- MQTT Topics: robot/{id}/state, robot/{id}/cmd
- Persistence: Redis for current state, PostgreSQL for history

## Dependencies
- Related: #156 (MQTT message routing)
- Related: #167 (Robot status monitoring)

## Labels
`type:feature` `component:vda5050` `priority:critical` `robot-fleet` `mqtt`
```

### 6. Bulk Issue Creation

**Script for GitHub API**

```bash
#!/bin/bash
# Create issues from PRD sections

PRD_FILE="prd.md"
REPO="org/repo"

# Extract stories
grep "^### Story:" $PRD_FILE | while read -r story; do
  TITLE=$(echo $story | cut -d':' -f2-)
  
  # Create issue
  gh issue create \
    --repo $REPO \
    --title "$TITLE" \
    --body "$(extract_story_body $PRD_FILE "$TITLE")" \
    --label "type:story" \
    --milestone "Sprint $(date +%Y-%m)"
done
```

### 7. Issue Prioritization

**P0 - Critical**
- Security vulnerabilities
- System outages
- Data corruption
- SAP integration failures

**P1 - High**
- Core features blocking users
- Performance degradation
- Robot dispatch failures
- VDA5050 protocol violations

**P2 - Medium**
- New features
- UX improvements
- Technical debt
- Monitoring gaps

**P3 - Low**
- Nice-to-have features
- Code cleanup
- Documentation
- Developer tooling

### 8. Milestone Planning

**Sprint Structure**
```
Sprint 1: Foundation
- SAP authentication
- Basic VDA5050 state machine
- MQTT infrastructure
- Database schema

Sprint 2: Core Features
- Order retrieval from SAP
- Robot assignment algorithm
- Command dispatch via MQTT
- Status monitoring

Sprint 3: Advanced Features
- Multi-brand support
- Error handling & recovery
- Performance optimization
- Monitoring & alerting
```

### 9. Dependency Management

**Track Dependencies**
```
Issue #123 → Issue #145 → Issue #167
   ↓              ↓
Issue #134    Issue #156
```

**Dependency Types**
- Blocks: Must be done first
- Blocked by: Must wait for
- Related: Should coordinate
- Duplicates: Same work

### 10. Quality Checklist

Before creating issues:
- [ ] Each issue has clear acceptance criteria
- [ ] Dependencies identified and linked
- [ ] Estimates provided
- [ ] Labels assigned
- [ ] Priority set
- [ ] Component tagged
- [ ] Testing strategy defined
- [ ] Definition of Done clear
- [ ] No duplicate issues
- [ ] Milestone assigned

## When to Use

- After PRD approved
- Before sprint planning
- When breaking down epics
- When creating project roadmap
- When onboarding new team members
