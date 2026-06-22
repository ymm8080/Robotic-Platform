---
name: Superpowers
description: Comprehensive checklist for AI-assisted development. Covers architecture, testing, security, performance, and maintainability. Use before major changes.
---

# Superpowers

## Pre-Implementation Checklist

Before starting any significant work, review these areas:

### 🏗️ Architecture
- [ ] Does this change fit the existing architecture patterns?
- [ ] Are we introducing new dependencies? Are they necessary?
- [ ] Will this scale? (data volume, user count, concurrent requests)
- [ ] Is there a simpler way to achieve the same result?
- [ ] What are the failure modes?

### 🧪 Testing
- [ ] Are there tests for the affected code?
- [ ] Do I need to add/update tests?
- [ ] What edge cases should be tested?
- [ ] Can this be tested in isolation (unit tests)?
- [ ] Do we need integration/E2E tests?

### 🔒 Security
- [ ] Are user inputs validated and sanitized?
- [ ] Are there authentication/authorization checks?
- [ ] Is sensitive data encrypted/stored securely?
- [ ] Are there any SQL injection/XSS/CSRF vulnerabilities?
- [ ] Are secrets/credentials exposed in logs or code?

### ⚡ Performance
- [ ] Are there N+1 queries or inefficient loops?
- [ ] Do we need caching? What caching strategy?
- [ ] Are database queries optimized (indexes, execution plans)?
- [ ] Will this increase memory usage significantly?
- [ ] Are there async operations that should be parallelized?

### 📝 Maintainability
- [ ] Is the code self-documenting (clear names, simple logic)?
- [ ] Are complex parts explained with comments?
- [ ] Is error handling consistent and helpful?
- [ ] Will future developers understand this?
- [ ] Is there duplicate code that should be extracted?

### 🔄 Data Flow
- [ ] Where does data come from? Where does it go?
- [ ] Is data validated at boundaries?
- [ ] What happens when data is missing/invalid?
- [ ] Are there race conditions or concurrency issues?
- [ ] Is the data transformation correct in all cases?

### 🚀 Deployment
- [ ] Are there database migrations needed?
- [ ] Are environment variables configured?
- [ ] Is there a feature flag needed for gradual rollout?
- [ ] What's the rollback plan?
- [ ] Does this break backward compatibility?

### 📊 Observability
- [ ] Are there appropriate logs (not too much, not too little)?
- [ ] Are errors tracked with context?
- [ ] Do we need metrics/alerts for this feature?
- [ ] Can we monitor the health of this feature?
- [ ] Are there business events to track?

## When to Use

- Before starting new features
- Before major refactoring
- During code review
- When designing system architecture
- When troubleshooting complex issues

## Quick Rules

✅ **Think before coding** - 5 minutes of planning saves 5 hours of debugging  
✅ **Challenge assumptions** - "It can't fail" is famous last words  
✅ **Consider the user** - Both end users AND developer users  
✅ **Leave it better** - Fix small issues you find along the way  
✅ **Know when to stop** - Perfect is the enemy of good  

## Red Flags

🚩 No tests  
🚩 Functions >50 lines  
🚩 Nested conditionals >3 levels  
🚩 No error handling  
🚩 "Magic" numbers/strings  
🚩 Copy-paste code  
🚩 No logging  
🚩 Tight coupling  
🚩 Side effects in pure functions  
🚩 Mutating shared state
