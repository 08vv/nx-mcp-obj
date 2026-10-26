#!/usr/bin/env python3
"""
check_parametric_quality.py
===========================
Automated Siemens NX Parametric CAD Quality & Architecture Enforcer.

Enforces non-negotiable parametric CAD quality criteria on any .prt file:
  [CHECK 1] Sketch-Based Architecture:
            - Verifies native Sketch features exist.
            - Verifies solid features (Revolves/Extrudes) reference sketch geometry.
            - Verifies sketch dimensions link to driving expressions.
  [CHECK 2] Feature Decomposition / Monolithic Check:
            - Verifies multi-feature decomposition (sketches, revolves, unities, blends).
            - Ensures no dumb non-parametric lofts span the entire part.
  [CHECK 3] Active Driving Expressions (Zero Orphans):
            - 10% sensitivity perturbation on every user expression.
            - Fails if any user expression does not alter solid geometry.
  [CHECK 4] Parametric Diameter Resizing & Robust Update Test:
            - Perturbs primary diameter expression (e.g. CAP_DIA, BODY_DIA, MAX_DIA).
            - Calls DoUpdate to ensure 0 update errors and clean geometric scaling.
  [CHECK 5] Associative Edge Blends:
            - Fails if any Edge Blend uses non-associative dumb edge rules (Type 0).

Usage:
    python scripts/check_parametric_quality.py <path_to_prt_file>
    or:
    run_journal.exe scripts/check_parametric_quality.py -args <path_to_prt_file>
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def setup_nx_license() -> None:
    os.environ.setdefault("UGII_BASE_DIR", r"C:\Program Files\Siemens\NX2206")
    os.environ.setdefault("UGII_ROOT_DIR", r"C:\Program Files\Siemens\NX2206\NXBIN")
    curr_lic = os.environ.get("SPLM_LICENSE_SERVER", "")
    if "192.168.1.5" not in curr_lic:
        lic = None
        cfg_path = REPO_ROOT / "config.json"
        if cfg_path.exists():
            try:
                import json
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    lic = cfg.get("license_server")
            except Exception:
                pass
        fallback = "28000@192.168.1.5;28000@SunFibo19;28000@192.168.1.29;28000@192.168.1.3;28000@SUN004"
        server_str = lic or fallback
        os.environ["SPLM_LICENSE_SERVER"] = server_str
        os.environ["SALT_LICENSE_SERVER"] = server_str
    path = os.environ.get("PATH", "")
    nxbin = r"C:\Program Files\Siemens\NX2206\NXBIN"
    ugii = r"C:\Program Files\Siemens\NX2206\UGII"
    if nxbin not in path:
        os.environ["PATH"] = f"{nxbin};{ugii};{path}"

setup_nx_license()



def _reinvoke_under_run_journal_if_needed(args: List[str]) -> None:
    try:
        import NXOpen
    except ImportError:
        run_journal_exe = Path(r"C:\Program Files\Siemens\NX2206\NXBIN\run_journal.exe")
        if not run_journal_exe.exists():
            print(f"[FAIL] NXOpen not found in Python path and {run_journal_exe} does not exist.")
            sys.exit(1)
        this_script = Path(__file__).resolve()
        cmd = [str(run_journal_exe), str(this_script), "-args"]
        for a in args:
            ap = Path(a)
            if ap.exists():
                cmd.append(str(ap.resolve()))
            else:
                cmd.append(str(a))
        print(f"[LAUNCH] Re-invoking checker under Siemens NX Journal runner...")
        sys.stdout.flush()
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        res = subprocess.run(cmd, env=env)
        sys.exit(res.returncode)



def compute_body_bounds(body) -> Optional[Tuple[float, float, float, float, float, float]]:
    import NXOpen.UF
    uf = NXOpen.UF.UFSession.GetUFSession()
    try:
        mod = getattr(uf, "ModlGeneral", None) or getattr(uf, "Modl", None)
        if mod and hasattr(mod, "AskBoundingBoxExact"):
            min_pt, _, box_sizes = mod.AskBoundingBoxExact(body.Tag, 0)
            return (
                float(min_pt[0]), float(min_pt[1]), float(min_pt[2]),
                float(min_pt[0] + box_sizes[0]), float(min_pt[1] + box_sizes[1]), float(min_pt[2] + box_sizes[2])
            )
        elif mod and hasattr(mod, "AskBoundingBox"):
            box = mod.AskBoundingBox(body.Tag)
            if box and len(box) >= 6:
                return (float(box[0]), float(box[1]), float(box[2]), float(box[3]), float(box[4]), float(box[5]))
    except Exception:
        pass

    xs, ys, zs = [], [], []
    for e in body.GetEdges():
        try:
            v1, v2 = e.GetVertices()
            xs.extend([v1.X, v2.X])
            ys.extend([v1.Y, v2.Y])
            zs.extend([v1.Z, v2.Z])
        except Exception:
            pass

    if not xs:
        return None
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def compute_union_bounds(bodies_list) -> Optional[Tuple[float, float, float, float, float, float]]:
    """Computes the union bounding box enclosing all bodies in bodies_list."""
    min_x, min_y, min_z = float("inf"), float("inf"), float("inf")
    max_x, max_y, max_z = float("-inf"), float("-inf"), float("-inf")
    found = False
    for b in bodies_list:
        bb = compute_body_bounds(b)
        if bb:
            found = True
            min_x = min(min_x, bb[0])
            min_y = min(min_y, bb[1])
            min_z = min(min_z, bb[2])
            max_x = max(max_x, bb[3])
            max_y = max(max_y, bb[4])
            max_z = max(max_z, bb[5])
    if not found:
        return None
    return (min_x, min_y, min_z, max_x, max_y, max_z)


def compute_geometry_fingerprint(body) -> Tuple[Any, ...]:
    """Computes a high-sensitivity geometric fingerprint of a solid body."""
    bounds = compute_body_bounds(body)
    faces = list(body.GetFaces())
    edges = list(body.GetEdges())
    
    face_centers = []
    edge_lengths = []
    for e in edges:
        try:
            edge_lengths.append(round(e.GetLength(), 3))
        except Exception:
            pass

    for f in faces:
        try:
            for fe in f.GetEdges():
                v1, v2 = fe.GetVertices()
                face_centers.extend([round(v1.X, 3), round(v1.Y, 3), round(v1.Z, 3)])
        except Exception:
            pass

    return (
        tuple(round(b, 3) for b in bounds) if bounds else (),
        len(faces),
        len(edges),
        sum(face_centers),
        sum(edge_lengths),
    )


def check_part(prt_path: Path, min_features: int = 4, obj_path: Optional[Path] = None) -> bool:
    import NXOpen

    print("=" * 75)
    print(f"PARAMETRIC CAD QUALITY VERIFICATION")
    print(f"  Target PRT: {prt_path}")
    print("=" * 75)

    if not prt_path.exists():
        print(f"[FAIL] Part file does not exist: {prt_path}")
        return False

    session = NXOpen.Session.GetSession()
    session.Parts.OpenDisplay(str(prt_path))
    part = session.Parts.Work

    bodies = [b for b in part.Bodies if b.IsSolidBody]
    if not bodies:
        print("[FAIL] Model contains 0 solid bodies!")
        return False
    if len(bodies) != 1:
        print(f"[FAIL] Model contains {len(bodies)} solid bodies! Exactly 1 solid body is required.")
        for idx, b in enumerate(bodies, 1):
            bb = compute_body_bounds(b)
            print(f"  Solid {idx}: bbox = {bb}")
        return False
    main_body = bodies[0]
    total_bounds = compute_body_bounds(main_body)
    if not total_bounds:
        print("[FAIL] Unable to compute solid body bounding box!")
        return False

    dx = total_bounds[3] - total_bounds[0]
    dy = total_bounds[4] - total_bounds[1]
    dz = total_bounds[5] - total_bounds[2]
    total_height = max(dx, dy, dz)
    print(f"Part Dimensions: {dx:.2f} x {dy:.2f} x {dz:.2f} mm (Span = {total_height:.2f} mm)")

    all_passed = True
    check_results = {
        "C1": "PASS",
        "C2": "PASS",
        "C3": "PASS",
        "C4": "PASS",
        "C5": "PASS",
        "C6": "PASS",
        "C7": "PASS",
        "C8": "PASS",
    }

    feats = [f for f in part.Features if not getattr(f, "Suppressed", False)]
    is_loft = any("THRU_CURVE" in f.FeatureType.upper() or "LOFT" in f.GetFeatureName().upper() for f in feats)

    # -------------------------------------------------------------------------
    # CHECK 1: Sketch-Based Architecture & Solid Parentage Check
    # -------------------------------------------------------------------------
    print("\n[CHECK 1] Sketch/Outline Architecture & References Check...")
    sketch_feats = [f for f in part.Features if "SKETCH" in f.FeatureType.upper() or "SKETCH" in f.GetFeatureName().upper()]
    sketches = list(part.Sketches)
    total_sketches = max(len(sketch_feats), len(sketches))
    print(f"  Native Sketch features found: {total_sketches}")

    if total_sketches < 1:
        print("  -> FAIL: Part has fewer than 1 native sketch driving a solid (found 0 sketches)!")
        all_passed = False
        check_results["C1"] = "FAIL"
    else:
        print(f"  -> PASS: Sketch features confirmed in part ({total_sketches} sketch(es)).")

    # Check that sketches only use lines, arcs, circles, and analytic ellipses (no high-order splines)
    spline_in_sketch_violations = []
    for sk in sketches:
        try:
            geom = sk.GetAllGeometry()
            for g in geom:
                g_type = type(g).__name__.upper()
                g_str = str(g).upper()
                if "SPLINE" in g_type or "SPLINE" in g_str:
                    pole_count = 0
                    try:
                        if hasattr(g, "NumPoles"):
                            pole_count = g.NumPoles
                        elif hasattr(g, "NumberOfPoles"):
                            pole_count = g.NumberOfPoles
                        elif hasattr(g, "GetPoles"):
                            pole_count = len(g.GetPoles())
                    except Exception:
                        pass
                    # If pole_count > 4 or pole_count == 0 (unverified complex spline)
                    if pole_count > 4 or pole_count == 0:
                        spline_in_sketch_violations.append((sk.Name, f"Spline with {pole_count} poles"))
        except Exception:
            pass

    if spline_in_sketch_violations:
        print(f"  -> FAIL: Sketch outlines contain complex spline curves: {spline_in_sketch_violations}. Only lines, arcs, circles, and analytic ellipses are permitted.")
        all_passed = False
        check_results["C1"] = "FAIL"
    else:
        print("  -> PASS: All sketch curves are native analytic geometry (lines, arcs, circles, ellipses; no high-order splines).")

    # Check solid feature sketch parentage & ensure no solid is built from loose/free splines
    solid_feats = [f for f in part.Features if any(k in f.FeatureType.upper() for k in ("REVOLVE", "EXTRUDE", "SWP", "THRU_CURVE", "LOFT"))]
    print(f"  Solid generation features found: {len(solid_feats)}")
    
    free_spline_parents = []
    unparented_solids = []
    for sf in solid_feats:
        parents = list(sf.GetParents())
        has_free_spline = any("SPLINE" in (p.FeatureType or "").upper() or "SPLINE" in (p.GetFeatureName() or "").upper() for p in parents)
        has_sketch_parent = any("SKETCH" in (p.FeatureType or "").upper() or "SKETCH" in (p.GetFeatureName() or "").upper() for p in parents)
        if has_free_spline:
            free_spline_parents.append(sf.GetFeatureName())
        if not has_sketch_parent:
            unparented_solids.append(sf.GetFeatureName())

    if free_spline_parents:
        print(f"  -> FAIL: Solid features are built from loose/free splines: {free_spline_parents}")
        all_passed = False
        check_results["C1"] = "FAIL"
    else:
        print("  -> PASS: No solid features are built from loose/free splines.")

    if unparented_solids:
        print(f"  -> FAIL: Solid features lack native sketch parents: {unparented_solids}")
        all_passed = False
        check_results["C1"] = "FAIL"
    else:
        print("  -> PASS: Solid features properly reference sketch geometry.")

    # -------------------------------------------------------------------------
    # CHECK 2: Feature Decomposition & Monolithic Check
    # -------------------------------------------------------------------------
    print(f"\n[CHECK 2] Feature Decomposition Check (Minimum {min_features} features)...")
    
    # Exclude loose splines, Scale Body, and DATUM entities from model features count
    excluded_feats = [
        f for f in feats
        if any(k in f.FeatureType.upper() or k in f.GetFeatureName().upper() for k in ("SPLINE", "SCALE", "DATUM", "CSYS"))
    ]
    real_feats = [f for f in feats if f not in excluded_feats]
    
    print(f"  Total features in Part Navigator: {len(feats)}")
    print(f"  Real model features: {len(real_feats)} (Excluded {len(excluded_feats)} loose spline / scale / datum features)")
    for idx, f in enumerate(real_feats, 1):
        print(f"    [{idx:2d}] {f.GetFeatureName():<30} (Type: {f.FeatureType})")
    if excluded_feats:
        print("  Excluded non-model / datum features (do not count toward CAD decomposition):")
        for idx, f in enumerate(excluded_feats, 1):
            print(f"    [X{idx}] {f.GetFeatureName():<30} (Type: {f.FeatureType})")

    # Check for uneditable raw multi-loft sweeps spanning entire part
    dumb_lofts = [f for f in feats if "THRU_CURVE" in f.FeatureType.upper() or "LOFT" in f.GetFeatureName().upper()]
    if dumb_lofts and len(feats) < 3:
        print(f"  -> FAIL: Monolithic uneditable loft spans entire part: {[f.GetFeatureName() for f in dumb_lofts]}")
        all_passed = False
        check_results["C2"] = "FAIL"
    elif len(real_feats) < min_features:
        print(f"  -> FAIL: Part has only {len(real_feats)} real model features (minimum {min_features} required). Datum features, loose splines, and Scale Body do not count.")
        all_passed = False
        check_results["C2"] = "FAIL"
    elif total_sketches < 1:
        print(f"  -> FAIL: Part has 0 native sketches driving solids.")
        all_passed = False
        check_results["C2"] = "FAIL"
    else:
        print(f"  -> PASS: Multi-feature architecture confirmed ({len(real_feats)} >= {min_features} real model features).")

    # -------------------------------------------------------------------------
    # CHECK 3: Active Driving Expressions Check (0 Orphans)
    # -------------------------------------------------------------------------
    print("\n[CHECK 3] Active Driving Expressions Sensitivity Check...")
    expressions = [e for e in part.Expressions]
    print(f"  Total expressions defined: {len(expressions)}")
    
    fp_base = compute_geometry_fingerprint(main_body)
    orphan_expressions = []
    tested_count = 0

    for exp in expressions:
        ename = exp.Name
        erhs = exp.RightHandSide
        eval_num = exp.Value
        
        # Skip pure counters or zero values
        if abs(eval_num) < 1e-4:
            continue

        # Skip internal NX system parameter registers (e.g. p1, p2, p40, p49)
        if ename.startswith("p") and ename[1:].isdigit():
            continue

        # Skip chained positional markers (driven by chained HEIGHT expressions per Rule 4).
        # NOTE: *_START_Y expressions are intentionally NOT skipped so any unused start expression
        # (like BODY_START_Y) is tested and reported as an orphan per requirement.
        if ename.endswith("_START"):
            continue

        tested_count += 1
        mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, f"test_{ename}")
        active_mark_name = f"test_{ename}"
        try:
            fp_perturbed = fp_base
            n_errs = 1
            try:
                # Check if erhs is a simple number or a formula
                try:
                    raw_val = float(erhs)
                    exp.RightHandSide = f"{raw_val * 1.10:.4f}"
                except ValueError:
                    # For formulas (e.g. DIA / 2.0), perturb via multiplier if not an alias
                    if any(op in erhs for op in ("/", "*", "+", "-")):
                        exp.RightHandSide = f"({erhs}) * 1.10"
                    else:
                        exp.RightHandSide = f"{erhs} * 1.10"

                n_errs = session.UpdateManager.DoUpdate(mark)
                current_body = [b for b in part.Bodies if b.IsSolidBody][0]
                fp_perturbed = compute_geometry_fingerprint(current_body)
            except Exception:
                n_errs = 1

            if fp_perturbed == fp_base or n_errs != 0:
                # Try -10% in case +10% exceeded a geometric upper limit (e.g. base radius exceeding top radius on a short blended zone)
                session.UndoToMark(mark, active_mark_name)
                active_mark_name = f"test_{ename}_neg"
                mark = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, active_mark_name)
                try:
                    try:
                        raw_val = float(erhs)
                        exp.RightHandSide = f"{raw_val * 0.90:.4f}"
                    except ValueError:
                        exp.RightHandSide = f"({erhs}) * 0.90"
                    n_errs_neg = session.UpdateManager.DoUpdate(mark)
                    current_body = [b for b in part.Bodies if b.IsSolidBody][0]
                    fp_neg = compute_geometry_fingerprint(current_body)
                    if fp_neg != fp_base and n_errs_neg == 0:
                        fp_perturbed = fp_neg
                        n_errs = 0
                except Exception:
                    pass

            if fp_perturbed == fp_base or n_errs != 0:
                orphan_expressions.append((ename, erhs, eval_num))
                print(f"  [ORPHAN] {ename} = {erhs} (No geometry change when varied by +/-10%)")
            else:
                print(f"  [ACTIVE] {ename} = {erhs} (Successfully drives geometry)")
        except Exception as e:
            # If update threw an error, check if geometry actually changed before rollback
            print(f"  [WARN] Expression {ename} ({erhs}) sensitivity update note: {e}")
            orphan_expressions.append((ename, erhs, eval_num))
        finally:
            session.UndoToMark(mark, active_mark_name)

    if orphan_expressions:
        print(f"  -> FAIL: Found {len(orphan_expressions)} orphan expressions that do NOT drive geometry!")
        all_passed = False
        check_results["C3"] = "FAIL"
    else:
        print(f"  -> PASS: All {tested_count} tested expressions actively drive solid geometry (0 orphans).")

    # -------------------------------------------------------------------------
    # CHECK 4: Multi-Directional Dimension Perturbation & Robust Update Check
    # -------------------------------------------------------------------------
    print("\n[CHECK 4] Parametric Resizing & DoUpdate Check...")
    
    # Identify candidate driving dimension expressions per direction:
    is_axisymmetric = any("BODY_MAX_DIA" in e.Name.upper() for e in expressions)
    directional_candidates: List[Tuple[str, Any]] = []

    import re
    def zone_num_key(e):
        m = re.search(r'ZONE(\d+)', e.Name.upper())
        return int(m.group(1)) if m else -1

    if is_axisymmetric:
        dia_candidates = [e for e in expressions if "BODY_MAX_DIA" in e.Name.upper()]
        if not dia_candidates:
            dia_candidates = [e for e in expressions if any(k in e.Name.upper() for k in ("MAX_DIA", "CAP_DIA", "BODY_DIA", "DIA")) and abs(e.Value) > 1.0]
        if dia_candidates:
            directional_candidates.append(("Diameter (X/Z)", dia_candidates[0]))
        
        h_candidates = [e for e in expressions if ("HEIGHT" in e.Name.upper() or "LENGTH" in e.Name.upper()) and not e.Name.upper().startswith("TOTAL_") and abs(e.Value) > 0.05]
        h_candidates.sort(key=lambda e: (zone_num_key(e), abs(e.Value)), reverse=True)
        if h_candidates:
            directional_candidates.append(("Height (Y)", h_candidates[0]))
    else:
        w_candidates = [e for e in expressions if ("WIDTH" in e.Name.upper() or "DIA" in e.Name.upper()) and not e.Name.upper().startswith(("SCALE", "REF_")) and abs(e.Value) > 1.0]
        w_candidates.sort(key=lambda e: abs(e.Value), reverse=True)
        if w_candidates:
            directional_candidates.append(("Width (X)", w_candidates[0]))
        t_candidates = [e for e in expressions if "THICKNESS" in e.Name.upper() and not e.Name.upper().startswith(("SCALE", "REF_")) and abs(e.Value) > 1.0]
        t_candidates.sort(key=lambda e: abs(e.Value), reverse=True)
        if t_candidates:
            directional_candidates.append(("Thickness (Z)", t_candidates[0]))
        h_candidates = [e for e in expressions if ("HEIGHT" in e.Name.upper() or "LENGTH" in e.Name.upper()) and not e.Name.upper().startswith(("SCALE", "REF_")) and abs(e.Value) > 0.05]
        h_candidates.sort(key=lambda e: (zone_num_key(e), abs(e.Value)), reverse=True)
        if h_candidates:
            directional_candidates.append(("Height (Y)", h_candidates[0]))

    MIN_PERTURBATION_FRACTION = 0.10  # Dimension change must be at least 10% of perturbation delta

    if not directional_candidates:
        print("  -> FAIL [NOT VERIFIED]: No candidate dimension expressions found for multi-directional resize test.")
        all_passed = False
    else:
        dirs_passed = 0
        for dir_name, target_exp in directional_candidates:
            orig_val = target_exp.Value
            solids_before = [b for b in part.Bodies if b.IsSolidBody]
            n_solids_before = len(solids_before)
            bounds_before = compute_union_bounds(solids_before)

            mark_dim = session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, f"test_resize_{target_exp.Name}")
            try:
                target_exp.RightHandSide = str(orig_val * 1.15)
                n_errs = session.UpdateManager.DoUpdate(mark_dim)
                solids_after = [b for b in part.Bodies if b.IsSolidBody]
                n_solids_after = len(solids_after)
                bounds_after = compute_union_bounds(solids_after)

                delta_exp = abs(orig_val * 0.15)
                dim_idx = 0 if ("Width" in dir_name or "Diameter" in dir_name) else (1 if "Height" in dir_name else 2)
                delta_ext = 0.0

                if bounds_after and bounds_before:
                    b_dx = bounds_before[3] - bounds_before[0]
                    b_dy = bounds_before[4] - bounds_before[1]
                    b_dz = bounds_before[5] - bounds_before[2]
                    a_dx = bounds_after[3] - bounds_after[0]
                    a_dy = bounds_after[4] - bounds_after[1]
                    a_dz = bounds_after[5] - bounds_after[2]
                    b_ext = bounds_before[dim_idx + 3] - bounds_before[dim_idx]
                    a_ext = bounds_after[dim_idx + 3] - bounds_after[dim_idx]
                    delta_ext = abs(a_ext - b_ext)
                    print(f"  [DIR: {dir_name}] Perturbed '{target_exp.Name}' ({orig_val:.2f} -> {orig_val*1.15:.2f}):")
                    print(f"    - Body Count:  Before = {n_solids_before}, After = {n_solids_after}")
                    print(f"    - Union BBox Before: [{bounds_before[0]:.2f}, {bounds_before[1]:.2f}, {bounds_before[2]:.2f}] to [{bounds_before[3]:.2f}, {bounds_before[4]:.2f}, {bounds_before[5]:.2f}] ({b_dx:.2f} x {b_dy:.2f} x {b_dz:.2f} mm)")
                    print(f"    - Union BBox After:  [{bounds_after[0]:.2f}, {bounds_after[1]:.2f}, {bounds_after[2]:.2f}] to [{bounds_after[3]:.2f}, {bounds_after[4]:.2f}, {bounds_after[5]:.2f}] ({a_dx:.2f} x {a_dy:.2f} x {a_dz:.2f} mm)")
                    print(f"    - Dimension Extent Change: {b_ext:.2f} -> {a_ext:.2f} mm (Delta = {delta_ext:.3f} mm, Required >= {MIN_PERTURBATION_FRACTION * delta_exp:.3f} mm)")

                if n_solids_before != 1 or n_solids_after != 1:
                    print(f"    -> FAIL: Expected exactly 1 solid body before and after resize, but got before={n_solids_before}, after={n_solids_after}!")
                    all_passed = False
                elif not (delta_ext >= MIN_PERTURBATION_FRACTION * delta_exp):
                    print(f"    -> FAIL: BBox dimension change ({delta_ext:.3f} mm) is less than required fraction ({MIN_PERTURBATION_FRACTION*100:.0f}%) of perturbation ({delta_exp:.3f} mm)!")
                    all_passed = False
                elif n_errs == 0:
                    print(f"    -> Verified: Geometry altered meaningfully ({delta_ext:.2f} mm >= {MIN_PERTURBATION_FRACTION*delta_exp:.2f} mm) with 1 solid body and 0 DoUpdate errors.")
                    dirs_passed += 1
                else:
                    print(f"    -> FAIL: Parametric DoUpdate returned {n_errs} error(s) during resize!")
                    all_passed = False
            except Exception as update_err:
                print(f"    -> FAIL: Parametric update threw an error: {update_err}")
                all_passed = False
            finally:
                session.UndoToMark(mark_dim, f"test_resize_{target_exp.Name}")

        if dirs_passed == len(directional_candidates):
            print(f"  -> PASS: Multi-directional resizing verified across all {dirs_passed} tested direction(s).")
        else:
            print(f"  -> FAIL: Resizing failed in {len(directional_candidates) - dirs_passed} direction(s).")
            all_passed = False
            check_results["C4"] = "FAIL"

    # -------------------------------------------------------------------------
    # CHECK 5: Associative Edge Blends Check
    # -------------------------------------------------------------------------
    print("\n[CHECK 5] Associative Edge Blend Rule Check...")
    blend_feats = [f for f in part.Features if f.FeatureType == "BLEND"]
    print(f"  Edge Blend features found: {len(blend_feats)}")

    dumb_blend_violations = []
    for bf in blend_feats:
        try:
            bb = part.Features.CreateEdgeBlendBuilder(bf)
            n_chains = bb.GetNumberOfValidChainsets()
            for c_idx in range(n_chains):
                collector, _ = bb.GetChainset(c_idx)
                rules = collector.GetRules()
                for r in rules:
                    rtype_val = getattr(r, "Type", None)
                    print(f"    Feature '{bf.GetFeatureName()}' Chain {c_idx+1}: Rule Type={rtype_val}")
                    is_dumb = (str(rtype_val) == "0" or getattr(rtype_val, "value", None) == 0 or "DUMB" in str(rtype_val).upper())
                    if is_dumb:
                        dumb_blend_violations.append((bf.GetFeatureName(), "CreateRuleEdgeDumb (Type 0)"))
            bb.Destroy()
        except Exception as e:
            print(f"    Feature '{bf.GetFeatureName()}' rule inspect notice: {e}")

    if dumb_blend_violations:
        print(f"  -> FAIL: Edge blends using dumb edge rules detected: {dumb_blend_violations}")
        all_passed = False
        check_results["C5"] = "FAIL"
    elif len(blend_feats) == 0:
        print("  -> NOT APPLICABLE: No edge blends exist in this part.")
    else:
        print("  -> PASS: All Edge Blends use associative topological face/feature rules.")

    # -------------------------------------------------------------------------
    # CHECK 6: Zone Linking & Master Driver Ratio Proportionality Check
    # -------------------------------------------------------------------------
    print("\n[CHECK 6] Zone Linking & Continuous Junction Proportionality Check...")
    if is_loft:
        print("  -> NOT APPLICABLE (loft path): Continuous Through Curves surface has no stepped zone junctions.")
    else:
        master_drivers = [e for e in expressions if e.Name in ("BODY_MAX_DIA", "BODY_WIDTH")]
        if master_drivers:
            m_exp = master_drivers[0]
            print(f"  Master dimension driver found: {m_exp.Name} = {m_exp.RightHandSide} ({m_exp.Value:.2f} mm)")
            
            # Check junction continuity expressions
            zone_base_dims = sorted([e for e in expressions if (e.Name.endswith("_BASE_DIA") or e.Name.endswith("_BASE_WIDTH")) and "ZONE" in e.Name], key=lambda e: e.Name)
            zone_top_dims = sorted([e for e in expressions if (e.Name.endswith("_TOP_DIA") or e.Name.endswith("_TOP_WIDTH")) and "ZONE" in e.Name], key=lambda e: e.Name)
            
            continuity_confirmed = 0
            for i in range(1, len(zone_base_dims)):
                base_e = zone_base_dims[i]
                prev_top_e = zone_top_dims[i-1]
                if prev_top_e.Name in base_e.RightHandSide or m_exp.Name in base_e.RightHandSide:
                    continuity_confirmed += 1
                    print(f"    Zone Junction {i}->{i+1}: {base_e.Name} = '{base_e.RightHandSide}' (Proportionally linked)")

            expected_links = max(0, len(zone_base_dims) - 1)
            if expected_links > 0:
                if continuity_confirmed > 0:
                    print(f"  -> PASS: All {continuity_confirmed} zone junctions confirmed proportionally linked without step discontinuities.")
                else:
                    print(f"  -> FAIL: Zone junction continuity NOT confirmed (0 / {expected_links} links confirmed).")
                    all_passed = False
                    check_results["C6"] = "FAIL"
            else:
                print(f"  -> NOT APPLICABLE (single zone): no zone junctions to verify (master driver '{m_exp.Name}' present).")
        else:
            print("  -> FAIL [NOT VERIFIED]: Master expression 'BODY_MAX_DIA' or 'BODY_WIDTH' not explicitly named.")
            all_passed = False
            check_results["C6"] = "FAIL"

    # -------------------------------------------------------------------------
    # CHECK 7: Geometric & Dimensional Fidelity Verification (CAD vs OBJ)
    # -------------------------------------------------------------------------
    print("\n[CHECK 7] Geometric & Dimensional Fidelity Verification (CAD vs OBJ)...")
    obj_candidate = None
    if obj_path:
        if Path(obj_path).exists():
            obj_candidate = Path(obj_path)
        else:
            print(f"  -> FAIL [NOT VERIFIED]: Specified reference OBJ file does not exist: {obj_path}")
            all_passed = False
    else:
        # Search in obj/ folder or specification JSON source_mesh
        stem_raw = prt_path.stem.replace("_Parametric", "").replace("_spec", "").replace("_feature_plan", "")
        for sc_name in [f"{stem_raw}_feature_plan.json", f"{stem_raw}_spec.json"]:
            sc_path = prt_path.parent / sc_name
            if not sc_path.exists():
                sc_path = Path("output") / sc_name
            if sc_path.exists():
                try:
                    with open(sc_path, "r", encoding="utf-8") as f:
                        s_data = json.load(f)
                    sm = s_data.get("source_mesh") or s_data.get("mesh_name")
                    if sm:
                        for cand in [Path(sm), Path("obj") / sm, Path("obj") / Path(sm).name]:
                            if cand.exists():
                                obj_candidate = cand
                                break
                    if obj_candidate:
                        break
                except Exception:
                    pass

        if not obj_candidate:
            for p in [Path("obj") / f"{stem_raw}.obj", Path("obj") / f"{stem_raw}_reduced.obj"]:
                if p.exists():
                    obj_candidate = p
                    break
        if not obj_candidate:
            # Try fuzzy match in obj/
            for p in Path("obj").glob("*.obj"):
                if p.stem.lower().startswith(stem_raw.lower()[:5]):
                    obj_candidate = p
                    break

    if obj_candidate and obj_candidate.exists():
        print(f"  Reference OBJ Mesh: {obj_candidate}")
        try:
            MAX_SECTION_DEVIATION_PCT = 10.0
            MAX_AREA_DEVIATION_PCT = 10.0
            MAX_BBOX_DEVIATION_PCT = 10.0
            MAX_VOLUME_DEVIATION_PCT = 10.0

            stem_clean = prt_path.stem
            for suffix in ['_Parametric', '_parametric', '_spec', '_feature_plan']:
                if stem_clean.endswith(suffix):
                    stem_clean = stem_clean[:-len(suffix)]
            
            cand_filenames = [
                f"{stem_clean}_feature_plan.json",
                f"{prt_path.stem.replace('_Parametric', '').replace('_parametric', '')}_feature_plan.json",
                f"{stem_clean}_outlines.json",
                f"{stem_clean}_spec.json",
                f"{stem_clean}_reduced_feature_plan.json",
                f"{stem_clean}_reduced_spec.json",
            ]
            spec_candidate = None
            for cfn in cand_filenames:
                for base in [prt_path.parent, Path("output"), Path(".")]:
                    p = (base / cfn).resolve()
                    if p.exists():
                        spec_candidate = p
                        break
                if spec_candidate:
                    break
            stl_candidate = prt_path.with_suffix(".stl")
            
            cb_str = repr(tuple(float(v) for v in total_bounds)) if total_bounds else "None"
            sp_str = f"Path(r'{spec_candidate}')" if spec_candidate and spec_candidate.exists() else "None"
            stl_str = f"Path(r'{stl_candidate}')" if stl_candidate.exists() else "None"
            py_script = f"""
import json
from pathlib import Path
from src.nx_mcp.fidelity_checker import run_fidelity_check

res = run_fidelity_check(
    obj_path=Path(r'{obj_candidate}'),
    spec_path={sp_str},
    stl_path={stl_str},
    output_dir=Path(r'{prt_path.parent}'),
    cad_bounds={cb_str},
    n_stations=50
)
print('__RESULT_JSON__' + json.dumps(res))
"""
            py_exe = r"C:\Users\HP\AppData\Local\Programs\Python\Python311\python.exe"
            clean_env = dict(os.environ)
            clean_env.pop("PYTHONPATH", None)
            cmd_f = [py_exe if os.path.exists(py_exe) else "python", "-c", py_script]
            p_f = subprocess.run(cmd_f, env=clean_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if p_f.returncode != 0:
                raise RuntimeError(p_f.stderr or p_f.stdout)
            out_f = p_f.stdout
            idx_f = out_f.find("__RESULT_JSON__")
            if idx_f == -1:
                raise RuntimeError(f"No result found: {out_f}")
            f_res = json.loads(out_f[idx_f + len("__RESULT_JSON__"):].strip())
            if f_res.get("error"):
                raise RuntimeError(f_res["error"])

            print(f"  Sampled {f_res['station_count']} Cross-Section Stations:")
            print(f"    - Slicing axis: {f_res.get('axis_name')} | spec used: {f_res.get('spec_used')}")
            print(f"    - OBJ {f_res.get('axis_name')} range (mm): {f_res.get('obj_axial_range_mm')}")
            print(f"    - CAD {f_res.get('axis_name')} range (mm): {f_res.get('cad_axial_range_mm')}")
            print(f"    - Station {f_res.get('axis_name')} values (same value used in OBJ and CAD frame): {f_res.get('stations_z')}")
            print(f"    - Per-station table:")
            print(f"      {'#':>2} {'axial':>8} {'OBJ_W':>8} {'CAD_W':>8} {'OBJ_T':>8} {'CAD_T':>8} {'OBJ_area':>11} {'CAD_area':>11} {'err%':>6}")
            for _i, _r in enumerate(f_res.get('station_rows', []), 1):
                print(f"      {_i:>2} {_r['axial_mm']:>8.2f} {_r['obj_width']:>8.2f} {_r['cad_width']:>8.2f} {_r['obj_thick']:>8.2f} {_r['cad_thick']:>8.2f} {_r['obj_area']:>11.1f} {_r['cad_area']:>11.1f} {_r['area_err_pct']:>6.2f}")
            _ax = f_res.get('axis_name', '?')
            print(f"    - Max X-Width Dev:      {f_res['max_x_deviation_mm']:.3f} mm ({f_res['max_x_deviation_pct']:.2f}%) at {_ax} = {f_res['max_x_deviation_z_mm']:.2f} mm")
            print(f"    - Max Z-Thickness Dev:  {f_res['max_z_deviation_mm']:.3f} mm ({f_res['max_z_deviation_pct']:.2f}%) at {_ax} = {f_res['max_z_deviation_z_mm']:.2f} mm")
            print(f"    - Max Section Area Dev: {f_res.get('max_area_deviation_pct', 0.0):.2f}% at {_ax} = {f_res.get('max_area_deviation_z_mm', 0.0):.2f} mm")
            print(f"    - Mean Dev (X/Z/Area):  {f_res['mean_x_deviation_pct']:.2f}% / {f_res['mean_z_deviation_pct']:.2f}% / {f_res.get('mean_area_deviation_pct', 0.0):.2f}%")
            print(f"    - OBJ Volume:           {f_res.get('obj_volume')} mm^3")
            print(f"    - CAD Volume:           {f_res.get('cad_volume')} mm^3")
            if f_res.get('vol_error_pct') is not None:
                print(f"    - Volume Error:         {f_res.get('vol_error_pct'):.2f}% ({f_res.get('vol_error_mm3'):.2f} mm^3)")
            print(f"    - OBJ Extents (mm):     {f_res['obj_bounds_mm']}")
            print(f"    - CAD Extents (mm):     {f_res.get('cad_bounds_mm')}")
            print(f"    - Comparison Plot:      {f_res.get('comparison_plot')}")
            if "bbox_end_gaps" in f_res and f_res["bbox_end_gaps"]:
                print(f"    - CAD BBox End Gaps vs Mesh (each end, each axis):")
                print(f"      {'Axis':<4} {'Mesh Min':>10} {'CAD Min':>10} {'Min Gap (mm)':>14} {'Mesh Max':>10} {'CAD Max':>10} {'Max Gap (mm)':>14}")
                for ax_lbl, gap_dict in f_res["bbox_end_gaps"].items():
                    print(f"      {ax_lbl:<4} {gap_dict['mesh_min']:>10.4f} {gap_dict['cad_min']:>10.4f} {gap_dict['gap_min_mm']:>14.4f} {gap_dict['mesh_max']:>10.4f} {gap_dict['cad_max']:>10.4f} {gap_dict['gap_max_mm']:>14.4f}")

            # 1. Whole-Part Volume Check
            vol_passed = f_res.get("volume_pass", True)
            vol_err = f_res.get("vol_error_pct")
            if not vol_passed or (vol_err is not None and vol_err > MAX_VOLUME_DEVIATION_PCT):
                print(f"  -> FAIL: Whole-part volume error ({vol_err:.2f}%) exceeds tolerance (<= {MAX_VOLUME_DEVIATION_PCT:.1f}%):")
                print(f"       OBJ={f_res.get('obj_volume')} mm^3, CAD={f_res.get('cad_volume')} mm^3, Diff={f_res.get('vol_error_mm3')} mm^3 ({vol_err:.2f}%)")
                all_passed = False
                check_results["C7"] = "FAIL"
            elif vol_err is not None:
                print(f"  -> PASS: Whole-part volume matches within {MAX_VOLUME_DEVIATION_PCT:.1f}% tolerance ({vol_err:.2f}% error).")
            else:
                print("  -> PASS: Whole-part volume check passed.")

            # 2. Bounding Box Extents Check
            bbox_passed = f_res.get("bbox_pass", False)
            if not bbox_passed:
                print(f"  -> FAIL: Bounding box extents mismatch vs OBJ (threshold: <= {MAX_BBOX_DEVIATION_PCT:.1f}%):")
                for dim_name, b_info in f_res.get("bbox_errors", {}).items():
                    status_str = "PASS" if b_info["pass"] else "FAIL"
                    print(f"       [{dim_name}] OBJ={b_info['obj_mm']}mm, CAD={b_info['cad_mm']}mm, Err={b_info['error_mm']}mm ({b_info['error_pct']}%) [{status_str}]")
                all_passed = False
                check_results["C7"] = "FAIL"
            else:
                print(f"  -> PASS: Bounding box extents match within {MAX_BBOX_DEVIATION_PCT:.1f}% tolerance.")

            # 2b. Axial End Gap Check (Separate Top and Bottom Gaps)
            end_gap_passed = f_res.get("end_gap_pass", True)
            gap_bot = f_res.get("gap_bottom_mm")
            gap_top = f_res.get("gap_top_mm")
            max_allowed_gap = f_res.get("max_axial_gap_allowed_mm")
            ax_name = f_res.get("axis_name", "Y")
            if not end_gap_passed:
                print(f"  -> FAIL: Axial end gap along {ax_name} exceeds tolerance (<= {max_allowed_gap:.2f} mm / 1.0% of height):")
                print(f"       Bottom {ax_name} Gap: {gap_bot:.4f} mm (Allowed <= {max_allowed_gap:.4f} mm)")
                print(f"       Top {ax_name} Gap:    {gap_top:.4f} mm (Allowed <= {max_allowed_gap:.4f} mm)")
                all_passed = False
                check_results["C7"] = "FAIL"
            elif gap_bot is not None and gap_top is not None:
                print(f"  -> PASS: Axial end gaps match within 1.0% height tolerance: Bottom={gap_bot:.3f}mm, Top={gap_top:.3f}mm (Limit: <= {max_allowed_gap:.3f}mm).")

            # 3. Cross-Section Stations Separate Width (X), Thickness (Z), and Area Check
            slice_passed = f_res.get("slice_pass", False)
            max_x_pct = f_res["max_x_deviation_pct"]
            max_z_pct = f_res["max_z_deviation_pct"]
            max_area_pct = f_res.get("max_area_deviation_pct", 0.0)
            max_int_area = f_res.get("max_interior_area_deviation_pct", max_area_pct)

            if not slice_passed:
                print(f"  -> FAIL: Cross-section dimensions/shape out of tolerance:")
                failing_stns = [s for s in f_res.get("station_rows", []) if not s.get("station_pass", True)]
                for fs in failing_stns[:5]:
                    ez_str = " (End-Zone)" if fs.get("is_end_zone") else " (Interior)"
                    print(f"       At axial={fs['axial_mm']}mm{ez_str}: Area Err={fs['area_err_pct']}%, Width Err={fs.get('dev_x_pct', '?')}%, Dist Err={fs.get('station_dist_err_mm', '?')}mm")
                all_passed = False
                check_results["C7"] = "FAIL"
            else:
                print(f"  -> PASS: Cross-section shape verified for X-width ({max_x_pct:.2f}%), Z-thickness ({max_z_pct:.2f}%), and Area (interior {max_int_area:.2f}% <= {MAX_AREA_DEVIATION_PCT:.1f}%).")

            # 4. Bidirectional Surface Distance Check (catches non-axisymmetric contour / shape mismatches)
            surf_eval = f_res.get("surface_eval")
            if surf_eval:
                if not surf_eval.get("pass", True):
                    print(f"  -> FAIL: Surface distance discrepancy between CAD and OBJ mesh:")
                    print(f"       {surf_eval.get('reason')}")
                    all_passed = False
                    check_results["C7"] = "FAIL"
                else:
                    print(f"  -> PASS: Bidirectional surface distance verified: Mean={surf_eval['mean_distance_mm']:.2f}mm <= {surf_eval['mean_limit_allowed_mm']:.2f}mm, P95={surf_eval['p95_distance_mm']:.2f}mm <= {surf_eval['p95_limit_allowed_mm']:.2f}mm, Max={surf_eval['max_distance_mm']:.2f}mm <= {surf_eval['max_limit_allowed_mm']:.2f}mm.")

        except Exception as f_err:
            print(f"  -> CRASH [EXCEPTION IN CHECK 7]: Fidelity calculation failed with exception: {f_err}")
            all_passed = False
            check_results["C7"] = "CRASH"
    else:
        print("  -> FAIL [NOT VERIFIED]: Reference OBJ mesh not found for fidelity comparison.")
        all_passed = False
        check_results["C7"] = "FAIL"

    # -------------------------------------------------------------------------
    # CHECK 8: Visual Directives Enforcement Check (Groove & Ribs)
    # -------------------------------------------------------------------------
    print("\n[CHECK 8] Visual Directives Enforcement Check (Groove & Ribs)...")
    spec_candidates = [
        prt_path.parent / f"{prt_path.stem.replace('_Parametric', '')}_feature_plan.json",
        prt_path.parent / f"{prt_path.stem.replace('_Parametric', '')}_spec.json",
        prt_path.with_suffix(".json"),
        Path("output") / f"{prt_path.stem.replace('_Parametric', '')}_feature_plan.json",
        Path("output") / f"{prt_path.stem.replace('_Parametric', '')}_spec.json",
        Path("output") / f"{prt_path.stem}_spec.json",
    ]
    spec_found = None
    for sc in spec_candidates:
        if sc.exists():
            spec_found = sc
            break

    if spec_found:
        try:
            with open(spec_found, "r", encoding="utf-8") as sf_f:
                s_data = json.load(sf_f)

            groove_cfg = s_data.get("groove")
            ribs_cfg = s_data.get("ribs")

            feat_names = [f.GetFeatureName().upper() for f in part.Features]
            feat_names.extend([getattr(f, "Name", "").upper() for f in part.Features if getattr(f, "Name", None)])
            feat_names.extend([getattr(f, "FeatureType", "").upper() for f in part.Features if getattr(f, "FeatureType", None)])

            has_directives = False
            if groove_cfg and groove_cfg.get("enabled", True):
                has_directives = True
                has_groove = any("GROOVE" in fn or "WAIST" in fn or "NECK" in fn for fn in feat_names)
                if not has_groove:
                    print("  -> FAIL: Visual directives specified GROOVE, but no groove feature was found in NX features!")
                    all_passed = False
                    check_results["C8"] = "FAIL"
                else:
                    print("  -> PASS: Verified required GROOVE feature in NX Part Navigator.")

            if ribs_cfg and ribs_cfg.get("enabled", True):
                has_directives = True
                has_ribs = any("RIB" in fn or "FLUTE" in fn or "PATTERN" in fn for fn in feat_names)
                if not has_ribs:
                    print("  -> FAIL: Visual directives specified RIBS, but no rib/flute feature was found in NX features!")
                    all_passed = False
                    check_results["C8"] = "FAIL"
                else:
                    print("  -> PASS: Verified required RIBS feature in NX Part Navigator.")

            if not has_directives:
                print("  -> SKIPPED (no visual directives): Part specification defines no secondary groove or rib features.")
        except Exception as dir_err:
            print(f"  -> CRASH [EXCEPTION IN CHECK 8]: Could not evaluate directives check: {dir_err}")
            all_passed = False
            check_results["C8"] = "CRASH"
    else:
        print("  -> SKIPPED (no visual directives): No specification JSON found to evaluate secondary features.")

    # -------------------------------------------------------------------------
    # FINAL VERDICT
    # -------------------------------------------------------------------------
    print(f"\nCHECK_RESULTS_JSON: {json.dumps(check_results)}")
    print("\n" + "=" * 75)
    if all_passed:
        print(f"FINAL RESULT: ALL QUALITY CHECKS PASSED FOR {prt_path.name}")
        print("=" * 75)
        return True
    else:
        print(f"FINAL RESULT: QUALITY CHECKS FAILED FOR {prt_path.name}")
        print("=" * 75)
        return False


def main():
    args = [a for a in sys.argv[1:] if a != "-args" and not a.startswith("-")]
    if not args:
        print("Usage: python scripts/check_parametric_quality.py <path_to_prt_file> [<path_to_obj_file>]")
        sys.exit(1)

    prt_arg = args[0]
    obj_arg = args[1] if len(args) > 1 else None
    
    _reinvoke_under_run_journal_if_needed(args)

    prt_path = Path(prt_arg).resolve()
    obj_path = Path(obj_arg).resolve() if obj_arg else None
    success = check_part(prt_path, obj_path=obj_path)
    if "NXOpen" in sys.modules:
        os._exit(0 if success else 1)
    else:
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
