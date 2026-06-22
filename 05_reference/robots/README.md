# Robot Reference Files

Vendor-provided documentation for all robot brands.

## Folder Guide

| Folder | What goes here | File examples |
|--------|---------------|---------------|
| `vda5050/` | VDA5050 protocol specification documents | `VDA5050_2.0.0_EN.pdf`, `VDA5050_1.1.0_DE.pdf`, `protocol_changelog.md` |
| `kuka/` | KUKA KMR iiwa manuals, API refs, known quirks | `KMR_iiwa_OperatingManual.pdf`, `KUKA_VDA5050_impl_notes.md` |
| `mir/` | MiR250 manuals, REST API docs, quirks | `MiR250_UserGuide.pdf`, `MiR_REST_API_v2.pdf`, `MiR_state_mapping.md` |
| `otto/` | OTTO 1500 manuals, battery specs, quirks | `OTTO1500_ProductManual.pdf`, `OTTO_battery_curve.csv` |
| `manuals/` | Safety, installation, maintenance (cross-brand) | `AGV_Safety_ISO_3691-4.md`, `warehouse_layout_guide.pdf` |

## Robot Quirks Quick Reference

| Brand | VDA5050 | Key Quirk |
|-------|---------|-----------|
| KUKA KMR iiwa | 2.0.0 | Lifting action requires pre-navigate, height in mm |
| MiR250 | 1.1.0 | `DRIVING` vs `MOVING` state mismatch; `WAITING` before `IDLE` |
| OTTO 1500 | 2.0.0 | Battery in millivolts, custom charging state |
