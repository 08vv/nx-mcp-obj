"""
visualize_toddler_toothbrush_verification.py
=============================================
Comprehensive CAD geometric validation and multi-panel visual inspection
comparing the reference OBJ mesh (obj/Todddler_toothbrush.obj) against the
reconstructed parametric Siemens NX part (Toddler_Toothbrush_Strict_Fidelity.stl).
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
    obj_path = repo_root / "obj" / "Todddler_toothbrush.obj"
    stl_path = repo_root / "Toddler_Toothbrush_Strict_Fidelity.stl"
    out_png = repo_root / "Toddler_Toothbrush_Strict_Fidelity_verification.png"

    print("=" * 75)
    print("GEOMETRIC VERIFICATION: OBJ REFERENCE vs NX PARAMETRIC PART")
    print(f"  OBJ Reference: {obj_path}")
    print(f"  NX Output STL: {stl_path}")
    print(f"  Plot Output:   {out_png}")
    print("=" * 75)

    # 1. Load meshes
    mesh_raw = trimesh.load(str(obj_path), process=False)
    if isinstance(mesh_raw, trimesh.Scene):
        mesh_raw = trimesh.util.concatenate(mesh_raw.dump())
    if (mesh_raw.bounds[1][1] - mesh_raw.bounds[0][1]) < 10.0:
        mesh_raw.apply_scale(100.0)

    comps = mesh_raw.split(only_watertight=False)
    src_mesh = max(comps, key=lambda c: len(c.faces))

    # Center source mesh on X and Z
    cx = float((src_mesh.bounds[0][0] + src_mesh.bounds[1][0]) / 2.0)
    cz = float((src_mesh.bounds[0][2] + src_mesh.bounds[1][2]) / 2.0)
    src_mesh.vertices[:, 0] -= cx
    src_mesh.vertices[:, 2] -= cz

    rec_mesh = trimesh.load(str(stl_path), process=False)
    if isinstance(rec_mesh, trimesh.Scene):
        rec_mesh = trimesh.util.concatenate(rec_mesh.dump())

    # 2. Dimensions & Bounding Boxes
    src_bb = src_mesh.bounds
    rec_bb = rec_mesh.bounds
    src_ext = src_mesh.extents
    rec_ext = rec_mesh.extents

    print(f"  Source Extents: X={src_ext[0]:.2f}, Y={src_ext[1]:.2f}, Z={src_ext[2]:.2f} mm")
    print(f"  CAD Extents:    X={rec_ext[0]:.2f}, Y={rec_ext[1]:.2f}, Z={rec_ext[2]:.2f} mm")
    delta_ext = np.abs(src_ext - rec_ext)
    print(f"  Delta Extents:  dX={delta_ext[0]:.2f}, dY={delta_ext[1]:.2f}, dZ={delta_ext[2]:.2f} mm")

    # 3. Distance Metrics via cKDTree
    print("\nComputing point-to-surface deviation metrics...")
    pts_rec, _ = trimesh.sample.sample_surface(rec_mesh, 25000)
    pts_src, _ = trimesh.sample.sample_surface(src_mesh, 25000)

    tree_src = cKDTree(pts_src)
    dists_rec_to_src, _ = tree_src.query(pts_rec, k=1)

    mean_err = np.mean(dists_rec_to_src)
    median_err = np.median(dists_rec_to_src)
    p95_err = np.percentile(dists_rec_to_src, 95)
    max_err = np.max(dists_rec_to_src)

    print(f"  Mean Absolute Deviation:   {mean_err:.3f} mm")
    print(f"  Median Deviation:          {median_err:.3f} mm")
    print(f"  95th Percentile Deviation: {p95_err:.3f} mm")
    print(f"  Max Deviation:             {max_err:.3f} mm")

    # 4. Multi-Panel Visualization Plot
    fig = plt.figure(figsize=(20, 12))

    # Panel 1: Front View Overlay (X-Y)
    ax1 = fig.add_subplot(1, 4, 1)
    ax1.scatter(pts_src[::5, 0], pts_src[::5, 1], s=0.8, c="royalblue", alpha=0.4, label="OBJ Reference")
    ax1.scatter(pts_rec[::5, 0], pts_rec[::5, 1], s=0.8, c="crimson", alpha=0.4, label="CAD Reconstruction")
    ax1.set_title("Front View (X-Y Overlay)", fontsize=13, fontweight="bold")
    ax1.set_xlabel("X (Width, mm)")
    ax1.set_ylabel("Y (Height, mm)")
    ax1.set_aspect("equal")
    ax1.legend(loc="upper left")
    ax1.grid(True, linestyle=":", alpha=0.5)

    # Panel 2: Side View Overlay (Z-Y)
    ax2 = fig.add_subplot(1, 4, 2)
    ax2.scatter(pts_src[::5, 2], pts_src[::5, 1], s=0.8, c="royalblue", alpha=0.4, label="OBJ Reference")
    ax2.scatter(pts_rec[::5, 2], pts_rec[::5, 1], s=0.8, c="crimson", alpha=0.4, label="CAD Reconstruction")
    ax2.set_title("Side View (Z-Y Overlay)", fontsize=13, fontweight="bold")
    ax2.set_xlabel("Z (Depth, mm)")
    ax2.set_ylabel("Y (Height, mm)")
    ax2.set_aspect("equal")
    ax2.legend(loc="upper left")
    ax2.grid(True, linestyle=":", alpha=0.5)

    # Panel 3: Collar & Head Detail (X-Z)
    ax3 = fig.add_subplot(1, 4, 3)
    c_mask_src = pts_src[:, 1] > 10.0
    c_mask_rec = pts_rec[:, 1] > 10.0
    ax3.scatter(pts_src[c_mask_src][::2, 0], pts_src[c_mask_src][::2, 2], s=1.0, c="royalblue", alpha=0.5, label="OBJ Collar & Head")
    ax3.scatter(pts_rec[c_mask_rec][::2, 0], pts_rec[c_mask_rec][::2, 2], s=1.0, c="crimson", alpha=0.5, label="CAD Collar & Head")
    ax3.set_title("Collar & Head (X-Z Overlay)", fontsize=13, fontweight="bold")
    ax3.set_xlabel("X (Width, mm)")
    ax3.set_ylabel("Z (Depth, mm)")
    ax3.set_aspect("equal")
    ax3.legend(loc="upper right")
    ax3.grid(True, linestyle=":", alpha=0.5)

    # Panel 4: Deviation Heatmap
    ax4 = fig.add_subplot(1, 4, 4)
    vmax_val = max(1.5, p95_err * 1.5)
    sc = ax4.scatter(pts_rec[::2, 0], pts_rec[::2, 1], s=1.5, c=dists_rec_to_src[::2], cmap="turbo", vmin=0.0, vmax=vmax_val)
    ax4.set_title(f"Surface Deviation Heatmap\n(Mean: {mean_err:.2f}mm, P95: {p95_err:.2f}mm)", fontsize=13, fontweight="bold")
    ax4.set_xlabel("X (Width, mm)")
    ax4.set_ylabel("Y (Height, mm)")
    ax4.set_aspect("equal")
    cbar = plt.colorbar(sc, ax=ax4, orientation="vertical", shrink=0.7)
    cbar.set_label("Deviation from Reference OBJ (mm)")
    ax4.grid(True, linestyle=":", alpha=0.5)

    plt.suptitle("Toddler Toothbrush — CAD Reconstruction Strict Geometric Verification", fontsize=16, fontweight="bold", y=0.98)
    plt.tight_layout()
    plt.savefig(str(out_png), dpi=150, bbox_inches="tight")
    print(f"\n[OK] Verification plot saved to {out_png}")


if __name__ == "__main__":
    main()
