# Examples: Generic NX Reverse-Engineering Pipeline (v2)

This directory contains clean, minimal examples showing how to use the unified parametric NX CAD reverse-engineering pipeline.

The pipeline takes **any arbitrary Wavefront OBJ mesh**, performs analytical surface segmentation and topological feature extraction, constructs a parametric feature dependency DAG (Reconstruction Intent IR), and builds a native, fully parametric Siemens NX part (`.prt`) driven by named expressions and generic CAD primitives (`EXTRUDE`, `REVOLVE`, `LOFT`, `CYLINDER`, `THROUGH_CUTOUT`, `HOLE`, `POCKET`, `BOSS`).

---

## 1. Quick Start via CLI

The primary entry point is [`scripts/build_from_intent.py`](../scripts/build_from_intent.py):

```bash
# Set license server (if not already set in environment)
$env:SPLM_LICENSE_SERVER = "28000@192.168.1.29"

# 1. Axisymmetric Revolve Body (e.g. Axe deodorant container)
python scripts/build_from_intent.py Axe3.obj --output Axe3_Parametric.prt

# 2. Multi-Tier Axial Body (e.g. TRESemme shampoo with collar/pump)
python scripts/build_from_intent.py TRESemme6.obj --output TRESemme6_Parametric.prt

# 3. Genus-1 Loft Body with Through-Cutout (e.g. Surfexcel detergent with handle)
python scripts/build_from_intent.py Surfexcel2_reduced.obj --output Surfexcel2_Parametric.prt
```

---

## 2. Example Scripts

- [`run_rebuild_mesh.py`](run_rebuild_mesh.py): Demonstrates programmatic invocation of the end-to-end rebuilder from Python with error handling and result inspection.
- [`analyze_mesh_intent.py`](analyze_mesh_intent.py): Demonstrates running Phase 1 (Segmentation), Phase 2 (Feature Extraction), and Phase 3 (DAG / Intent IR) independently to inspect geometric features before sending to NX.

---

## 3. Legacy Code Note

All earlier handwritten per-object journals (e.g. `create_axe3_parametric.py`, `create_tresemme6_parametric.py`, etc.) have been removed. The system no longer uses shape-specific scripts; all geometry is rebuilt dynamically by the generic primitive engine.
