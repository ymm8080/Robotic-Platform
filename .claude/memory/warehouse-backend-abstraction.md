---
name: warehouse-backend-abstraction
description: Dual EWM+WM warehouse backend — code complete, 35 tests passing. WM needs real SAP system verification.
metadata:
  node_type: memory
  type: project
  status: code-complete-verified
  originSessionId: ad66e039-1e6f-4984-9ffb-06cfd54d0bd2
---

## Decision: Plugin Registry for Multi-Warehouse Backend Support

Decided 2026-06-24. **Implemented 2026-06-25.** All tests pass (354 total).

### Architecture

`sap-bridge/backends/` mirrors `sap-bridge/strategies/` pattern exactly:

```
sap-bridge/backends/
  ├── base.py              ← WarehouseBackend ABC (mirrors strategies/base.py)
  ├── registry.py           ← singleton registry (mirrors strategies/registry.py)
  ├── ewm_backend.py        ← EWM OData — real SAP connected ✅
  ├── wm_backend.py         ← WM RFC/BAPI — code + 35 tests ✅, needs real SAP
  └── factory.py            ← selects backend per warehouse from config.yaml

tests/
  ├── test_wm_backend.py    ← 25 unit tests (mock RFC CRUD + error handling)
  └── test_wm_integration.py ← 10 E2E tests (backend → batch → order flow)
```

### Key Design Choices

1. **Config-driven per warehouse** — `config.yaml` `sap.warehouses` map with `backend: ewm|wm` + connection params
2. **Single container handles mixed** — one `sap-bridge` can talk to EWM and WM warehouses simultaneously
3. **WM needs real SAP system** — code is tested via mock RFC; final verification requires:
   - SAP NW RFC SDK (`pip install pyrfc`)
   - Real WM system credentials (ashost/sysnr/client)
   - Docker build with `INCLUDE_RFC=true`

**Why:** [[claude-code-equip-v3.4]] — the strategies/ pattern already proves this works.
