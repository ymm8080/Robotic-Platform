---
name: tdd
description: Test-Driven Development discipline. Write tests first, watch them fail, write minimal code to pass, refactor. Ensures code quality and prevents regressions.
---

# Test-Driven Development (TDD)

## The Three Laws

1. **You may not write production code until you have written a failing unit test**
2. **You may not write more of a unit test than is sufficient to fail**
3. **You may not write more production code than is sufficient to pass the currently failing test**

## Red-Green-Refactor Cycle

### 1. RED - Write a failing test
- Write a test that describes the desired behavior
- Run it and watch it fail (this confirms the test works)
- The failure should be meaningful (not a syntax error)

### 2. GREEN - Make it pass
- Write the MINIMUM code needed to make the test pass
- Don't over-engineer
- Hard-code if needed (you'll refactor next)

### 3. REFACTOR - Clean up
- Remove duplication
- Improve naming
- Extract functions/classes
- Ensure all tests still pass

## When to Use

- New feature development
- Bug fixes (write test that reproduces bug first)
- Refactoring existing code (write tests first if missing)
- Complex business logic

## Benefits

✅ Tests serve as living documentation  
✅ Prevents regressions  
✅ Forces you to think about edge cases  
✅ Results in better architecture  
✅ Safe to refactor  

## Anti-Patterns to Avoid

❌ Writing all tests upfront (write one at a time)  
❌ Writing tests after implementation (defeats the purpose)  
❌ Testing implementation details (test behavior, not internals)  
❌ Skipping the refactor step (technical debt accumulates)  

## Example Flow

```typescript
// 1. RED - Write failing test
test('calculates total with tax', () => {
  const cart = { items: [{ price: 100 }] };
  expect(calculateTotal(cart, 0.1)).toBe(110);
});

// 2. GREEN - Minimal implementation
function calculateTotal(cart, taxRate) {
  return cart.items[0].price * (1 + taxRate);
}

// 3. REFACTOR - Handle multiple items
function calculateTotal(cart, taxRate) {
  const subtotal = cart.items.reduce((sum, item) => sum + item.price, 0);
  return subtotal * (1 + taxRate);
}
```
