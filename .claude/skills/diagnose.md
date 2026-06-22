---
name: diagnose
description: Systematic debugging methodology. Reproduce, isolate, identify root cause, fix, verify. Prevents random guessing and ensures thorough problem-solving.
---

# Diagnose

## Systematic Debugging Process

### Step 1: Reproduce the Problem
- Get a clear, reproducible test case
- Document exact steps to trigger the issue
- Identify the minimal reproduction
- Confirm it fails consistently

### Step 2: Gather Information
- Check error messages and stack traces
- Review recent changes (git diff)
- Examine logs and metrics
- Ask: What changed? When did it start?

### Step 3: Isolate the Root Cause
- Form a hypothesis
- Test the hypothesis
- If wrong, form a new hypothesis
- Use binary search (comment out half the code, does it still fail?)
- Add strategic logging/debug points

### Step 4: Fix the Issue
- Address the ROOT CAUSE, not symptoms
- Make the smallest change that fixes the issue
- Write a test that would have caught this bug
- Consider edge cases

### Step 5: Verify the Fix
- Run the reproduction case - should now pass
- Run full test suite - nothing should break
- Test related functionality
- Monitor for side effects

## Debugging Principles

✅ **Understand before changing** - Don't guess, know WHY it's broken  
✅ **One change at a time** - Multiple changes hide the real fix  
✅ **Document your process** - Write down what you tried  
✅ **Rubber duck** - Explain the problem out loud  

## Common Techniques

### Logging Strategy
```javascript
// Bad
console.log('here');
console.log(data);

// Good
console.log('[DEBUG] Processing order', { orderId: order.id, step: 'validation' });
```

### Binary Search Debugging
1. Comment out half the code
2. Does the bug still occur?
   - Yes → Bug is in remaining half
   - No → Bug is in commented half
3. Repeat until isolated

### State Inspection
- What SHOULD the state be?
- What IS the state?
- Where did they diverge?

## Anti-Patterns

❌ **Shotgun debugging** - Randomly changing things hoping it works  
❌ **Fixing symptoms** - Treating the pain, not the disease  
❌ **Assuming** - "It can't be X" → It's often X  
❌ **Ignoring tests** - If tests pass but bug exists, tests are wrong  

## When Stuck

1. Take a break (fresh perspective)
2. Ask someone to rubber duck with you
3. Check if it's a known issue (GitHub, Stack Overflow)
4. Review documentation
5. Simplify the problem (create minimal reproduction)
6. Sleep on it

## Example Debug Session

```
Problem: User can't login

1. REPRODUCE:
   - Try login with valid credentials → fails with 500 error
   - Try login with invalid credentials → fails with 401 (expected)

2. GATHER:
   - Error: "Cannot read property 'token' of undefined"
   - Stack trace points to: auth.service.ts:42
   - Recent changes: Updated JWT library

3. ISOLATE:
   - Hypothesis: JWT library update changed response structure
   - Check: Log the response object → confirmed, 'token' is now 'accessToken'

4. FIX:
   - Change: response.token → response.accessToken
   - Add test for response structure validation

5. VERIFY:
   - Login works ✓
   - All auth tests pass ✓
   - Check logout, refresh token → all work ✓
```
