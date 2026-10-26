"""
test_primitive_segmenter.py
===========================
Unit and integration tests for Phase 1 Primitive Surface Segmentation.
Verifies pure geometric detection of analytical cylinders, planes, and freeform residuals
without any archetype-specific heuristics.
"""

import sys
from pathlib import Path
import numpy as np
import pytest
import trimesh

# Add src to path
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from nx_mcp.mesh_analyzer.primitive_segmenter import PrimitivePatch, PrimitiveSegmenter


def test_synthetic_cylinder_detection():
    """Validates that an analytical synthetic cylinder is accurately identified."""
    # Create an analytical cylinder: radius=25mm, height=100mm
    cyl = trimesh.creation.cylinder(radius=25.0, height=100.0, sections=48)
    segmenter = PrimitiveSegmenter(cyl, cylinder_tolerance_mm=0.5)
    patches = segmenter.segment()

    # Must detect exactly 1 dominant cylinder
    cyl_patches = [p for p in patches if p.primitive_type == "CYLINDER"]
    assert len(cyl_patches) >= 1, "Failed to detect synthetic cylinder primitive"
    main_cyl = max(cyl_patches, key=lambda p: p.face_count)
    assert abs(main_cyl.parameters["radius_mm"] - 25.0) < 0.5, f"Radius error: {main_cyl.parameters['radius_mm']}"
    assert abs(main_cyl.parameters["diameter_mm"] - 50.0) < 1.0
    assert main_cyl.inlier_rms_error_mm < 0.20


def test_synthetic_box_plane_detection():
    """Validates that planar faces of a box are accurately segmented."""
    box = trimesh.creation.box(extents=[60.0, 40.0, 20.0])
    segmenter = PrimitiveSegmenter(box, plane_tolerance_mm=0.1)
    patches = segmenter.segment()

    plane_patches = [p for p in patches if p.primitive_type == "PLANE"]
    assert len(plane_patches) == 6, f"Expected 6 box planar faces, got {len(plane_patches)}"


def test_axe3_real_cylinder_segmentation():
    """Validates on real Axe3.obj: detects primary 360-degree cylinder body."""
    axe_path = repo_root / "obj" / "Axe3.obj"
    if not axe_path.exists():
        pytest.skip("Axe3.obj not found")

    m = trimesh.load(str(axe_path), process=False)
    segmenter = PrimitiveSegmenter(m)
    patches = segmenter.segment()

    cyl_patches = [p for p in patches if p.primitive_type == "CYLINDER"]
    assert len(cyl_patches) >= 1, "Failed to detect cylinder on Axe3"

    main_cyl = max(cyl_patches, key=lambda p: p.face_count)
    # Axe can body radius is approx 37-39mm (Diameter ~76-78mm)
    assert 36.0 <= main_cyl.parameters["radius_mm"] <= 40.0
    assert main_cyl.parameters["angular_span_deg"] >= 300.0
    assert main_cyl.face_count > 10000


def test_tresemme6_freeform_rejection():
    """Validates on real TRESemme6.obj: correctly identifies body as UNCLASSIFIED_FREEFORM."""
    tre_path = repo_root / "obj" / "TRESemme6.obj"
    if not tre_path.exists():
        pytest.skip("TRESemme6.obj not found")

    m = trimesh.load(str(tre_path), process=False)
    segmenter = PrimitiveSegmenter(m)
    patches = segmenter.segment()

    # The bottle body is superelliptical and should not be forced into a single cylinder
    freeform_patches = [p for p in patches if p.primitive_type == "UNCLASSIFIED_FREEFORM"]
    assert len(freeform_patches) >= 1, "TRESemme6 should have dominant freeform component"
    total_freeform_faces = sum(p.face_count for p in freeform_patches)
    assert total_freeform_faces > 15000, f"Main bottle body should be mostly freeform (got {total_freeform_faces})"

    # End caps should be detected as planes
    plane_patches = [p for p in patches if p.primitive_type == "PLANE"]
    assert len(plane_patches) >= 2, "Bottom and top flat caps should be detected as planes"
