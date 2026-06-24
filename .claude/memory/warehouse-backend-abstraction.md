---
name: warehouse-backend-abstraction
description: Dual EWM+WM warehouse backend architecture — plugin registry pattern mirrors strategies/
metadata: 
  node_type: memory
  type: project
  status: design-approved-unimplemented
  originSessionId: ad66e039-1e6f-4984-9ffb-06cfd54d0bd2
---

## Decision: Plugin Registry for Multi-Warehouse Backend Support

Decided 2026-06-24. Will implement later.

### Architecture

`sap-bridge/backends/` mirrors `sap-bridge/strategies/` pattern exactly:

```
sap-bridge/backends/
  ├── base.py              ← WarehouseBackend ABC (mirrors strategies/base.py)
  ├── registry.py           ← singleton registry (mirrors strategies/registry.py)
  ├── ewm_backend.py        ← existing OData code extracted (mirrors strategies/kuka.py)
  ├── wm_backend.py         ← new pyrfc/BAPI implementation (mirrors strategies/mir.py)
  └── __init__.py

sap-bridge/models/
  ├── warehouse_task.py     ← canonical task model (EWM WT + WM TO fields)
  └── order.py              ← existing, SAP-agnostic ✓
```

### Key Design Choices

1. **Config-driven per warehouse** — `config.yaml` `sap.warehouses` map with `backend: ewm|wm` + connection params
2. **Single container handles mixed** — one `sap-bridge` can talk to EWM and WM warehouses simultaneously (same as one bridge handles KUKA + MiR robots)
3. **Plugin-loadable** — future: scan `/app/backends/plugins/` for file-drop new backends
4. **ABC contract tests** — single test suite runs against any backend mock

### Files to Change (when implemented)

| File | Action |
|------|--------|
| `backends/base.py` | NEW |
| `backends/registry.py` | NEW |
| `backends/ewm_backend.py` | NEW (extract from ewm_warehouse_service.py) |
| `backends/wm_backend.py` | NEW |
| `models/warehouse_task.py` | NEW |
| `services/ewm_warehouse_service.py` | DELETE |
| `services/batch_service.py` | MODIFY |
| `services/inventory_service.py` | MODIFY |
| `services/__init__.py` | MODIFY |
| `main.py` | MODIFY |
| `config.yaml` | MODIFY |
| `Dockerfile` | MODIFY (add pyrfc conditional) |
| `requirements.txt` | MODIFY |

**Why:** [[claude-code-equip-v3.4]] — the strategies/ pattern already proves this works.
