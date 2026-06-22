---
name: dify-workflow
description: Build and manage Dify workflow DSL for AI-powered automation. Create, validate, and deploy workflow definitions for SAP EWM and robot dispatch integration.
---

# Dify Workflow Builder

## Overview

Dify workflows enable AI-powered automation by connecting LLM nodes, code execution, HTTP requests, and conditional logic in a visual workflow. This skill helps you create valid Dify workflow DSL (YAML/JSON).

## Workflow Structure

```yaml
app:
  mode: workflow
  name: "SAP EWM Order Dispatcher"
  description: "Processes inbound delivery orders and dispatches to appropriate robot fleet"
  
workflow:
  graph:
    edges:
      - source: "start"
        sourceHandle: "source"
        target: "validate_order"
        targetHandle: "target"
      - source: "validate_order"
        sourceHandle: "source"
        target: "check_inventory"
        targetHandle: "target"
    
    nodes:
      - id: "start"
        type: "start"
        title: "Start"
        data:
          variables:
            - label: "order_id"
              variable: "order_id"
              type: "string"
              required: true
      
      - id: "validate_order"
        type: "code"
        title: "Validate Order"
        data:
          code: |
            def main(order_id: str) -> dict:
              # Validation logic
              if not order_id:
                return {"valid": False, "error": "Order ID required"}
              return {"valid": True, "order_id": order_id}
          outputs:
            valid:
              type: "boolean"
            error:
              type: "string"
      
      - id: "llm_decision"
        type: "llm"
        title: "AI Decision Engine"
        data:
          model: "gpt-4"
          prompt: |
            Analyze this order and recommend robot type:
            Order: {{order_id}}
            Priority: {{priority}}
            Items: {{item_count}}
            
            Return JSON: {"robot_type": "...", "reason": "..."}
          temperature: 0.1
      
      - id: "http_request"
        type: "http-request"
        title: "Call SAP OData"
        data:
          url: "https://sap-ewm.example.com/sap/opu/odata/sap/EWM_INBOUND_DELIVERY_SRV/InboundDeliverySet"
          method: "GET"
          headers:
            Authorization: "Bearer {{sap_token}}"
            Accept: "application/json"
          params:
            $filter: "DeliveryID eq '{{order_id}}'"
      
      - id: "condition"
        type: "if-else"
        title: "Route Decision"
        data:
          conditions:
            - id: "high_priority"
              logical_operator: "and"
              conditions:
                - variable: "{{priority}}"
                  comparison_operator: "is"
                  value: "HIGH"
            - id: "normal_priority"
              logical_operator: "and"
              conditions:
                - variable: "{{priority}}"
                  comparison_operator: "is"
                  value: "NORMAL"
      
      - id: "end"
        type: "end"
        title: "End"
        data:
          outputs:
            - value: "{{dispatch_result}}"
```

## Node Types

### 1. Start Node
Entry point with input variables.
```yaml
type: "start"
data:
  variables:
    - label: "Display Name"
      variable: "variable_name"
      type: "string|number|boolean|object"
      required: true|false
      default: "optional_default"
```

### 2. LLM Node
AI processing with prompts.
```yaml
type: "llm"
data:
  model: "gpt-4|gpt-3.5-turbo|claude-2"
  prompt: "Your prompt with {{variables}}"
  temperature: 0.0-1.0
  max_tokens: 1000
  context:
    - role: "system"
      content: "You are an expert in..."
```

### 3. Code Node
Execute Python/JavaScript.
```yaml
type: "code"
data:
  language: "python3|javascript"
  code: |
    def main(input_var: str) -> dict:
      # Your code here
      return {"result": "value"}
  outputs:
    result:
      type: "string"
```

### 4. HTTP Request Node
External API calls.
```yaml
type: "http-request"
data:
  url: "https://api.example.com/endpoint"
  method: "GET|POST|PUT|DELETE"
  headers:
    Content-Type: "application/json"
  body: '{"key": "{{variable}}"}'
  timeout: 30
```

### 5. Condition Node (If-Else)
Branching logic.
```yaml
type: "if-else"
data:
  conditions:
    - id: "branch_name"
      conditions:
        - variable: "{{var}}"
          comparison_operator: "is|contains|gt|lt|gte|lte|starts_with|ends_with"
          value: "comparison_value"
```

### 6. End Node
Output results.
```yaml
type: "end"
data:
  outputs:
    - value: "{{final_result}}"
```

## Best Practices

### 1. Error Handling
```yaml
# Add error catching at critical points
- id: "try_catch"
  type: "code"
  data:
    code: |
      def main() -> dict:
        try:
          # Risky operation
          result = risky_operation()
          return {"success": True, "data": result}
        except Exception as e:
          return {"success": False, "error": str(e)}
```

### 2. Variable Naming
- Use `snake_case` for variables
- Be descriptive: `order_priority` not `op`
- Prefix with context: `sap_order_id`, `robot_status`

### 3. Logging
```python
# In code nodes
import logging
logging.info(f"Processing order {{order_id}}")
logging.error(f"Failed to dispatch: {error_message}")
```

### 4. Validation at Boundaries
```yaml
# Always validate external inputs
- id: "validate_input"
  type: "code"
  data:
    code: |
      def main(order_data: dict) -> dict:
        required = ['order_id', 'items', 'priority']
        missing = [k for k in required if k not in order_data]
        if missing:
          return {"valid": False, "error": f"Missing: {missing}"}
        return {"valid": True}
```

## SAP EWM Integration Patterns

### Pattern 1: Order Processing
```yaml
start → validate_order → check_sap_inventory → llm_dispatch_decision → http_dispatch_robot → end
```

### Pattern 2: Status Monitoring
```yaml
start → http_get_robot_status → condition_battery_low → alert_if_needed → end
```

### Pattern 3: Error Recovery
```yaml
start → try_operation → catch_errors → retry_logic → escalate_if_failed → end
```

## Testing Workflows

### 1. Unit Test Nodes
- Test each node in isolation
- Verify outputs match expected format
- Check error handling

### 2. Integration Test
- Run complete workflow with test data
- Verify all edges work
- Check end-to-end timing

### 3. Edge Cases
- Empty inputs
- Invalid data types
- Network timeouts
- API rate limits

## Deployment

### Export Workflow
```bash
# From Dify UI: Export as YAML
# Or via API:
curl -X GET "https://dify.example.com/api/workflows/{workflow_id}/export" \
  -H "Authorization: Bearer {api_key}"
```

### Import Workflow
```bash
curl -X POST "https://dify.example.com/api/workflows/import" \
  -H "Authorization: Bearer {api_key}" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@workflow.yaml"
```

## Common Issues

### ❌ Invalid variable references
```yaml
# Wrong
"{{undefined_variable}}"

# Right
"{{defined_in_start_node}}"
```

### ❌ Missing edges
```yaml
# Every node (except end) must have outgoing edges
edges:
  - source: "node_a"
    target: "node_b"
```

### ❌ Type mismatches
```yaml
# If output is boolean, don't use as string
# Fix: Convert in next node
```

## Resources

- Dify Documentation: https://docs.dify.ai
- Workflow DSL Schema: Check Dify repo
- Examples: https://github.com/langgenius/dify/tree/main/workflows
