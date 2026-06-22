---
name: to-prd
description: Turn the current conversation context into a Product Requirements Document (PRD) and publish it to the project issue tracker or docs folder.
---

# To PRD (Product Requirements Document)

## Purpose

Convert informal discussions, requirements, or feature requests into a structured PRD that engineers and stakeholders can execute against.

## When to Use

✅ **After discovery calls** - Capture requirements before development  
✅ **Before major features** - Document scope, constraints, success criteria  
✅ **When stakeholders align** - Lock in agreed requirements  
✅ **Before handoff to engineering** - Clear spec for implementation  

## PRD Structure

### 1. Executive Summary
```markdown
# Feature: [Name]

**Problem Statement**: [What problem are we solving?]
**Target Users**: [Who benefits?]
**Business Impact**: [Why does this matter?]
**Priority**: [P0/P1/P2]
**Target Release**: [Date or sprint]
```

### 2. User Stories
```markdown
## User Stories

### Story 1: [Title]
**As a** [user type]  
**I want to** [action]  
**So that** [benefit]  

**Acceptance Criteria**:
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Edge case handled

**Priority**: [Must/Should/Could/Won't]
```

### 3. Functional Requirements
```markdown
## Functional Requirements

### FR-001: [Requirement Title]
**Description**: [What the system must do]
**Inputs**: [What data/events trigger this]
**Outputs**: [What happens]
**Constraints**: [Performance, security, compliance]
**Dependencies**: [What this requires]
```

### 4. Non-Functional Requirements
```markdown
## Non-Functional Requirements

### Performance
- Response time: <200ms for 95th percentile
- Throughput: 1000 requests/second
- Scalability: Handle 10x load increase

### Security
- Authentication required
- Data encrypted at rest and in transit
- RBAC enforced

### Reliability
- 99.9% uptime SLA
- Graceful degradation on failures
- Auto-recovery from common errors
```

### 5. Technical Specifications
```markdown
## Technical Design

### Architecture
[High-level diagram or description]

### API Contracts
```typescript
interface CreateOrderRequest {
  orderId: string;
  items: OrderItem[];
  priority: 'HIGH' | 'NORMAL' | 'LOW';
}

interface CreateOrderResponse {
  success: boolean;
  orderId: string;
  estimatedCompletionTime: Date;
}
```

### Data Model
```sql
CREATE TABLE dispatch_orders (
  id UUID PRIMARY KEY,
  sap_order_id VARCHAR(36) NOT NULL,
  robot_type VARCHAR(50),
  status VARCHAR(20) DEFAULT 'PENDING',
  created_at TIMESTAMP DEFAULT NOW()
);
```
```

### 6. Edge Cases & Error Handling
```markdown
## Edge Cases

1. **SAP API Unavailable**
   - Retry 3 times with exponential backoff
   - Queue order for later processing
   - Alert operations team

2. **No Robots Available**
   - Return estimated wait time
   - Offer alternative robot types
   - Log for capacity planning

3. **Partial Delivery**
   - Split order into multiple dispatches
   - Track each dispatch independently
   - Notify warehouse of split
```

### 7. Success Metrics
```markdown
## Success Criteria

### Primary Metrics
- Order processing time: <5 seconds
- Robot utilization: >80%
- Dispatch accuracy: >99%

### Secondary Metrics
- User satisfaction score
- Error rate
- Mean time to recovery

### Monitoring
- Dashboard alerts on SLA breaches
- Daily reports on dispatch volume
- Weekly robot utilization review
```

### 8. Dependencies & Risks
```markdown
## Dependencies

| Dependency | Owner | Status | Risk |
|-----------|-------|--------|------|
| SAP OData API upgrade | SAP Team | In Progress | Medium |
| Robot firmware v2.1 | Vendor | Testing | High |
| Network upgrade | Infrastructure | Planned | Low |

## Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Robot API incompatibility | High | Medium | Vendor testing in staging |
| SAP downtime during rollout | High | Low | Schedule during maintenance window |
| Insufficient robot capacity | Medium | Medium | Capacity planning review |
```

### 9. Rollout Plan
```markdown
## Deployment Strategy

### Phase 1: Internal Testing (Week 1)
- Deploy to staging
- Test with mock SAP data
- Validate with 2 test robots

### Phase 2: Pilot (Week 2-3)
- Deploy to 1 warehouse zone
- Monitor for 2 weeks
- Collect feedback from 5 users

### Phase 3: Gradual Rollout (Week 4-6)
- Expand to 25% of zones
- Monitor metrics daily
- Address issues before next phase

### Phase 4: Full Rollout (Week 7-8)
- Deploy to all zones
- Continue monitoring
- Close pilot feedback loops

### Rollback Plan
If dispatch failure rate >5%:
1. Route new orders to manual process
2. Investigate root cause
3. Fix and re-test in staging
4. Re-deploy with pilot approach
```

### 10. Open Questions
```markdown
## Open Questions

1. [ ] Should we support mixed-brand robot fleets in Phase 1?
2. [ ] What's the fallback if MQTT broker goes down?
3. [ ] Do we need real-time SAP sync or batch is acceptable?
4. [ ] Who owns robot maintenance scheduling?

**Owner**: [Name]  
**Review Date**: [Date]
```

## Workflow

### Step 1: Extract Requirements
From conversation, identify:
- User needs
- Business constraints
- Technical requirements
- Success criteria

### Step 2: Structure the PRD
Fill in each section above with specifics from the discussion.

### Step 3: Identify Gaps
Ask clarifying questions on:
- Ambiguous requirements
- Missing acceptance criteria
- Unclear priorities
- Unidentified dependencies

### Step 4: Generate PRD
Create the markdown file with all sections populated.

### Step 5: Review & Iterate
- Share with stakeholders
- Collect feedback
- Update PRD
- Get sign-off

## Output Location

```
docs/prds/
├── PRD-001-robot-dispatch-v2.md
├── PRD-002-sap-integration.md
└── PRD-003-multi-brand-support.md
```

## Example PRD Creation

```
User: "We need to dispatch robots based on SAP inbound deliveries"

Agent applies to-prd skill:
1. Extracts: SAP integration, robot dispatch, delivery matching
2. Structures: User stories, API contracts, data flows
3. Identifies gaps: What if delivery is delayed? Robot capacity?
4. Generates: Full PRD in docs/prds/PRD-001-sap-robot-dispatch.md
5. Shares: "Here's the PRD. Review and I'll update based on feedback."
```

## Integration with Issue Tracker

After PRD approval:
```
Convert PRD to issues:
- Each user story → GitHub/GitLab issue
- Acceptance criteria → Issue checklist
- Technical specs → Implementation notes
- Dependencies → Issue labels
```

Use `/to-issues` skill to automate this conversion.

## Quality Checklist

Before finalizing PRD:
- [ ] Problem statement is clear and specific
- [ ] User stories have acceptance criteria
- [ ] Technical design addresses edge cases
- [ ] Success metrics are measurable
- [ ] Dependencies and risks identified
- [ ] Rollout plan includes rollback
- [ ] Open questions documented
- [ ] Stakeholders reviewed and approved
