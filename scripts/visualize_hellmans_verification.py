"""
visualize_hellmans_verification.py
==================================
CAD geometric validation and multi-panel visual inspection comparing
the authoritative reference OBJ mesh (obj/Hellmans_reduced.obj) against the
reconstructed parametric Siemens NX part (Hellmans_reduced_Parametric.stl).
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import cKDTree
import trimesh


def main():
    repo_root = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
    obj_path = repo_root / "obj" / "Hellmans_reduced.obj"
    stl_path = repo_root / "Hellmans_reduced_Parametric.stl"
    out_png = repo_root / "Hellmans_reduced_verification.png"

    print("=" * 75)
    print("GEOMETRIC VERIFICATION: OBJ REFERENCE vs NX PARAMETRIC PART")
    print(f"  OBJ Reference: {obj_path}")
    print(f"  NX Output STL: {stl_path}")
    print(f"  Plot Output:   {out_png}")
    print("=" * 75)

    if not stl_path.exists():
        print(f"Error: {stl_path} does not exist!")
        return

    # 1. Load meshes
    mesh_raw = trimesh.load(str(obj_path), process=False)
    if isinstance(mesh_raw, trimesh.Scene):
        mesh_raw = trimesh.util.concatenate(mesh_raw.dump())
    if (mesh_raw.bounds[1][1] - mesh_raw.bounds[0][1]) < 10.0:
        mesh_raw.apply_scale(100.0)

    comps = mesh_raw.split(only_watertight=False)
    src_mesh = max(comps, key=lambda c: len(c.faces))

    # Center source mesh on X and Z
    cx = float(np.mean(src_mesh.vertices[:, 0]))
    cz = float(np.mean(src_mesh.vertices[:, 2]))
    src_mesh.vertices[:, 0] -= cx
    src_mesh.vertices[:, 2] -= cz

    rec_mesh = trimesh.load(str(stl_path), process=False)
    if isinstance(rec_mesh, trimesh.Scene):
        rec_mesh = trimesh.util.concatenate(rec_mesh.dump())

    # 2. Bounding Box & Dimensions
    print("\n[1/3] Bounding Box & Key Dimensions:")
    src_bb = src_mesh.bounds
    rec_bb = rec_mesh.bounds
    src_ext = src_mesh.extents
    rec_ext = rec_mesh.extents

    print(f"  Source OBJ Bounding Box: X=[{src_bb[0][0]:.3f}, {src_bb[1][0]:.3f}], Y=[{src_bb[0][1]:.3f}, {src_bb[1][1]:.3f}], Z=[{src_bb[0][2]:.3f}, {src_bb[1][2]:.3f}]")
    print(f"  NX Part Bounding Box:    X=[{rec_bb[0][0]:.3f}, {rec_bb[1][0]:.3f}], Y=[{rec_bb[0][1]:.3f}, {rec_bb[1][1]:.3f}], Z=[{rec_bb[0][2]:.3f}, {rec_bb[1][2]:.3f}]")
    print(f"  Source Length (Height):  {src_ext[1]:.3f} mm")
    print(f"  NX Part Length (Height): {rec_ext[1]:.3f} mm")
    diff_h = abs(rec_ext[1] - src_ext[1])
    pct_h = (diff_h / src_ext[1]) * 100.0
    print(f"  Height Difference:       {diff_h:.3f} mm ({pct_h:.2f}%)")

    # 3. Dense Surface Accuracy Analysis
    print("\n[2/3] Computing Surface Point-to-Mesh Deviation (cKDTree)...")
    samples_src, _ = trimesh.sample.sample_surface(src_mesh, 50000)
    samples_rec, _ = trimesh.sample.sample_surface(rec_mesh, 60000)

    tree = cKDTree(samples_rec)
    dists, _ = tree.query(samples_src)

    mean_err = float(np.mean(dists))
    median_err = float(np.median(dists))
    p90_err = float(np.percentile(dists, 90))
    p95_err = float(np.percentile(dists, 95))
    max_err = float(np.max(dists))
    rms_err = float(np.sqrt(np.mean(dists**2)))

    print(f"  Mean Deviation:    {mean_err:.4f} mm")
    print(f"  Median Deviation:  {median_err:.4f} mm")
    print(f"  RMS Deviation:     {rms_err:.4f} mm")
    print(f"  90th Percentile:   {p90_err:.4f} mm")
    print(f"  95th Percentile:   {p95_err:.4f} mm")
    print(f"  Max Deviation:     {max_err:.4f} mm")

    regions = [
        ("Base & Lower Chime", -100.5, -63.5),
        ("Main Cylindrical Body", -63.5, 30.0),
        ("Upper Ring & Shoulder", 30.0, 75.5),
        ("Ribbed Cap & Crown Dome", 75.5, 100.5),
    ]

    print("\n  Regional Deviation Breakdown:")
    for reg_name, y0, y1 in regions:
        m = (samples_src[:, 1] >= y0) & (samples_src[:, 1] < y1)
        if np.any(m):
            sub_d = dists[m]
            print(f"    - {reg_name:<26} Mean={np.mean(sub_d):.3f} mm, P90={np.percentile(sub_d, 90):.3f} mm, Max={np.max(sub_d):.3f} mm")

    # 4. Multi-Panel Visual Verification Figure
    print("\n[3/3] Generating Multi-Panel Visual Inspection Figure...")
    fig = plt.figure(figsize=(18, 12))

    # Panel 1: Front Silhouette Comparison (X vs Y)
    ax1 = fig.add_subplot(2, 3, 1)
    ax1.set_title("Front Silhouette: OBJ (Blue) vs NX CAD (Red)", fontsize=11, fontweight="bold")
    ax1.scatter(samples_src[:, 0], samples_src[:, 1], s=0.3, c="dodgerblue", alpha=0.3, label="Reference OBJ")
    ax1.scatter(samples_rec[:, 0], samples_rec[:, 1], s=0.3, c="crimson", alpha=0.3, label="Parametric NX")
    ax1.set_xlabel("X (mm)")
    ax1.set_ylabel("Y (Height mm)")
    ax1.set_aspect("equal")
    ax1.legend(loc="upper right", markerscale=10)
    ax1.grid(True, linestyle="--", alpha=0.5)

    # Panel 2: Side Silhouette Comparison (Z vs Y)
    ax2 = fig.add_subplot(2, 3, 2)
    ax2.set_title("Side Silhouette: OBJ (Blue) vs NX CAD (Red)", fontsize=11, fontweight="bold")
    ax2.scatter(samples_src[:, 2], samples_src[:, 1], s=0.3, c="dodgerblue", alpha=0.3, label="Reference OBJ")
    ax2.scatter(samples_rec[:, 2], samples_rec[:, 1], s=0.3, c="crimson", alpha=0.3, label="Parametric NX")
    ax2.set_xlabel("Z (Depth mm)")
    ax2.set_ylabel("Y (Height mm)")
    ax2.set_aspect("equal")
    ax2.legend(loc="upper right", markerscale=10)
    ax2.grid(True, linestyle="--", alpha=0.5)

    # Panel 3: Surface Error Heatmap
    ax3 = fig.add_subplot(2, 3, 3)
    ax3.set_title(f"Surface Deviation Heatmap (Mean: {mean_err:.2f}mm)", fontsize=11, fontweight="bold")
    sc = ax3.scatter(samples_src[:, 0], samples_src[:, 1], c=dists, s=0.5, cmap="turbo", vmin=0.0, vmax=2.5)
    ax3.set_xlabel("X (mm)")
    ax3.set_ylabel("Y (Height mm)")
    ax3.set_aspect("equal")
    cbar = plt.colorbar(sc, ax=ax3)
    cbar.set_label("Deviation (mm)")
    ax3.grid(True, linestyle="--", alpha=0.5)

    # Panel 4: Cap Rib Cross-Section (Y = 88 mm)
    ax4 = fig.add_subplot(2, 3, 4)
    ax4.set_title("Cap Ribs Cross-Section (Y = 88.0 mm)", fontsize=11, fontweight="bold")
    sec_obj = src_mesh.section(plane_origin=[0, 88.0, 0], plane_normal=[0, 1, 0])
    sec_nx = rec_mesh.section(plane_origin=[0, 88.0, 0], plane_normal=[0, 1, 0])
    if sec_obj and len(sec_obj.discrete) > 0:
        lp_obj = max(sec_obj.discrete, key=len)
        ax4.plot(lp_obj[:, 0], lp_obj[:, 2], "b-", linewidth=1.2, label="OBJ Ribs")
    if sec_nx and len(sec_nx.discrete) > 0:
        lp_nx = max(sec_nx.discrete, key=len)
        ax4.plot(lp_nx[:, 0], lp_nx[:, 2], "r--", linewidth=1.2, label="NX CAD Ribs")
    ax4.set_xlabel("X (mm)")
    ax4.set_ylabel("Z (mm)")
    ax4.set_aspect("equal")
    ax4.legend(loc="upper right")
    ax4.grid(True, linestyle="--", alpha=0.5)

    # Panel 5: Body Mid-Section (Y = 0.0 mm)
    ax5 = fig.add_subplot(2, 3, 5)
    ax5.set_title("Main Body Cross-Section (Y = 0.0 mm)", fontsize=11, fontweight="bold")
    sec_b_obj = src_mesh.section(plane_origin=[0, 0.0, 0], plane_normal=[0, 1, 0])
    sec_b_nx = rec_mesh.section(plane_origin=[0, 0.0, 0], plane_normal=[0, 1, 0])
    if sec_b_obj and len(sec_b_obj.discrete) > 0:
        lp_b_obj = max(sec_b_obj.discrete, key=len)
        ax5.plot(lp_b_obj[:, 0], lp_b_obj[:, 2], "b-", linewidth=1.5, label="OBJ Body")
    if sec_b_nx and len(sec_b_nx.discrete) > 0:
        lp_b_nx = max(sec_b_nx.discrete, key=len)
        ax5.plot(lp_b_nx[:, 0], lp_b_nx[:, 2], "r--", linewidth=1.5, label="NX Body")
    ax5.set_xlabel("X (mm)")
    ax5.set_ylabel("Z (mm)")
    ax5.set_aspect("equal")
    ax5.legend(loc="upper right")
    ax5.grid(True, linestyle="--", alpha=0.5)

    # Panel 6: Base Chime Cross-Section (Y = -95.0 mm)
    ax6 = fig.add_subplot(2, 3, 6)
    ax6.set_title("Base Chime Cross-Section (Y = -95.0 mm)", fontsize=11, fontweight="bold")
    sec_c_obj = src_mesh.section(plane_origin=[0, -95.0, 0], plane_normal=[0, 1, 0])
    sec_c_nx = rec_mesh.section(plane_origin=[0, -95.0, 0], plane_normal=[0, 1, 0])
    if sec_c_obj and len(sec_c_obj.discrete) > 0:
        lp_c_obj = max(sec_c_obj.discrete, key=len)
        ax6.plot(lp_c_obj[:, 0], lp_c_obj[:, 2], "b-", linewidth=1.5, label="OBJ Base")
    if sec_c_nx and len(sec_c_nx.discrete) > 0:
        lp_c_nx = max(sec_c_nx.discrete, key=len)
        ax6.plot(lp_c_nx[:, 0], lp_c_nx[:, 2], "r--", linewidth=1.5, label="NX Base")
    ax6.set_xlabel("X (mm)")
    ax6.set_ylabel("Z (mm)")
    ax6.set_aspect("equal")
    ax6.legend(loc="upper right")
    ax6.grid(True, linestyle="--", alpha=0.5)

    plt.tight_layout()
    plt.savefig(str(out_png), dpi=150)
    plt.close()
    print(f"  [OK] Verification plot saved: {out_png}")


if __name__ == "__main__":
    main()
