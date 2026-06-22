---
name: prompt-engineering
description: Techniques for writing effective prompts that get the best results from LLMs. Includes patterns, anti-patterns, and optimization strategies.
---

# Prompt Engineering

## Core Principles

### 1. Be Specific and Explicit
❌ **Bad**: "Write a function to handle orders"
✅ **Good**: "Write a TypeScript function that validates an order object, checking: (1) items array is not empty, (2) each item has productId (string), quantity (number > 0), and price (number > 0), (3) totalAmount matches sum of (quantity * price) for all items. Return validation errors as an array of strings."

### 2. Provide Context
```
Context: Building an SAP EWM integration for warehouse management
Task: Create a function to parse inbound delivery notifications
Expected input: JSON from SAP IDoc WEADM
Expected output: Normalized delivery object with {id, items[], expectedDate}
Constraints: Must handle partial deliveries, validate against purchase orders
```

### 3. Use Examples (Few-Shot Prompting)
```
Convert these user requests to SQL queries:

User: "Show me all orders from last week"
SQL: SELECT * FROM orders WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)

User: "Find customers who spent more than $1000"
SQL: SELECT customer_id, SUM(total) as total_spent FROM orders GROUP BY customer_id HAVING total_spent > 1000

User: "Get the top 5 products by revenue this month"
SQL: [LLM completes]
```

### 4. Specify Format
```
Return the result as JSON with this structure:
{
  "success": boolean,
  "data": { ... },
  "errors": string[],
  "metadata": {
    "timestamp": "ISO 8601",
    "processingTimeMs": number
  }
}
```

## Advanced Techniques

### Chain of Thought
Ask the LLM to think step by step:
```
"Let's solve this systematically:
1. First, identify the root cause
2. Then, consider 3 possible solutions
3. Evaluate pros/cons of each
4. Recommend the best approach with reasoning"
```

### Role Prompting
```
"You are a senior backend architect with 15 years of experience in distributed systems.
Review this microservice design for:
- Scalability bottlenecks
- Single points of failure
- Data consistency issues
- Security vulnerabilities"
```

### Constraint Setting
```
"Write a function that:
- Uses ONLY built-in methods (no external libraries)
- Has O(n) time complexity
- Handles null/undefined gracefully
- Includes JSDoc comments
- Is less than 30 lines"
```

### Iterative Refinement
```
"First pass: Write the basic implementation
Second pass: Add error handling
Third pass: Optimize performance
Fourth pass: Add comprehensive tests"
```

## Prompt Patterns

### Template Pattern
```
[Role/Context]
You are a [expert in X] working on [project Y].

[Task]
Create/Refactor/Debug [specific component].

[Requirements]
- Must do: [non-negotiable requirements]
- Should do: [important but flexible]
- Nice to have: [if time permits]

[Constraints]
- Tech stack: [languages, frameworks]
- Performance: [time/space complexity]
- Style: [coding standards]

[Examples]
Input: [example input]
Output: [expected output]

[Format]
Return as: [code/JSON/explanation/steps]
```

### Critique Pattern
```
"Review this code and provide:
1. What's done well (specific examples)
2. Issues found (with severity: critical/major/minor)
3. Specific improvements (with code examples)
4. Edge cases not handled
5. Security concerns
6. Performance optimizations"
```

### Exploration Pattern
```
"I need to [goal]. Explore these approaches:

Approach A: [describe briefly]
Approach B: [describe briefly]
Approach C: [describe briefly]

For each approach, analyze:
- Complexity (implementation effort)
- Maintainability (long-term cost)
- Performance (runtime characteristics)
- Risks (what could go wrong)

Recommend the best approach for [specific constraints]."
```

## Anti-Patterns

❌ **Vague requests**: "Make it better"
❌ **Too broad**: "Build me an e-commerce platform"
❌ **No constraints**: Leads to over-engineered solutions
❌ **Assuming context**: LLM doesn't know your codebase
❌ **Single massive prompt**: Break into smaller tasks

## Optimization Tips

### 1. Temperature Settings
- Code generation: 0.1-0.3 (deterministic)
- Brainstorming: 0.7-0.9 (creative)
- Bug fixing: 0.0-0.2 (precise)

### 2. Token Budget
- Keep prompts under 2000 tokens when possible
- Use ellipsis for long code: `// ... existing code ...`
- Reference files instead of pasting entire contents

### 3. Feedback Loop
```
"That's close, but:
- The error handling needs to be more specific
- Add validation for edge case X
- Use async/await instead of promises
Regenerate with these changes."
```

## SAP EWM Specific Prompts

### OData Service Generation
```
"Generate a TypeScript client for this SAP OData service:
Service URL: /sap/opu/odata/sap/EWM_INBOUND_DELIVERY_SRV
Entities: InboundDelivery, DeliveryItem, HandlingUnit
Include: Type definitions, query methods, error handling
Use: axios for HTTP, proper SAP authentication headers"
```

### VDA5050 Message Handling
```
"Create a VDA5050 state machine that:
- Processes AGV state updates from MQTT
- Validates message schema against VDA5050 spec
- Handles connectionState (ONLINE/OFFLINE)
- Tracks battery level and triggers alerts < 20%
- Logs state transitions with timestamps"
```
