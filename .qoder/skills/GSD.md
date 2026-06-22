---
name: GSD
description: Get Shit Done. Action-oriented workflow for rapid development. Focus on shipping, avoid analysis paralysis, iterate quickly.
---

# GSD (Get Shit Done)

## Core Philosophy

**Done is better than perfect. Ship it, then improve it.**

## Workflow

### 1. Clarify the Goal (2 minutes)
- What's the MINIMUM viable outcome?
- What does "done" look like?
- Who is this for?

### 2. Plan Minimally (5 minutes)
- What are the 3-5 key steps?
- What's the fastest path?
- What can we skip for now?

### 3. Execute Relentlessly
- Time-box: Work in 25-minute sprints
- No distractions: Close Slack, silence phone
- One task at a time: Finish before switching
- Good enough > perfect: Ship working code

### 4. Review & Iterate
- Does it work? ✓
- Is it secure? ✓
- Can we improve it later? ✓
- SHIP IT

## Rules

✅ **Time-box everything** - Parkinson's Law: work expands to fill time  
✅ **Minimum viable solution** - Don't build a spaceship when you need a bike  
✅ **Perfectionism is procrastination** - 80% good + shipped > 100% good + stuck  
✅ **Done means deployable** - Not "done on my machine"  
✅ **Iterate in public** - Get feedback early and often  

## Anti-Patterns

❌ **Over-engineering** - Building for requirements that don't exist yet  
❌ **Analysis paralysis** - Researching instead of doing  
❌ **Refactoring rabbit holes** - "I'll just clean this up first..."  
❌ **Feature creep** - "While I'm at it, I should also..."  
❌ **Premature optimization** - Making it fast before making it work  

## Decision Framework

When stuck on a decision, ask:

1. **Can I reverse this easily?**
   - Yes → Decide in 30 seconds, move on
   - No → Spend max 5 minutes thinking

2. **What's the cost of being wrong?**
   - Low (can fix in <1 hour) → Just do it
   - Medium (can fix in <1 day) → Think for 2 minutes
   - High (major rework) → Think for 5 minutes, then decide

3. **Will this matter in 6 months?**
   - Yes → Worth investing time
   - No → Quick and dirty is fine

## Code Guidelines

### Start Simple
```javascript
// V1: Hard-coded, works
const taxRate = 0.1;

// V2: Configurable (when needed)
const taxRate = config.taxRate || 0.1;

// V3: Dynamic (when users demand it)
const taxRate = getTaxRate(order.region, order.date);
```

### Iterate Fast
1. Make it work (ugly, hard-coded, whatever)
2. Make it right (tests, refactoring, clean code)
3. Make it fast (optimization, caching, indexes)

**Never skip step 1 to get to step 3.**

## Time Allocation

- 60% - Building the thing
- 20% - Testing the thing
- 10% - Cleaning up the thing
- 10% - Documenting the thing (comments, README)

## When to Use GSD

✅ Prototypes and MVPs  
✅ Internal tools  
✅ Bug fixes  
✅ Small features (<2 days)  
✅ Experiments and spikes  

## When NOT to Use GSD

❌ Security-critical code (payments, auth, personal data)  
❌ Core infrastructure (databases, networking)  
❌ Public APIs (once published, hard to change)  
❌ Team-wide standards (worth discussing and agreeing)  

## Emergency Mantra

> "Perfect is the enemy of done.  
> Done is the enemy of shipped.  
> Shipped is the enemy of improved.  
> Get it shipped, then improve it."

## Quick Checklist

- [ ] Does it solve the core problem?
- [ ] Does it work end-to-end?
- [ ] Are there any obvious bugs?
- [ ] Is it secure (no exposed secrets, validated inputs)?
- [ ] Can I deploy this NOW?

If all yes → **SHIP IT** 🚀
