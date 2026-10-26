import json
import sys
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import trimesh

repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from src.nx_mcp.mesh_analyzer.revolve_profile_analyzer import RevolveProfileAnalyzer

out_dir = repo_root / "output" / "profile_overlays"
out_dir.mkdir(parents=True, exist_ok=True)

targets = [
    ("Hellmans_reduced", repo_root / "obj" / "Hellmans_reduced.obj", repo_root / "output" / "Hellmans_reduced_spec.json"),
    ("makeup_cosmetic_star2", repo_root / "obj" / "makeup_cosmetic_star2.obj", repo_root / "output" / "makeup_cosmetic_star2_spec.json"),
    ("Oziva4_reduced", repo_root / "obj" / "Oziva4_reduced.obj", repo_root / "output" / "Oziva4_reduced_spec.json"),
]

for name, obj_p, spec_p in targets:
    print(f"Generating profile overlay for {name}...")
    mesh = trimesh.load(str(obj_p), force="mesh")
    if max(mesh.extents) < 15.0:
        mesh.apply_scale(100.0)

    # 1. Analyzer circularity profile (100 stations along Y)
    analyzer = RevolveProfileAnalyzer(str(obj_p))
    profile = analyzer.compute_circularity_profile(n_slices=100)
    raw_zones = analyzer.segment_zones(profile, max_zones=8)
    zones, refine_status = analyzer.refine_zones(profile, raw_zones)

    stations = profile["stations"]
    y_valid = np.array([s["z"] for s in stations])
    r_mesh = np.array([s["radius"] for s in stations])

    r_plan = np.zeros_like(y_valid)
    for i, y in enumerate(y_valid):
        val = r_mesh[i] # fallback
        for z in zones:
            z_st = z.get("z_start", z.get("start_elevation_mm", z.get("start_y", 0.0)))
            z_en = z.get("z_end", z_st + z.get("height", z.get("height_mm", 0.0)))
            z_h = max(z_en - z_st, 1e-4)
            if z_st - 0.2 <= y <= z_en + 0.2:
                r_b = z.get("r_start", z.get("base_radius_mm", z.get("radius_mm", 0.0)))
                r_t = z.get("r_end", z.get("top_radius_mm", z.get("radius_mm", r_b)))
                seg_type = z.get("segment_type", "LINE")
                frac = (y - z_st) / z_h
                frac = float(np.clip(frac, 0.0, 1.0))
                if seg_type == "ARC":
                    r_m = z.get("r_mid", (r_b + r_t) / 2.0)
                    val = (1.0 - frac)**2 * r_b + 2.0 * frac * (1.0 - frac) * r_m + frac**2 * r_t
                else:
                    val = r_b + frac * (r_t - r_b)
                break
        r_plan[i] = val

    err = np.abs(r_mesh - r_plan)
    err_pct = (err / np.maximum(r_mesh, 1e-4)) * 100.0

    fail_mask_5 = (err_pct > 5.0) & (err_pct <= 10.0)
    fail_mask_10 = err_pct > 10.0

    # Create 2-panel plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True, gridspec_kw={"height_ratios": [2, 1]})

    ax1.plot(y_valid, r_mesh, "b-", linewidth=2.0, label="Mesh Profile $R_{\\mathrm{mesh}}(Y)$")
    ax1.plot(y_valid, r_plan, "r--", linewidth=2.0, label="Planned Profile $R_{\\mathrm{plan}}(Y)$")
    if np.any(fail_mask_5):
        ax1.scatter(y_valid[fail_mask_5], r_mesh[fail_mask_5], color="orange", s=35, zorder=5, label=f"Near-miss (5-10%): {np.sum(fail_mask_5)} stations")
    if np.any(fail_mask_10):
        ax1.scatter(y_valid[fail_mask_10], r_mesh[fail_mask_10], color="red", s=50, marker="x", zorder=6, label=f"Far-miss (>10%): {np.sum(fail_mask_10)} stations")

    # Draw zone boundaries
    for z in zones:
        z_st = z.get("z_start", z.get("start_elevation_mm", z.get("start_y", 0.0)))
        z_en = z.get("z_end", z_st + z.get("height", z.get("height_mm", 0.0)))
        ax1.axvline(z_st, color="gray", linestyle=":", alpha=0.6)
        ax1.axvline(z_en, color="gray", linestyle=":", alpha=0.6)

    ax1.set_ylabel("Radius (mm)", fontsize=11)
    ax1.set_title(f"Profile Overlay: {name} (Mesh vs CAD Plan)", fontsize=13, fontweight="bold")
    ax1.legend(loc="best", fontsize=9)
    ax1.grid(True, linestyle="--", alpha=0.5)

    ax2.plot(y_valid, err, "k-", linewidth=1.5, label="Absolute Radius Deviation $\\Delta R$ (mm)")
    ax2.plot(y_valid, err_pct, "m-.", linewidth=1.2, label="Relative Error %")
    ax2.axhline(5.0, color="orange", linestyle=":", alpha=0.8, label="Refinement Tol (5%)")
    ax2.axhline(10.0, color="red", linestyle="--", alpha=0.8, label="Check 7 Limit (10%)")
    if np.any(fail_mask_5):
        ax2.scatter(y_valid[fail_mask_5], err_pct[fail_mask_5], color="orange", s=35, zorder=5)
    if np.any(fail_mask_10):
        ax2.scatter(y_valid[fail_mask_10], err_pct[fail_mask_10], color="red", s=50, marker="x", zorder=6)

    ax2.set_xlabel("Elevation $Y$ along Axis (mm)", fontsize=11)
    ax2.set_ylabel("Deviation (mm / %)", fontsize=11)
    ax2.legend(loc="upper right", fontsize=9)
    ax2.grid(True, linestyle="--", alpha=0.5)

    plot_path = out_dir / f"{name}_profile_overlay.png"
    plt.tight_layout()
    plt.savefig(str(plot_path), dpi=150)
    plt.close()
    print(f"  Saved plot: {plot_path}")
    print(f"  Max radius error: {np.max(err):.3f} mm ({np.max(err_pct):.2f}%) at Y = {y_valid[np.argmax(err)]:.2f} mm")
    print(f"  Failing stations (>5%): {np.sum(err_pct > 5.0)} / {len(y_valid)}")
