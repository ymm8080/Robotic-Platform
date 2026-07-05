# ADR-006: Message Gateway Architecture (Multi-Channel Notification)

**Date**: 2026-07-05
**Status**: Accepted
**Version**: v3.5

## Context

The SAP-EWM robot dispatch platform (v3.4) supported alert notifications only via Node-RED → Feishu webhook. As the platform matures, operators need:

1. **Multi-channel notification**: WeChat Work, Feishu, DingTalk, Email — not just Feishu
2. **Mobile operation**: Ability to execute operations (stop robot, cancel order) from mobile devices
3. **100% accuracy guarantee**: No room for misinterpreted natural language commands
4. **Audit compliance**: All mobile operations must be logged immutably (≥3 years retention)
5. **Platform isolation**: Gateway failure must not affect the core dispatch engine

## Decision

Add a **Message Gateway** as Layer 5 in the architecture, deployed as an independent FastAPI service.

### Architecture

```
Core Platform (Node-RED) → Kafka → Message Gateway → WeChat / Feishu / DingTalk / Email
                                         ↓
                              ┌─────────────────────┐
                              │  Message Router      │  (priority, dedup, time control)
                              │  Card Template Engine│  (platform-specific cards)
                              │  Action Validator    │  (six-layer validation)
                              │  Email Gateway       │  (SMTP)
                              │  Audit Logger        │  (Elasticsearch, WORM)
                              └─────────────────────┘
                                         ↑
                    Platform Callback (POST /webhook/{platform})
```

### Key Design Decisions

1. **Kafka decoupling**: Core platform produces alert events to Kafka; gateway consumes independently. If gateway is down, alerts queue in Kafka (no impact on dispatch).

2. **Six-layer validation** (not NLU): All write operations triggered via structured buttons must pass:
   - Identity → Permission → Object → Anti-replay → Secondary confirmation → Pre-execution
   - Natural language input is explicitly rejected for write operations.

3. **Unified callback**: `POST /webhook/{platform}` abstracts platform differences. Each platform adapter handles signature verification and format normalization.

4. **Operation state machine**: INIT → NOTIFIED → CONFIRMING → CONFIRMED → EXECUTING → SUCCESS/FAILED/TIMEOUT/CANCELLED. State transitions are strict and auditable.

5. **Elasticsearch for audit**: All operations logged to ES with 3-year retention. Critical operations flagged for WORM backup.

6. **CowAgent isolation** (optional): Read-only AI query assistant is strictly isolated from the write operation pipeline. Even if compromised, cannot trigger physical world actions.

## Consequences

### Positive
- Operators can manage alerts from any device (phone, tablet, desktop)
- 100% accuracy via structured buttons + six-layer validation (no NLU ambiguity)
- Complete audit trail for compliance (等保)
- Platform-agnostic: adding a new channel only requires a new adapter
- Core platform unaffected by gateway outages (Kafka buffering)

### Negative
- Additional infrastructure: Kafka + Elasticsearch increase resource usage (~1.5GB RAM)
- Operational complexity: more services to monitor and maintain
- Platform API differences require adapter maintenance

### Risks Mitigated
- **Misoperation risk**: Six-layer validation + secondary confirmation for dangerous operations
- **Replay attacks**: Anti-replay layer with SHA-256 fingerprint + Redis TTL
- **Unauthorized access**: Identity binding + permission check before any operation
- **Audit gap**: All operations logged to ES + WORM backup for critical ops

## Implementation

- **Phase 1-2** (Week 7): Gateway core (Router, Email, Audit, WeChat/Feishu/DingTalk adapters)
- **Phase 3-4** (Week 8): Card templates, Action Validator, integration testing, CowAgent (optional)

See `docker-compose.yml` services: `kafka`, `elasticsearch`, `message-gateway`.

## References

- v3.5 Design Document: `SAP-EWM-机器人调度平台-Cursor生产级配置终极清单-v3.5.docx`
- Iron Rules 11-13: Message gateway accuracy, platform callback security, audit log immutability
- Six-layer validation detail: `gateway/app/action_validator.py`
- Card templates: `gateway/app/card_template_engine.py`
