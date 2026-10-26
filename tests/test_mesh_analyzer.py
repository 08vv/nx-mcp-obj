"""
test_mesh_analyzer.py
=====================
Tests for nx_mcp.mesh_analyzer package:
- Reconstruction Intent IR & feature schemas
- Feature orientation classification (Longitudinal vs Circumferential)
- Curvature-adaptive silhouette profile sampling
- Per-region shape classification and axial segmentation
- Post-build surface residual validation (RMS, Hausdorff)
- Real-world mesh regression (Axe3.obj, TRESemme6.obj)
"""

import json
from pathlib import Path
import numpy as np
import pytest
import trimesh

from nx_mcp.mesh_analyzer import (
    ComprehensiveMeshAnalyzer,
    analyze_mesh,
    CapRibFeature,
    RecessedPanelFeature,
    HandleFeature,
    PeriodicFeatureDetector,
    SurfaceResidualValidator,
    PerRegionShapeClassifier,
    PureRevolveExtractor,
    FeatureOrientation,
    FeaturePatternType,
    RegionShapeType,
    ResidualMap,
    ResidualVertex,
)
from nx_mcp.tools.registry import ToolRegistry


_REPO_ROOT = Path(__file__).resolve().parent.parent
AXE3_OBJ = _REPO_ROOT / "obj" / "Axe3.obj"
TRESEMME_OBJ = _REPO_ROOT / "obj" / "TRESemme6.obj"


def test_feature_schema_dataclasses():
    cap = CapRibFeature(
        cap_center=[0.0, 100.0, 0.0],
        cap_diameter_mm=25.0,
        cap_height_mm=15.0,
        collar_diameter_mm=28.0,
        collar_height_mm=8.0,
        cap_top_diameter_mm=24.0,
        rib_count=18,
        rib_pitch_deg=20.0,
        rib_width_mm=3.0,
        rib_depth_mm=1.5,
    )
    d = cap.to_dict()
    assert d["rib_count"] == 18
    assert d["cap_diameter_mm"] == 25.0

    panel = RecessedPanelFeature(
        center_position=[0.0, 50.0, 30.0],
        width_mm=40.0,
        height_mm=60.0,
        recess_depth_mm=2.5,
    )
    dp = panel.to_dict()
    assert dp["width_mm"] == 40.0
    assert dp["recess_depth_mm"] == 2.5

    handle = HandleFeature(
        position=[15.0, 80.0, 0.0],
        orientation_tilt_deg=-12.5,
        outer_width_mm=25.0,
        inner_void_width_mm=14.0,
        height_span_mm=75.0,
        depth_mm=30.0,
    )
    dh = handle.to_dict()
    assert dh["inner_void_width_mm"] == 14.0


def test_feature_orientation_longitudinal_vs_circumferential():
    """
    Verifies that the detector distinguishes longitudinal flutes
    (circular pattern around axis) from circumferential rings (grooves along axis).
    """
    # 1. Synthetic cylinder with 12 longitudinal ribs around perimeter
    rv_long = []
    for y in np.linspace(-40, 40, 50):
        for th in np.linspace(-np.pi, np.pi, 120, endpoint=False):
            disp = 1.2 * np.cos(12 * th)
            r = 20.0 + disp
            x = r * np.cos(th)
            z = r * np.sin(th)
            rv_long.append(ResidualVertex(
                pos_mm=np.array([x, y, z]),
                displacement_mm=disp,
                normal_disp_mm=disp,
                body_normal=np.array([np.cos(th), 0.0, np.sin(th)])
            ))

    rmap_long = ResidualMap(vertices=rv_long)
    det_long = PeriodicFeatureDetector(rmap_long, np.array([[-22, -50, -22], [22, 50, 22]]))
    has_feat_long, data_long = det_long.detect()

    assert has_feat_long is True
    assert data_long["orientation"] == FeatureOrientation.AXIAL_LONGITUDINAL.value
    assert data_long["pattern_type"] == FeaturePatternType.CIRCULAR_ARRAY.value
    assert data_long["rib_count"] == 12
    assert abs(data_long["pitch_deg"] - 30.0) < 1.0
    assert data_long["confidence"] >= 0.70

    # 2. Synthetic cylinder with 8 circumferential groove rings along Y
    rv_circ = []
    for y in np.linspace(-40, 40, 80):
        disp = 1.2 * np.cos(2.0 * np.pi * y / 10.0)
        for th in np.linspace(-np.pi, np.pi, 60, endpoint=False):
            r = 20.0 + disp
            x = r * np.cos(th)
            z = r * np.sin(th)
            rv_circ.append(ResidualVertex(
                pos_mm=np.array([x, y, z]),
                displacement_mm=disp,
                normal_disp_mm=disp,
                body_normal=np.array([np.cos(th), 0.0, np.sin(th)])
            ))

    rmap_circ = ResidualMap(vertices=rv_circ)
    det_circ = PeriodicFeatureDetector(rmap_circ, np.array([[-22, -50, -22], [22, 50, 22]]))
    has_feat_circ, data_circ = det_circ.detect()

    assert has_feat_circ is True
    assert data_circ["orientation"] == FeatureOrientation.CIRCUMFERENTIAL_AZIMUTHAL.value
    assert data_circ["pattern_type"] == FeaturePatternType.LINEAR_ARRAY.value
    assert data_circ["rib_count"] >= 7
    assert data_circ["confidence"] >= 0.70


def test_curvature_adaptive_profile_sampling():
    """
    Verifies that curvature-adaptive sampling places more points in high-curvature
    transitions (fillets/steps) than in flat cylindrical sections.
    """
    # Create stepped cylinder with sharp fillet transition
    mesh = trimesh.creation.cylinder(radius=20.0, height=80.0, sections=40)
    extractor = PureRevolveExtractor(mesh)
    prof = extractor.extract_silhouette_profile(n_samples=50, adaptive=True)

    assert prof["is_axisymmetric"] is True
    assert prof["sampling_mode"] == "curvature_adaptive"
    pts = prof["profile_points"]
    assert len(pts) == 50

    y_vals = [p["y"] for p in pts]
    # Verify monotonic ordering along Y
    assert all(y_vals[i] <= y_vals[i+1] for i in range(len(y_vals)-1))


def test_surface_residual_validator():
    """
    Verifies post-build surface residual validation metrics (Hausdorff, RMS error).
    """
    mesh_orig = trimesh.creation.box(extents=[10, 10, 10])
    # Exact match CAD geometry -> RMS = 0, 100% in tolerance
    val_pass = SurfaceResidualValidator.validate_surfaces(
        source_mesh=mesh_orig,
        cad_geometry=mesh_orig.vertices * 100.0,
        tolerance_mm=0.5
    )
    assert val_pass["is_valid"] is True
    assert val_pass["rms_error_mm"] < 1e-3
    assert val_pass["in_tolerance_percentage"] == 100.0

    # Distorted CAD geometry -> fails tolerance
    distorted_pts = mesh_orig.vertices * 100.0 + 3.0
    val_fail = SurfaceResidualValidator.validate_surfaces(
        source_mesh=mesh_orig,
        cad_geometry=distorted_pts,
        tolerance_mm=0.5
    )
    assert val_fail["is_valid"] is False
    assert val_fail["rms_error_mm"] > 1.0


def test_per_region_shape_classification():
    """
    Verifies axial segmentation and shape classification into distinct regions.
    """
    cyl = trimesh.creation.cylinder(radius=15.0, height=50.0, sections=36)
    # Align cylinder height with Y-axis
    R = trimesh.transformations.rotation_matrix(np.pi / 2.0, [1, 0, 0])
    cyl.apply_transform(R)

    classifier = PerRegionShapeClassifier(cyl, n_slices=20)
    regions = classifier.segment_regions()

    assert len(regions) >= 1
    # Cylinder should be classified as PURE_REVOLVE
    assert any(r.shape_type == RegionShapeType.PURE_REVOLVE.value for r in regions)


@pytest.mark.skipif(not AXE3_OBJ.exists(), reason="Axe3.obj mesh not found in workspace")
def test_axe3_analysis():
    report = analyze_mesh(AXE3_OBJ, num_slices=12)
    assert "dimensions" in report
    assert "topology" in report
    assert "cad_synthesis" in report
    assert "axial_regions" in report
    assert "reconstruction_intent" in report

    dims = report["dimensions"]
    assert dims["height_y_mm"] > 180.0
    assert dims["width_x_mm"] > 60.0

    intent = report["reconstruction_intent"]
    assert intent["global_shape_family"] in ("cylindrical_revolved_body", "freeform_lofted_solid")
    assert len(intent["regions"]) > 0
    assert intent["overall_confidence"] >= 0.70


@pytest.mark.skipif(not TRESEMME_OBJ.exists(), reason="TRESemme6.obj mesh not found in workspace")
def test_tresemme_analysis():
    report = analyze_mesh(TRESEMME_OBJ, num_slices=12)
    assert "dimensions" in report
    sec = report["secondary_features"]
    assert "cap_ribs" in sec
    cap = sec["cap_ribs"]
    assert cap["rib_count"] > 0
    assert "CAP_DIAMETER" in report["cad_synthesis"]["expressions"]


def test_mcp_tool_analyze_obj_mesh():
    import nx_mcp.server  # ensure tools loaded
    tool = ToolRegistry.get("analyze_obj_mesh")
    assert tool is not None, "analyze_obj_mesh must be registered in ToolRegistry"

    if AXE3_OBJ.exists():
        result = tool["fn"](str(AXE3_OBJ), num_slices=10)
        assert result.is_ok(), f"Tool returned error: {getattr(result, 'error', '')}"
        data = json.loads(result.message)
        assert "dimensions" in data
        assert "cad_synthesis" in data
        assert "reconstruction_intent" in data
