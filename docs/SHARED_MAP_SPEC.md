# Shared Canonical Facility Map — Function Specification

**Version:** 1.0  
**Date:** 2026-07-08  
**Status:** Draft  
**Author:** Platform Team  

---

## 1. Problem Statement

The platform dispatches 6 robot brands (KUKA, MiR, OTTO, GeekPlus, HaiRobotics, Quicktron) via VDA5050/MQTT. Each brand runs its own proprietary SLAM and internal map — with its own coordinate origin, scale, and orientation. When two brands report position `(5000, 3000)` they are NOT at the same physical location. When the platform sends both to `nodePosition {x:8000, y:2000}` they go to different physical places.

**Without a shared map there is no:**
- Cross-brand coordinate consistency
- Cross-brand zone locking (WCS sandbox)
- Cross-brand traffic management
- Reliable SAP warehouse-bin-to-physical-location mapping

## 2. Solution Overview

**One canonical facility map** (single source of truth) + **per-brand affine calibration** (simple math transform: scale, rotate, translate) + **transparent conversion in the strategy layer**.

```
Canonical Map (PostgreSQL)
        │
Map Service (FastAPI routes)
        │
   ┌────┼────┬────────┐
   ▼    ▼    ▼        ▼
KUKA  MiR  OTTO  ... (each with own calibration)
```

## 3. Core Concepts

### 3.1 Canonical Facility Map

A single coordinate system for the entire warehouse. All platform logic (dispatch, zone reservation, SAP bin mapping, dashboard) works in canonical coordinates.

- **Origin:** Fixed physical reference point (e.g., southwest column of the building)
- **Unit:** Millimeters
- **Orientation:** X = east, Y = north (standard Cartesian)
- **Storage:** PostgreSQL, versioned (`facility_maps` table)
- **Format:** Nodes/edges/zones stored relationally; exportable as GeoJSON

### 3.2 Per-Brand Calibration (Affine Transform)

Each brand's native coordinate system is mapped to canonical via a 6-parameter affine transformation:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `scale_x` | X-axis scale factor | 1.0 |
| `scale_y` | Y-axis scale factor | 1.0 |
| `shear` | Shear factor | 0.0 |
| `rotation_deg` | Rotation in degrees | 0.0 |
| `translate_x` | X translation (mm) | 0.0 |
| `translate_y` | Y translation (mm) | 0.0 |

**Transform formula (native → canonical):**
```
x' = scale_x * x + shear * y
y' = scale_y * y
canonical_x = x' * cos(θ) - y' * sin(θ) + translate_x
canonical_y = x' * sin(θ) + y' * cos(θ) + translate_y
```

### 3.3 Calibration Procedure

1. Mark 3+ physical reference points on the warehouse floor (cross marks)
2. Measure their canonical coordinates (survey or building plan)
3. For each brand: drive one robot to each reference point, record its native (x, y)
4. Compute best-fit affine transform via least squares (6 unknowns, >= 6 equations from 3 points)
5. Store calibration with residual error (RMSE) and validity period (recommend 90 days)

### 3.4 Coordinate Conversion Flow

**Inbound (robot → platform):** `extract_position()` in strategy → `to_canonical()` → stored in Redis/DB in canonical coordinates.

**Outbound (platform → robot):** `dispatch()` in strategy → `from_canonical()` on node positions → sent as brand-native coordinates in VDA5050 order.

**Without calibration:** Identity transform (pass-through). System works exactly as before. Calibration is additive, not breaking.

## 4. API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/v1/map` | Get current facility map (GeoJSON) |
| `GET` | `/api/v1/map/nodes` | List all VDA5050 nodes in canonical coords |
| `POST` | `/api/v1/map/calibrations` | Compute & store brand calibration from reference points |
| `GET` | `/api/v1/map/calibrations/{brand}` | Get calibration for a brand |
| `DELETE` | `/api/v1/map/calibrations/{brand}` | Remove a brand's calibration |
| `POST` | `/api/v1/map/transform` | Test coordinate transform without storing |

## 5. Database Schema

```sql
facility_maps(id, name, version, map_data JSONB, origin_x, origin_y, created_at)
map_nodes(id, map_id FK, node_id, x, y, theta, properties JSONB, UNIQUE(map_id, node_id))
map_edges(id, map_id FK, edge_id, start_node_id, end_node_id, properties JSONB, UNIQUE(map_id, edge_id))
map_zones(id, map_id FK, zone_id, zone_type, polygon JSONB, properties JSONB)
brand_calibrations(id, brand, map_id FK, scale_x/y, shear, rotation_deg, translate_x/y,
                   reference_points JSONB, residual_error_mm, calibrated_at, calibrated_by, valid_until,
                   UNIQUE(brand, map_id))
```

## 6. Strategy Integration

`BaseStrategy` gains:
- `__init__(self, transform: AffineTransform | None = None)` — accepts optional calibration
- `to_canonical(x, y) -> (x, y)` — native → canonical (inverse of stored transform)
- `from_canonical(x, y) -> (x, y)` — canonical → native (forward transform)
- `extract_position(state) -> dict` — overridden to convert coordinates to canonical
- `dispatch(order) -> DispatchResult` — overridden to convert node positions to brand-native

All 6 brand strategies inherit this automatically. No per-brand changes needed.

## 7. Non-Goals

- This spec does NOT cover SLAM, path planning, or robot-local navigation
- This spec does NOT define a wire format for map distribution to robots (VDA5050 `map_id` side-channel is future work)
- This spec does NOT replace robot-internal maps — it defines a shared reference frame on top of them

## 8. Success Criteria

- [ ] AffineTransform class with forward/inverse/from_points, 100% test coverage
- [ ] DB migration creates all 5 tables via `init_schema()`
- [ ] Map REST routes respond correctly (tested with httpx TestClient)
- [ ] All 6 brand strategies accept and use calibration transforms
- [ ] Zero calibration = identity behavior (backward compatible)
- [ ] Calibration RMSE < 50mm for simulated test data
- [ ] All existing tests continue to pass
