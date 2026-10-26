"""
test_primitive_feature_extractor.py
===================================
Tests for Phase 2: Primitive Feature Extractor.
Verifies that CAD features (base bodies, holes, pockets/bosses, circular patterns)
are extracted purely from primitive relationships and boundary topology.
"""

import sys
import math
from pathlib import Path
import numpy as np
import pytest
import trimesh

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root / "src"))

from nx_mcp.mesh_analyzer.primitive_segmenter import PrimitiveSegmenter, PrimitivePatch
from nx_mcp.mesh_analyzer.primitive_feature_extractor import PrimitiveFeatureExtractor, ExtractedFeature


def test_axe3_base_revolve_feature():
    """Verify that Axe3 is identified as a REVOLVE_BODY from its dominant cylinder."""
    axe_path = repo_root / "obj" / "Axe3.obj"
    if not axe_path.exists():
        pytest.skip("Axe3.obj not found")

    mesh = trimesh.load(str(axe_path), process=False)
    segmenter = PrimitiveSegmenter(mesh)
    patches = segmenter.segment()

    extractor = PrimitiveFeatureExtractor(mesh, patches)
    features = extractor.extract_features()

    revolve_feats = [f for f in features if f.feature_type == "REVOLVE_BODY"]
    assert len(revolve_feats) == 1, "Should detect exactly one REVOLVE_BODY for Axe3"
    base = revolve_feats[0]
    assert 74.0 <= base.parameters["diameter_mm"] <= 78.0
    assert base.parameters["length_mm"] > 180.0


def test_tresemme6_base_loft_feature():
    """Verify that TRESemme6 is identified as a LOFT_BODY from its freeform shape."""
    tre_path = repo_root / "obj" / "TRESemme6.obj"
    if not tre_path.exists():
        pytest.skip("TRESemme6.obj not found")

    mesh = trimesh.load(str(tre_path), process=False)
    segmenter = PrimitiveSegmenter(mesh)
    patches = segmenter.segment()

    extractor = PrimitiveFeatureExtractor(mesh, patches)
    features = extractor.extract_features()

    loft_feats = [f for f in features if f.feature_type == "LOFT_BODY"]
    assert len(loft_feats) == 1, "Should detect a LOFT_BODY for TRESemme6"
    loft = loft_feats[0]
    assert loft.parameters["extents_mm"][1] > 150.0  # Height extent


def test_synthetic_box_prismatic_extrusion():
    """Verify that a basic box is identified as a PRISMATIC_EXTRUSION."""
    box = trimesh.creation.box(extents=[80.0, 50.0, 30.0])
    segmenter = PrimitiveSegmenter(box)
    patches = segmenter.segment()

    extractor = PrimitiveFeatureExtractor(box, patches)
    features = extractor.extract_features()

    extrude_feats = [f for f in features if f.feature_type == "PRISMATIC_EXTRUSION"]
    assert len(extrude_feats) >= 1, "Should detect PRISMATIC_EXTRUSION for a box"


def test_synthetic_hole_and_circular_pattern():
    """Verify hole and circular pattern extraction on synthetic cylinder primitives."""
    main_cyl = PrimitivePatch(
        patch_id=1,
        primitive_type="CYLINDER",
        confidence=0.98,
        parameters={
            "axis_direction": [0.0, 0.0, 1.0],
            "axis_origin": [0.0, 0.0, 0.0],
            "radius_mm": 50.0,
            "diameter_mm": 100.0,
            "length_mm": 20.0,
            "angular_span_deg": 360.0,
        },
        face_count=200,
        area_mm2=6280.0,
        inlier_rms_error_mm=0.01,
        face_indices=[],
    )

    mesh = trimesh.creation.box(extents=[120.0, 120.0, 20.0])

    bolt_radius = 35.0
    holes = []
    for i in range(4):
        ang = i * (math.pi / 2.0)
        hx = bolt_radius * math.cos(ang)
        hy = bolt_radius * math.sin(ang)
        holes.append(ExtractedFeature(
            feature_id=f"hole_{i}",
            feature_type="HOLE",
            parent_patch_id=1,
            confidence=0.95,
            parameters={
                "center": [hx, hy, 10.0],
                "direction": [0.0, 0.0, 1.0],
                "diameter_mm": 8.0,
                "depth_mm": 20.0,
                "is_through_hole": True,
            },
            source_primitive_ids=[10 + i],
        ))

    extractor = PrimitiveFeatureExtractor(mesh, [main_cyl])
    patterns = extractor._extract_patterns(holes)

    assert len(patterns) == 1, "Should detect 1 circular pattern"
    pat = patterns[0]
    assert pat.feature_type == "CIRCULAR_PATTERN"
    assert pat.parameters["instance_count"] == 4
    assert abs(pat.parameters["pitch_deg"] - 90.0) < 1.0
    assert abs(pat.parameters["pitch_radius_mm"] - 35.0) < 0.5
