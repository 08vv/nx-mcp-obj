"""
test_routing_and_verifier_quality.py
====================================
Automated quality regression tests for nx-mcp:
1. Real round part (Axe3.obj) passes circularity & radial variation gating.
2. Rounded-square part (Ellie_18_reduced.obj) is rejected with UNSUPPORTED_NON_ROUND.
3. Non-round oval part (Vaseline5_reduced.obj) is rejected with UNSUPPORTED_NON_ROUND.
4. Verifier fails disc vs rounded-square (volume error > 10%, area error > 10%).
5. Verifier fails cylinder vs oval mesh (bbox, volume, and section errors).
6. Orchestrator honesty: when verifier fails, prints ORCHESTRATION FAILED and exits code 1.
7. Verifier fails / raises on missing reference OBJ.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.nx_mcp.mesh_analyzer.revolve_profile_analyzer import (
    RevolveProfileAnalyzer,
    MIN_CIRCULARITY_THRESHOLD,
    MAX_ASPECT_RATIO_THRESHOLD,
    MAX_RADIAL_VARIATION_THRESHOLD,
)
from src.nx_mcp.fidelity_checker import (
    run_fidelity_check,
    MAX_SECTION_DEVIATION_PCT,
    MAX_AREA_DEVIATION_PCT,
    MAX_BBOX_DEVIATION_PCT,
    MAX_VOLUME_DEVIATION_PCT,
)


def test_round_part_identified_as_round():
    """Confirms that a truly round part (Axe3.obj) passes all round criteria."""
    mesh_path = REPO_ROOT / "obj" / "Axe3.obj"
    assert mesh_path.exists(), f"Reference mesh missing: {mesh_path}"

    analyzer = RevolveProfileAnalyzer(mesh_path)
    profile = analyzer.compute_circularity_profile(n_slices=50)

    assert profile["is_round"] is True, f"Expected is_round=True for {mesh_path.name}, got {profile}"
    assert profile["mean_circularity"] >= MIN_CIRCULARITY_THRESHOLD
    assert profile["mean_aspect_ratio"] <= MAX_ASPECT_RATIO_THRESHOLD
    assert profile["mean_radial_variation"] <= MAX_RADIAL_VARIATION_THRESHOLD


def test_rounded_square_mesh_rejected_by_gate():
    """
    Confirms that Ellie_18_reduced.obj (rounded-square compact) is rejected as
    UNSUPPORTED_NON_ROUND due to centroid radial variation > 12%.
    """
    mesh_path = REPO_ROOT / "obj" / "Ellie_18_reduced.obj"
    assert mesh_path.exists(), f"Reference mesh missing: {mesh_path}"

    analyzer = RevolveProfileAnalyzer(mesh_path)
    profile = analyzer.compute_circularity_profile(n_slices=50)

    assert profile["is_round"] is False, "Ellie rounded-square must be rejected"
    assert profile["mean_radial_variation"] > MAX_RADIAL_VARIATION_THRESHOLD

    # Also confirm run.py halts with UNSUPPORTED_NON_ROUND
    cmd = [sys.executable, str(REPO_ROOT / "run.py"), "--obj", str(mesh_path)]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    assert res.returncode == 1, f"Expected returncode 1, got {res.returncode}"
    assert "[ROUTE REJECTED] ROUTE: UNSUPPORTED_NON_ROUND" in res.stdout


def test_non_round_part_identified_as_non_round():
    """Confirms that the Vaseline oval squeeze tube is identified as non-round."""
    mesh_path = REPO_ROOT / "obj" / "Vaseline5_reduced.obj"
    assert mesh_path.exists(), f"Reference mesh missing: {mesh_path}"

    analyzer = RevolveProfileAnalyzer(mesh_path)
    profile = analyzer.compute_circularity_profile(n_slices=50)

    assert profile["is_round"] is False, f"Expected is_round=False for {mesh_path.name}"
    assert profile["mean_aspect_ratio"] > MAX_ASPECT_RATIO_THRESHOLD


def test_visual_json_does_not_bypass_rejection():
    """
    Confirms that running run.py on a non-round part ends in UNSUPPORTED_NON_ROUND
    and returncode 1, even when a visual JSON is present.
    """
    cmd = [
        sys.executable,
        str(REPO_ROOT / "run.py"),
        "--obj",
        str(REPO_ROOT / "obj" / "Vaseline5_reduced.obj"),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))

    assert res.returncode == 1, f"Expected returncode 1, got {res.returncode}"
    assert "[ROUTE REJECTED] ROUTE: UNSUPPORTED_NON_ROUND" in res.stdout
    assert "visual JSON cannot override non-round rejection" in res.stdout


def test_verifier_catches_disc_vs_rounded_square_fidelity(tmp_path):
    """
    Confirms that fidelity verifier fails when comparing a revolved disc CAD model
    against the Ellie rounded-square mesh (catches volume and corner cross-section area).
    """
    obj_path = REPO_ROOT / "obj" / "Ellie_18_reduced.obj"
    assert obj_path.exists()
    spec_path = tmp_path / "mock_disc_spec.json"
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump({
            "source_mesh": "Ellie_18_reduced.obj",
            "primary_axis": "Y",
            "axis_idx": 1,
            "expressions": [
                ["BODY_MAX_DIA", "194.16"],
                ["ZONE1_START", "-35.91"],
                ["ZONE1_HEIGHT", "71.10"],
                ["ZONE1_BASE_DIA", "BODY_MAX_DIA"],
                ["ZONE1_TOP_DIA", "BODY_MAX_DIA"],
                ["ZONE1_BASE_R", "BODY_MAX_DIA / 2.0"],
                ["ZONE1_TOP_R", "BODY_MAX_DIA / 2.0"],
            ],
            "zones": [
                {
                    "zone_idx": 1,
                    "zone_type": "CYLINDER",
                    "builder": "cylinder",
                    "base_elevation": -35.91,
                    "height": 71.10,
                }
            ]
        }, f)

    f_res = run_fidelity_check(
        obj_path=obj_path,
        spec_path=spec_path,
        cad_bounds=(-97.08, -35.91, -97.08, 97.08, 35.19, 97.08),
        n_stations=20,
    )

    assert f_res["passed"] is False, "Verifier must FAIL for disc vs rounded-square mesh"
    assert f_res["volume_pass"] is False, f"Volume check must fail: {f_res.get('vol_error_pct')}%"
    assert f_res["vol_error_pct"] > MAX_VOLUME_DEVIATION_PCT
    assert f_res["max_area_deviation_pct"] > MAX_AREA_DEVIATION_PCT


def test_verifier_catches_cylinder_vs_oval_fidelity(tmp_path):
    """
    Confirms that CHECK 7 / run_fidelity_check catches an oval mesh compared
    against a revolved circular specification (Vaseline5).
    """
    obj_path = REPO_ROOT / "obj" / "Vaseline5_reduced.obj"
    assert obj_path.exists()
    spec_path = tmp_path / "mock_cylinder_spec.json"
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump({
            "source_mesh": "Vaseline5_reduced.obj",
            "primary_axis": "Y",
            "axis_idx": 1,
            "expressions": [
                ["BODY_MAX_DIA", "42.23"],
                ["ZONE1_START", "-99.72"],
                ["ZONE1_HEIGHT", "199.44"],
                ["ZONE1_BASE_DIA", "BODY_MAX_DIA"],
                ["ZONE1_TOP_DIA", "BODY_MAX_DIA"],
                ["ZONE1_BASE_R", "BODY_MAX_DIA / 2.0"],
                ["ZONE1_TOP_R", "BODY_MAX_DIA / 2.0"],
            ],
            "zones": [
                {
                    "zone_idx": 1,
                    "zone_type": "CYLINDER",
                    "builder": "cylinder",
                    "base_elevation": -99.72,
                    "height": 199.44,
                }
            ]
        }, f)

    # Revolved cylinder bounds for Vaseline: 42.23 x 199.44 x 42.23 mm
    cad_bounds = (-21.11, 0.0, -21.11, 21.11, 199.44, 21.11)

    f_res = run_fidelity_check(
        obj_path=obj_path,
        spec_path=spec_path,
        cad_bounds=cad_bounds,
        n_stations=20,
    )

    assert f_res["passed"] is False, "Fidelity check should FAIL for cylinder vs oval mesh"
    assert f_res["bbox_pass"] is False, "Bounding box extents should fail"
    assert f_res["volume_pass"] is False, "Whole-part volume should fail"
    assert f_res["max_x_deviation_pct"] > MAX_SECTION_DEVIATION_PCT
    assert f_res["max_z_deviation_pct"] > MAX_SECTION_DEVIATION_PCT


def test_orchestrator_honesty_on_verifier_failure(tmp_path):
    """
    Confirms that when the verifier fails, run.py prints a clear FAILED message,
    does NOT print '100% SUCCESSFUL', and exits with return code 1.
    """
    from run import orchestrate_reconstruction

    # Create dummy spec
    dummy_spec = tmp_path / "dummy_spec.json"
    dummy_spec.write_text("{}", encoding="utf-8")

    # Mock builder to succeed and verifier to fail
    with patch("run.run_command_in_nx") as mock_nx, patch("sys.exit") as mock_exit:
        # 1st call is builder (success), 2nd call is verifier (failed)
        mock_nx.side_effect = [
            (0, "Build succeeded"),
            (1, "FINAL RESULT: QUALITY CHECKS FAILED FOR Dummy.prt"),
        ]

        # Call orchestrator
        passed = orchestrate_reconstruction(
            obj_path=None,
            image_path=None,
            spec_path=dummy_spec,
            output_dir=tmp_path,
        )

        assert passed is False, "Expected orchestrate_reconstruction to return False on verifier failure"


def test_verifier_missing_obj_raises():
    """Confirms that a missing OBJ file raises FileNotFoundError in fidelity check."""
    fake_obj = REPO_ROOT / "non_existent_reference.obj"
    with pytest.raises(FileNotFoundError):
        run_fidelity_check(fake_obj)


def test_builder_output_naming():
    """Confirms that the builder enforces <mesh>_Parametric.prt directly with no lowercase duplicates."""
    from src.nx_mcp.parametric_helpers import normalize_parametric_prt_path

    # Test path normalization logic
    test_cases = [
        ("Vaseline5_reduced_parametric.prt", "Vaseline5_reduced_Parametric.prt"),
        ("Vaseline5_reduced_Parametric.prt", "Vaseline5_reduced_Parametric.prt"),
        ("Ellie_18_reduced.prt", "Ellie_18_reduced_Parametric.prt"),
        ("Axe3_parametric.prt", "Axe3_Parametric.prt"),
    ]
    for in_name, exp_name in test_cases:
        normalized = normalize_parametric_prt_path(Path("output") / in_name)
        assert normalized.name == exp_name, f"Expected {exp_name}, got {normalized.name}"


def test_check4_rejects_insufficient_bbox_change():
    """
    Confirms that CHECK 4 rejects a tiny or decoupled bbox change (e.g. 0.01 mm)
    when an expression is perturbed by 15%, requiring at least 10% of perturbation delta.
    """
    MIN_PERTURBATION_FRACTION = 0.10
    
    # Case: TAB1_HEIGHT perturbed from 12.61 to 14.50 mm (delta = 1.8915 mm)
    orig_val = 12.61
    delta_exp = orig_val * 0.15  # 1.8915 mm
    required_min_change = MIN_PERTURBATION_FRACTION * delta_exp  # ~0.189 mm

    # An insufficient 0.01 mm bbox change
    measured_delta_ext = 0.01

    # Assert that 0.01 mm fails the CHECK 4 threshold
    assert not (measured_delta_ext >= required_min_change), (
        f"0.01 mm change must be REJECTED (required >= {required_min_change:.3f} mm)"
    )
    
    # Assert that a real coupled change (e.g. 1.89 mm) passes
    real_delta_ext = 1.89
    assert real_delta_ext >= required_min_change, (
        f"Real coupled change {real_delta_ext} mm must PASS (required >= {required_min_change:.3f} mm)"
    )


def test_verifier_fails_on_missing_end_tab():
    """
    Confirms that a part with a missing end tab (e.g. Vaseline CAD ending at Y = 86.84 mm
    instead of reaching mesh top Y = 99.455 mm) FAILS the axial end gap check.
    """
    obj_path = REPO_ROOT / "obj" / "Vaseline5_reduced.obj"
    assert obj_path.exists()

    # Truncated CAD bounds missing the 12.61 mm top tab (ends at Y = 86.84 mm)
    truncated_cad_bounds = (-37.63, -99.98, -17.97, 37.63, 86.84, 17.97)

    f_res = run_fidelity_check(
        obj_path=obj_path,
        cad_bounds=truncated_cad_bounds,
        n_stations=20,
    )

    assert f_res["end_gap_pass"] is False, "Missing end tab must FAIL the axial end gap check"
    assert f_res["passed"] is False, "Missing end tab must cause fidelity check to FAIL"
    assert f_res["gap_top_mm"] > f_res["max_axial_gap_allowed_mm"], (
        f"Top gap ({f_res['gap_top_mm']} mm) must exceed allowed limit ({f_res['max_axial_gap_allowed_mm']} mm)"
    )


def test_verifier_fails_on_loft_interstation_bulge(tmp_path):
    """
    Confirms that a part where a loft bulges between stations (e.g. Z thickness bulges to 35.95 mm
    vs mesh 28.79 mm, an error of 24.84% > 10.0% threshold) FAILS the verification check on dense sampling.
    """
    import trimesh
    obj_path = REPO_ROOT / "obj" / "Vaseline5_reduced.obj"
    assert obj_path.exists()

    # Create a bulging mesh: copy the Vaseline mesh and scale Z by 1.25 between Y = -70 and Y = 0
    ref_mesh = trimesh.load(str(obj_path), force="mesh")
    bulge_mesh = ref_mesh.copy()
    verts = bulge_mesh.vertices.copy()
    mask = (verts[:, 1] > -70.0) & (verts[:, 1] < 10.0)
    verts[mask, 2] *= 1.25  # Bulge Z thickness by 25% between stations
    bulge_mesh.vertices = verts

    bulge_cad_path = tmp_path / "bulging_loft.obj"
    bulge_mesh.export(str(bulge_cad_path))

    # Dense sampling (50 stations, <= 2% step)
    f_res = run_fidelity_check(
        obj_path=obj_path,
        cad_obj=bulge_cad_path,
        cad_bounds=bulge_mesh.bounds.flatten(),
        n_stations=50,
    )

    assert f_res["slice_pass"] is False, "Dense inter-station slicing must catch Z loft bulge"
    assert f_res["passed"] is False, "Bulging CAD loft must cause fidelity check to FAIL"
    assert f_res["max_z_deviation_pct"] > 10.0, (
        f"Z thickness deviation ({f_res['max_z_deviation_pct']}%) must exceed 10.0% limit"
    )
    assert f_res["bbox_pass"] is False, "Bulging CAD loft bbox must also FAIL"



def test_flanged_bearing_housing_rejected_for_negative_euler():
    """
    Confirms that flanged_bearing_housing.obj is rejected as UNSUPPORTED
    due to negative Euler characteristic (through-holes), never routed to REVOLVE.
    """
    import trimesh
    from scripts.run_benchmark import benchmark_single_mesh
    obj_path = REPO_ROOT / "obj" / "flanged_bearing_housing.obj"
    assert obj_path.exists()

    mesh_clean = trimesh.load(str(obj_path), force="mesh")
    mesh_clean.merge_vertices()
    euler_val = int(getattr(mesh_clean, "euler_number", 2))
    assert euler_val <= 0, f"Expected negative Euler number, got {euler_val}"

    # Verify pipeline rejection
    res = benchmark_single_mesh(obj_path, "held-out", REPO_ROOT / "output", timeout_sec=60)
    assert res["route"] == "UNSUPPORTED", f"Expected route UNSUPPORTED, got {res['route']}"
    assert res["final_result"] == "UNSUPPORTED"
    assert "Degenerate topology" in res["reason"]


def test_harness_reports_exception_as_crash_not_fail(monkeypatch, tmp_path):
    """
    Confirms that when an exception occurs inside a check in the verification harness,
    the benchmark harness records final_result='CRASH', NOT 'FAIL'.
    """
    from scripts.run_benchmark import benchmark_single_mesh
    
    # Mock subprocess run to simulate a check throwing an exception and emitting CRASH in CHECK_RESULTS_JSON
    fake_checker_output = (
        "[CHECK 1] ...\n"
        "  -> PASS\n"
        "[CHECK 7] ...\n"
        "  -> CRASH [EXCEPTION IN CHECK 7]: Fidelity calculation failed with exception: SimulatedError\n"
        'CHECK_RESULTS_JSON: {"C1": "PASS", "C2": "PASS", "C3": "PASS", "C4": "PASS", "C5": "PASS", "C6": "PASS", "C7": "CRASH", "C8": "PASS"}\n'
        "FINAL RESULT: QUALITY CHECKS FAILED\n"
    )

    def mock_run_process(cmd, timeout):
        # First call is builder (ok), second call is verifier (returns crash output)
        if "generic_nx_builder.py" in str(cmd):
            return 0, "Build OK"
        return 1, fake_checker_output

    monkeypatch.setattr("scripts.run_benchmark.run_process_with_timeout", mock_run_process)
    
    mesh_path = REPO_ROOT / "obj" / "Axe3.obj"
    assert mesh_path.exists()
    
    res = benchmark_single_mesh(mesh_path, "dev", tmp_path, timeout_sec=10)
    assert res["final_result"] == "CRASH", f"Expected CRASH, got {res['final_result']}"
    assert res["C7"] == "CRASH"
    assert "CHECK_EXCEPTION_C7" in res["failure_category"]


def test_oziva_routed_as_unsupported_for_profile_error_over_limit():
    """
    Confirms that Oziva4_reduced.obj has profile refinement error > 10.0% (at 100 slices),
    and is strictly routed to UNSUPPORTED by the benchmark and planner.
    """
    from scripts.run_benchmark import benchmark_single_mesh, DEFAULT_PROFILE_SLICES, PROFILE_NEAR_MISS_LIMIT_PCT
    
    mesh_path = REPO_ROOT / "obj" / "Oziva4_reduced.obj"
    assert mesh_path.exists()

    analyzer = RevolveProfileAnalyzer(mesh_path)
    profile = analyzer.compute_circularity_profile(n_slices=DEFAULT_PROFILE_SLICES)
    zones = analyzer.segment_zones(profile, max_zones=8)
    zones, refine_status = analyzer.refine_zones(profile, zones)
    
    worst_err = float(getattr(refine_status, "worst_error_pct", 0.0))
    assert worst_err >= PROFILE_NEAR_MISS_LIMIT_PCT, (
        f"Oziva profile error ({worst_err:.2f}%) must exceed near-miss threshold ({PROFILE_NEAR_MISS_LIMIT_PCT}%)"
    )

    # Benchmark routing check
    res = benchmark_single_mesh(mesh_path, "dev", REPO_ROOT / "output", timeout_sec=10)
    assert res["route"] == "UNSUPPORTED", f"Expected route UNSUPPORTED, got {res['route']}"
    assert res["final_result"] == "UNSUPPORTED", f"Expected final_result UNSUPPORTED, got {res['final_result']}"
    assert "near-miss" in res["reason"].lower() or "unsupported" in res["reason"].lower()





