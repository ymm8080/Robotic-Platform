---
name: careful
description: Double-check everything. Verify assumptions, validate edge cases, ensure correctness over speed. Use for critical systems and production code.
---

# Careful

## Philosophy

**Measure twice, cut once. In critical systems, errors are expensive.**

## When to Use

✅ **Production deployments** - Code that will run in production  
✅ **Security-sensitive code** - Authentication, authorization, encryption  
✅ **Financial calculations** - Payments, billing, pricing  
✅ **Data migrations** - Transforming or moving production data  
✅ **Infrastructure changes** - Database schemas, API contracts  
✅ **Public APIs** - Once published, hard to change  

## Checklist

### Before Implementation
- [ ] Do I fully understand the requirements?
- [ ] Have I identified all edge cases?
- [ ] Are there any hidden assumptions?
- [ ] What could go wrong? (List top 3 failure modes)
- [ ] Is there existing code I should reference?

### During Implementation
- [ ] Am I validating ALL inputs?
- [ ] Am I handling ALL error cases?
- [ ] Are there race conditions?
- [ ] Is this thread-safe/concurrency-safe?
- [ ] Am I leaking resources? (connections, memory, file handles)

### After Implementation
- [ ] Have I tested the happy path?
- [ ] Have I tested error paths?
- [ ] Have I tested edge cases? (empty, null, max, min)
- [ ] Does it handle unexpected input gracefully?
- [ ] Are error messages helpful and secure?

## Verification Techniques

### 1. Input Validation Matrix
```
Test each parameter with:
- Valid value ✓
- null
- undefined  
- empty string/array
- Max length/size
- Invalid type
- Special characters
- SQL injection attempts
- XSS attempts
```

### 2. State Machine Analysis
```
List all possible states:
- Initial state
- Valid transitions
- Invalid transitions (should error)
- Terminal states
- Timeout states

Verify: Every state has a path to completion or error.
```

### 3. Data Flow Tracking
```
For each piece of data:
1. Where does it originate?
2. How is it transformed?
3. Where is it stored?
4. Who can access it?
5. When is it deleted?
6. What validates it at each step?
```

### 4. Error Propagation
```
For each function call:
- What errors can it throw?
- Am I catching them?
- Am I handling them correctly?
- Am I swallowing errors silently?
- Do errors propagate to the right level?
```

## Code Review Questions

### Security
1. Can this be exploited? (SQLi, XSS, CSRF, injection)
2. Are secrets protected? (no hardcoded passwords, API keys)
3. Is authentication enforced? (not just obscurity)
4. Is data encrypted at rest and in transit?
5. Are there rate limits? (prevent abuse)

### Reliability
1. What happens if the database is down?
2. What happens if the network times out?
3. What happens if input is 1000x larger than expected?
4. What happens if two requests arrive simultaneously?
5. Is there a retry mechanism? (and is it safe to retry?)

### Maintainability
1. Will someone understand this in 6 months?
2. Is there documentation for complex logic?
3. Are there tests that serve as examples?
4. Can this be debugged in production?
5. Are logs sufficient but not excessive?

## Testing Strategy

### Unit Tests
```javascript
describe('careful function', () => {
  // Happy path
  test('works with valid input', () => {...});
  
  // Edge cases
  test('handles empty array', () => {...});
  test('handles null values', () => {...});
  test('handles maximum size', () => {...});
  
  // Error cases
  test('throws on invalid type', () => {...});
  test('throws on missing required field', () => {...});
  test('throws on duplicate entry', () => {...});
  
  // Security
  test('sanitizes HTML input', () => {...});
  test('prevents SQL injection', () => {...});
});
```

### Integration Tests
- Test with real database
- Test with real external APIs (staging)
- Test concurrent requests
- Test failure scenarios (network down, timeout)

## Deployment Precautions

### Database Migrations
```sql
-- ALWAYS test migrations on a copy of production data
-- ALWAYS have a rollback script
-- NEVER drop columns immediately (deprecate first)
-- ALWAYS check migration on empty database
-- ALWAYS check migration on database with existing data
```

### API Changes
- Version the API if breaking changes
- Maintain backward compatibility for at least 1 release
- Document all changes in changelog
- Notify consumers before deploying

### Feature Flags
```javascript
// Use feature flags for risky changes
if (featureFlags.isEnabled('new-payment-flow')) {
  return newPaymentFlow(payment);
} else {
  return oldPaymentFlow(payment); // Proven safe
}
```

## Red Flags (STOP and Review)

🚩 **Touching authentication code** - Get a second review  
🚩 **Handling money/pricing** - Verify calculations with test cases  
🚩 **Deleting data** - Are you sure? Can it be recovered?  
🚩 **Changing encryption** - Test migration of existing data  
🚩 **Modifying permissions** - Principle of least privilege  
🚩 **Direct SQL queries** - SQL injection risk, use parameterized queries  
🚩 **CORS changes** - Security implications  
🚩 **Environment variables with secrets** - Not in logs, not in code  

## Golden Rules

1. **Paranoia is a virtue** - Assume everything will fail
2. **Trust no input** - Validate at every boundary
3. **Fail safely** - Errors shouldn't corrupt data
4. **Log everything** - But not sensitive data
5. **Test in staging** - Never test critical changes directly in production
6. **Have a rollback plan** - Know how to undo before you do
7. **Get a second pair of eyes** - Code review is mandatory

## Example: Careful Implementation

```typescript
// ❌ Careless
async function updateUser(id: string, data: any) {
  const user = await db.users.update(id, data);
  return user;
}

// ✅ Careful
async function updateUser(
  id: string, 
  data: UpdateUserInput
): Promise<Result<User, Error>> {
  // 1. Validate input
  if (!isValidUUID(id)) {
    return failure(new ValidationError('Invalid user ID'));
  }
  
  const validation = validateUpdateInput(data);
  if (!validation.isValid) {
    return failure(validation.error);
  }
  
  // 2. Check existence
  const existing = await db.users.findById(id);
  if (!existing) {
    return failure(new NotFoundError('User not found'));
  }
  
  // 3. Check permissions
  if (!canUpdateUser(existing)) {
    return failure(new ForbiddenError('Cannot update this user'));
  }
  
  // 4. Sanitize data
  const sanitized = sanitizeUpdateData(data);
  
  // 5. Execute with error handling
  try {
    const updated = await db.users.update(id, sanitized, {
      optimisticLock: existing.version
    });
    return success(updated);
  } catch (error) {
    if (isOptimisticLockError(error)) {
      return failure(new ConflictError('User was modified by another request'));
    }
    logger.error('Failed to update user', { userId: id, error });
    return failure(new InternalError('Failed to update user'));
  }
}
```
