---
name: llm-models
description: LLM model reference guide. Choose the right model for the task based on capabilities, cost, and context windows.
---

# LLM Models Reference

## Model Selection Guide

### For Code Generation & Implementation

**GPT-4o / Claude 3.5 Sonnet** (Best Overall)
- ✅ Complex refactoring
- ✅ Architecture design
- ✅ Multi-step implementations
- ❌ Avoid for simple tasks (overkill)

**GPT-3.5 Turbo / Claude 3 Haiku** (Fast & Cheap)
- ✅ Code completion
- ✅ Simple refactors
- ✅ Documentation generation
- ✅ Repetitive transformations

### For Analysis & Debugging

**Claude 3.5 Sonnet** (Best Reasoning)
- ✅ Root cause analysis
- ✅ Performance optimization
- ✅ Security review
- ✅ Complex bug diagnosis

**GPT-4o** (Balanced)
- ✅ Code review
- ✅ Test generation
- ✅ API design

### For SAP EWM & Robot Platform Tasks

**Large Context Models (128K+ tokens)**
- ✅ Full system architecture analysis
- ✅ Multi-service debugging
- ✅ Complete VDA5050 message flow analysis
- ✅ SAP OData API integration patterns

**Specialized Models**
- ✅ Code generation with SAP ABAP patterns
- ✅ MQTT message validation
- ✅ Robot state machine logic
- ✅ Database query optimization

## Context Window Guidelines

| Task | Minimum Context | Recommended |
|------|----------------|-------------|
| Single function refactor | 4K | 8K |
| Service-level changes | 8K | 16K |
| Multi-service integration | 16K | 32K |
| Full architecture review | 32K | 128K+ |
| Complete codebase analysis | 128K | 200K+ |

## Cost Optimization

### When to Use Expensive Models
- Architectural decisions
- Complex debugging
- Security-sensitive code
- Production deployments
- SAP integration points

### When to Use Cheap Models
- Boilerplate generation
- Documentation updates
- Simple refactors
- Test scaffolding
- Code formatting

## Model-Specific Strengths

### GPT-4o
- Strong at following complex instructions
- Good at code structure
- Excellent tool use

### Claude 3.5 Sonnet
- Superior reasoning
- Better at finding bugs
- Strong security analysis

### Claude 3 Haiku
- Fast execution
- Cost-effective for bulk tasks
- Good for repetitive operations

## SAP EWM Context

For the Robot Dispatch Platform:
- Use **large context models** for VDA5050 protocol analysis
- Use **strong reasoning models** for SAP OData integration debugging
- Use **fast models** for generating robot state handlers
- Use **security-focused review** for authentication/authorization code

## Best Practices

1. **Match model to task complexity** - Don't overpay for simple tasks
2. **Use large context when needed** - Don't truncate critical information
3. **Verify critical code** - Always review AI-generated code for SAP integrations
4. **Test thoroughly** - AI can introduce subtle bugs in robot control logic
5. **Document decisions** - Record which model was used for audit trails
