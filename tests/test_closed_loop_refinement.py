"""
Tests for Phase 6D Step 2: Closed-Loop Plan Refinement.

Verifies:
  a) Refinement loop triggers when initial segmentation is coarse.
  b) Refinement converges to fewer errors with more zones.
  c) Zone-count cap prevents runaway splits.
  d) Surviving errors are correctly tagged near-miss vs far-miss.
"""
import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import numpy as np
import pytest
from src.nx_mcp.mesh_analyzer.revolve_profile_analyzer import (
    RevolveProfileAnalyzer,
    PROFILE_REFINEMENT_TOLERANCE_PCT,
    RefinementStatus,
)


def _make_synthetic_bottle_profile(n_stations: int = 100):
    """
    Creates a synthetic bottle circularity profile with:
    - Base to body: R = 25.0
    - Shoulder: R drops from 25.0 to 12.0 via a smooth sine transition
    - Neck: R = 12.0
    - Lip: R = 14.0
    """
    z_vals = np.linspace(0.0, 100.0, n_stations)
    r_vals = np.zeros_like(z_vals)
    stations = []

    for idx, z in enumerate(z_vals):
        if z <= 50.0:
            # Body: mild barrel convexity
            r = 25.0 + 2.0 * np.sin(np.pi * z / 50.0)
        elif z <= 75.0:
            # Shoulder: smooth transition from 25 to 12
            t = (z - 50.0) / 25.0
            r = 25.0 - 13.0 * (0.5 - 0.5 * np.cos(np.pi * t))
        elif z <= 90.0:
            # Neck
            r = 12.0
        else:
            # Lip
            r = 14.0
        r_vals[idx] = r
        stations.append({
            "station_idx": idx,
            "z": float(z),
            "radius": float(r),
            "is_circular": True,
            "mean_radius_error": 0.01,
        })

    profile = {
        "is_rotational": True,
        "axis": "Y",
        "stations": stations,
        "max_diameter": float(np.max(r_vals) * 2.0),
        "total_height": 100.0,
    }
    return profile, z_vals, r_vals


class DummyAnalyzer(RevolveProfileAnalyzer):
    """Subclass without file loading for pure geometric profile testing."""
    def __init__(self):
        pass


def test_refinement_triggers_when_coarse():
    """Requirement 4a: Refinement loop triggers when initial segmentation is coarse."""
    analyzer = DummyAnalyzer()
    profile, z_vals, r_vals = _make_synthetic_bottle_profile()

    # Create a deliberately coarse single-zone linear approximation over the whole bottle
    coarse_zone = {
        "zone_idx": 1,
        "name": "BODY",
        "role": "BODY",
        "segment_type": "LINE",
        "z_start": float(z_vals[0]),
        "z_end": float(z_vals[-1]),
        "height": float(z_vals[-1] - z_vals[0]),
        "r_start": float(r_vals[0]),
        "r_end": float(r_vals[-1]),
        "r_mid": float((r_vals[0] + r_vals[-1]) / 2.0),
        "dia_start": float(r_vals[0] * 2.0),
        "dia_end": float(r_vals[-1] * 2.0),
        "dia_max": float(np.max(r_vals) * 2.0),
        "max_dev_mm": 0.0,
    }

    # Initial coarse error should be high
    init_err_pct, init_err_mm, _ = analyzer._evaluate_zone_error(z_vals, r_vals, coarse_zone)
    assert init_err_pct > 20.0, f"Expected high initial error, got {init_err_pct:.1f}%"

    # Run refinement
    refined_zones, status = analyzer.refine_zones(profile, [coarse_zone], max_zones_cap=8)

    # Must have split beyond 1 zone
    assert len(refined_zones) > 1, f"Expected refinement to trigger and split, got {len(refined_zones)} zones"

    # Worst error across refined zones should be dramatically lower than initial
    worst_refined_err = max(analyzer._evaluate_zone_error(z_vals, r_vals, z)[0] for z in refined_zones)
    assert worst_refined_err < init_err_pct, f"Refinement did not reduce error: {worst_refined_err:.1f}% vs {init_err_pct:.1f}%"


def test_refinement_converges_with_more_zones():
    """Requirement 4b: Refinement converges to fewer errors with more zones."""
    analyzer = DummyAnalyzer()
    profile, z_vals, r_vals = _make_synthetic_bottle_profile()

    coarse_zone = {
        "zone_idx": 1,
        "name": "BODY",
        "role": "BODY",
        "segment_type": "LINE",
        "z_start": float(z_vals[0]),
        "z_end": float(z_vals[-1]),
        "height": float(z_vals[-1] - z_vals[0]),
        "r_start": float(r_vals[0]),
        "r_end": float(r_vals[-1]),
        "r_mid": float((r_vals[0] + r_vals[-1]) / 2.0),
        "dia_start": float(r_vals[0] * 2.0),
        "dia_end": float(r_vals[-1] * 2.0),
        "dia_max": float(np.max(r_vals) * 2.0),
        "max_dev_mm": 0.0,
    }

    errors_by_cap = {}
    for cap in [2, 4, 8]:
        zones, status = analyzer.refine_zones(profile, [dict(coarse_zone)], max_zones_cap=cap)
        worst_err = max(analyzer._evaluate_zone_error(z_vals, r_vals, z)[0] for z in zones)
        errors_by_cap[cap] = worst_err

    # As cap increases from 2 to 4 to 8, error must decrease or stay <= previous
    assert errors_by_cap[4] <= errors_by_cap[2] + 1e-4, f"Error did not decrease from cap=2 to cap=4: {errors_by_cap}"
    assert errors_by_cap[8] <= errors_by_cap[4] + 1e-4, f"Error did not decrease from cap=4 to cap=8: {errors_by_cap}"
    assert errors_by_cap[8] < errors_by_cap[2], f"Error did not improve significantly: {errors_by_cap}"


def test_zone_count_cap_prevents_runaway():
    """Requirement 4c: Zone-count cap prevents runaway splits."""
    analyzer = DummyAnalyzer()
    profile, z_vals, r_vals = _make_synthetic_bottle_profile()

    coarse_zone = {
        "zone_idx": 1,
        "name": "BODY",
        "role": "BODY",
        "segment_type": "LINE",
        "z_start": float(z_vals[0]),
        "z_end": float(z_vals[-1]),
        "height": float(z_vals[-1] - z_vals[0]),
        "r_start": float(r_vals[0]),
        "r_end": float(r_vals[-1]),
        "r_mid": float((r_vals[0] + r_vals[-1]) / 2.0),
        "dia_start": float(r_vals[0] * 2.0),
        "dia_end": float(r_vals[-1] * 2.0),
        "dia_max": float(np.max(r_vals) * 2.0),
        "max_dev_mm": 0.0,
    }

    for cap in [3, 5, 7]:
        zones, status = analyzer.refine_zones(profile, [dict(coarse_zone)], max_zones_cap=cap)
        assert len(zones) <= cap, f"Zones {len(zones)} exceeded cap {cap}!"


def test_surviving_errors_tagged_near_miss_vs_far_miss():
    """Requirement 4d: Surviving errors are correctly tagged near-miss vs far-miss."""
    analyzer = DummyAnalyzer()
    profile, z_vals, r_vals = _make_synthetic_bottle_profile()

    coarse_zone = {
        "zone_idx": 1,
        "name": "BODY",
        "role": "BODY",
        "segment_type": "LINE",
        "z_start": float(z_vals[0]),
        "z_end": float(z_vals[-1]),
        "height": float(z_vals[-1] - z_vals[0]),
        "r_start": float(r_vals[0]),
        "r_end": float(r_vals[-1]),
        "r_mid": float((r_vals[0] + r_vals[-1]) / 2.0),
        "dia_start": float(r_vals[0] * 2.0),
        "dia_end": float(r_vals[-1] * 2.0),
        "dia_max": float(np.max(r_vals) * 2.0),
        "max_dev_mm": 0.0,
    }

    # Restrict to only 2 zones so that errors survive
    zones, status = analyzer.refine_zones(profile, [dict(coarse_zone)], max_zones_cap=2)

    # Should have surviving errors
    assert len(status.surviving_errors) > 0, "Expected surviving errors with cap=2"

    for err in status.surviving_errors:
        err_pct = err["error_pct"]
        cls_tag = err["classification"]
        assert "z" in err
        assert "radius_mesh" in err
        assert "radius_plan" in err
        assert "error_mm" in err
        assert "zone_idx" in err
        assert "zone_name" in err

        if err_pct < 2.0 * PROFILE_REFINEMENT_TOLERANCE_PCT:
            assert cls_tag == "near-miss", f"Expected near-miss for error {err_pct}%, got {cls_tag}"
        else:
            assert cls_tag == "far-miss", f"Expected far-miss for error {err_pct}%, got {cls_tag}"

    # Also verify that zones themselves have surviving_errors attached
    total_zone_errs = sum(len(z.get("surviving_errors", [])) for z in zones)
    assert total_zone_errs == len(status.surviving_errors)


def test_loft_adaptive_sketch_refinement():
    """Requirement 3: Loft path refinement adaptively inserts intermediate stations."""
    from src.nx_mcp.mesh_analyzer.feature_recognizer import recognize_feature_plan
    obj_p = repo_root / "obj" / "Vaseline5_reduced.obj"
    if not obj_p.exists():
        pytest.skip(f"Mesh not found: {obj_p}")

    plan = recognize_feature_plan(str(obj_p))
    blended_ranges = [r for r in plan.get("ranges", []) if r.get("classification") == "BLENDED"]
    assert len(blended_ranges) >= 1, "Expected at least one BLENDED loft range in Vaseline"

    # Verify that at least one blended range adaptively inserted intermediate sketches (> 2 sketches)
    adaptive_lofts = [
        b for b in blended_ranges
        if b.get("fitted_parameters", {}).get("sketch_count", 0) > 2
    ]
    assert len(adaptive_lofts) >= 1, f"Expected adaptive multi-sketch insertion, got {[b.get('fitted_parameters', {}).get('sketch_count') for b in blended_ranges]}"

    for loft in adaptive_lofts:
        fp = loft["fitted_parameters"]
        # Error must have converged below or near limit
        assert fp.get("mid_interpolation_iou_error_pct", 100.0) <= 5.0, f"Interpolation error did not drop below 5%: {fp}"

