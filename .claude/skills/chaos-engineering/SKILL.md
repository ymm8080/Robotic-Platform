---
name: chaos-engineering
description: Chaos engineering patterns for testing system resilience, fault injection, and recovery validation in the EWM Robotic Platform.
---

# Chaos Engineering

System resilience testing through controlled failure injection.

## When to Use
- Testing system behavior under network partition
- Validating circuit breaker behavior with SAP API failures
- Testing MQTT broker failover scenarios
- Verifying recovery from Redis/PostgreSQL outages

## Activation Commands
> "Inject network latency between Node-RED and MQTT broker"
> "Test system recovery when Redis goes down"
> "Simulate SAP bridge unavailability and verify circuit breaker triggers"
