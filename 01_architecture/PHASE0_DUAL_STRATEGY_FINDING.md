# Phase 0 Dual-Strategy Architecture Finding

**Date:** 2026-07-14  
**Target:** Brand Knowledge Deduplication for EWM Robot Platform v7.0  

## Executive Summary

This document analyzes the dual strategy layer architecture and identifies shared vs. separate brand knowledge. The core insight: **both strategy layers legitimately differ in responsibilities and MUST remain separate**, but they duplicate static brand facts that can be centralized.

## Layer Responsibility Boundary

### DISPATCH Side (core/adapter/brands/strategies.py)
- **Purpose**: MQTT VDA5050 state → FleetState transformation for traffic coordinator
- **Output**: Core v5.0 FleetState messages
- **Scope**: Lightweight, standalone classes, zero dependency on SAP
- **Brand Handling**: Minimal quirks needed for state→FleetState conversion

### SAP Side (sap-bridge/strategies/)
- **Purpose**: SAP EWM Work Type → VDA5050 dispatch payload generation
- **Output**: VDA5050 order payloads for direct robot control
- **Scope**: Rich features (version checking, BrandQuirk tracking, dispatch routing)
- **Brand Handling**: Complex protocol handling (IOP REST, HAIQ, proprietary fallbacks)

The layers are intentionally separate with different jobs. **Never merge them** - the core must remain SAP-independent.

## Shared vs. Legitimately Separate Brand Knowledge

### ✅ SHARED FACTS (Moved to brand_knowledge.py)

#### 1. VDA5050 Version Support
- All brands: Which VDA5050 versions they support
- Critical for both layers to handle correct protocol versions

#### 2. Capability Vectors (Default Configuration)
- Payload capacity, max speed, supported models
- Action primitives supported by each brand
- Environment constraints (grade, friction, etc.)
- *Why shared*: Both layers need identical robot capability data for allocator

#### 3. Battery Conversion Logic
- Format detection (percentage, millivolts, adaptive)
- Conversion constants and thresholds
- Field mapping for different battery representations
- *Why shared*: Battery percentage is critical state used by both layers

#### 4. Standard Field Mappings
- Standard VDA5050 field names each brand uses
- Important for consistent state parsing
- *Why shared*: Both layers consume same VDA5050 state format

#### 5. Brand Model Support Lists
- Actual model names each brand supports
- *Why shared*: Both layers need to identify robot capabilities correctly

### ❌ LEGITIMATELY SEPARATE (Kept in strategy files)

#### 1. State-to-FleetState vs State-to-RobotState Logic
- **core/**: VDA5050 state → FleetState transformation
- **sap-bridge/**: VDA5050 state → RobotState normalization
- *Why separate*: Different output formats serve different purposes

#### 2. Dispatch Payload Generation
- **core/**: Minimal order transformation for traffic coordinator
- **sap-bridge/**: Full VDA5050 + proprietary protocol dispatch
- *Why separate*: SAP needs direct robot control, core needs simple routing

#### 3. Protocol-Specific Handling
- **Geek+:** IOP REST vs VDA5050 routing logic
- **HaiRobotics:** HAIQ-ESS REST vs VDA5050 handling
- **Quicktron:** VDA5050 vs proprietary fallback
- *Why separate*: SAP handles multiple protocols, core only uses VDA5050

#### 4. Quirk Documentation and Severity Tracking
- **sap-bridge/**: Detailed BrandQuirk with severity levels
- *Why separate*: SAP integration needs quirk tracking for deployment decisions

#### 5. Real-Time State Logic
- **MiR:** WAITING grace counter
- **OTTO:** Millivolt battery detection
- **KUKA:** Battery threshold charging
- *Why separate*: These are runtime behaviors, not static knowledge

## Implementation Decisions

### 1. brand_knowledge.py Design
- **Frozen dataclass**: Immutable brand knowledge prevents accidental mutation
- **Registry pattern**: Centralized lookup with get_brand_knowledge() accessor
- **Identity-default-safe**: `get_brand_knowledge()` raises `KeyError` for unregistered brands; the DISPATCH side only queries the six registered keys, so no runtime path hits an unknown brand
- **Brand keys**: Exact matches ("mir", "otto", etc.) to match both layers

### 2. Backward Compatibility
- DISPATCH side (`core/adapter/brands/strategies.py`): all six `to_capability_vector()`
  methods now source from the shared registry via `_capability_from_knowledge(brand)`.
  Values are **verified identical** to the previously-hardcoded vectors across all six
  brands (payload_kg, max_speed, supported_models, action_primitives, env,
  supports_reverse) — zero behavior change, guarded by `core/tests/` (94 passed/4
  skipped) and `traffic_coordinator_v5/tests/` (75 passed).
- SAP side (`sap-bridge/strategies/`): **unchanged** in this PR — wiring deferred
  (see DoD Status below).
- The shared module's `supported_versions` / `battery_quirks` / `field_mapping` /
  `error_quirks` fields are not yet consumed by either layer; they are foundational
  data carried for the SAP-side wiring and are **not yet consumer-validated**. The
  Quicktron `mv_min`/`mv_max` battery values are marked `[GUESS]`.

### 3. API Contract
```python
# Public API (fixed for rewire agents)
from core.adapter.brands.brand_knowledge import BrandKnowledge, BRAND_KNOWLEDGE, get_brand_knowledge

# Usage example
mir_knowledge = get_brand_knowledge("mir")
capability = mir_knowledge.default_capability_vector
```

## DoD Status (vs v7.0 plan Phase 0)

The v7.0 plan Phase 0 DoD requires: *"共享品牌知识模块被两侧引用（grep 可证）"* — the
shared module referenced by **both** strategy layers, grep-provable.

- ✅ **DISPATCH side (core)**: `core/adapter/brands/strategies.py` imports
  `get_brand_knowledge` and sources all six capability vectors from the registry
  (grep-provable: `grep -n brand_knowledge core/adapter/brands/strategies.py`).
- ⬜ **SAP side (sap-bridge)**: not yet wired — deferred to a follow-up PR. This PR
  does **not** fully satisfy the plan's "both sides" DoD; it lands the core half plus
  the shared module. Risk note honored: neither layer's responsibilities were deleted;
  only the knowledge layer is deduplicated.

## Future Roadmap

1. **Phase 0 step 2**: SAP strategies (`sap-bridge/strategies/`) import shared
   knowledge — eliminates the second copy and completes the "both sides" DoD.
2. **Phase 0 step 3**: Validate `supported_versions` / `battery_quirks` / quirks
   against the SAP layer's existing values; resolve `[GUESS]` Quicktron voltages.
3. **Phase 3**: Brand updates in one place (automatic sync via module import).

## Verification

Independent verification (re-run, not assumed):
- ✅ `ruff check` + `ruff format --check` clean on both touched files
- ✅ `python .github/scripts/syntax_check.py` — 90 files valid
- ✅ `pytest core/tests/` — 94 passed, 4 skipped
- ✅ `pytest traffic_coordinator_v5/tests/` — 75 passed
- ✅ Behavior-parity: each strategy's `to_capability_vector()` output matches the
  shared registry field-for-field for all six brands
- ✅ Immutability: `MappingProxyType` + `tuple` shallow-freeze blocks in-place
  mutation of registry fields
- ✅ `get_brand_knowledge()` raises `KeyError` for unknown brands (no silent default)

---

**Conclusion**: The dual-layer architecture is sound and should NOT be merged. This
PR deduplicates the DISPATCH side's brand capability knowledge into a single shared,
read-only registry (behavior-preserving), with SAP-side wiring deferred to a follow-up
to complete the v7.0 Phase 0 DoD.