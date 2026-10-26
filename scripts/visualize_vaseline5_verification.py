"""
visualize_vaseline5_verification.py
===================================
Comprehensive CAD geometric validation and multi-panel visual inspection
comparing the reference OBJ mesh (obj/Vaseline5_reduced.obj) against the
reconstructed parametric Siemens NX part (Vaseline5_Parametric_Strict.stl).
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
    obj_path = repo_root / "obj" / "Vaseline5_reduced.obj"
    stl_path = repo_root / "Vaseline5_Parametric_Strict.stl"
    out_png = repo_root / "Vaseline5_Parametric_Strict_verification.png"

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
    pts_rec, _ = trimesh.sample.sample_surface(rec_mesh, 30000)
    pts_src, _ = trimesh.sample.sample_surface(src_mesh, 30000)

    tree_src = cKDTree(pts_src)
    dists_rec_to_src, _ = tree_src.query(pts_rec, k=1)

    mean_err = np.mean(dists_rec_to_src)
    median_err = np.median(dists_rec_to_src)
    p90_err = np.percentile(dists_rec_to_src, 90)
    p95_err = np.percentile(dists_rec_to_src, 95)
    max_err = np.max(dists_rec_to_src)

    print(f"  Mean Absolute Deviation:   {mean_err:.3f} mm")
    print(f"  Median Deviation:          {median_err:.3f} mm")
    print(f"  90th Percentile Deviation: {p90_err:.3f} mm")
    print(f"  95th Percentile Deviation: {p95_err:.3f} mm")
    print(f"  Max Deviation:             {max_err:.3f} mm")

    # 4. Multi-Panel Visualization Plot
    fig = plt.figure(figsize=(22, 12))

    # Panel 1: Front View Overlay (X-Y)
    ax1 = fig.add_subplot(1, 4, 1)
    ax1.scatter(pts_src[::4, 0], pts_src[::4, 1], s=0.8, c="royalblue", alpha=0.35, label="OBJ Reference")
    ax1.scatter(pts_rec[::4, 0], pts_rec[::4, 1], s=0.8, c="crimson", alpha=0.35, label="CAD Reconstruction")
    ax1.set_title("Front Silhouette (X-Y)", fontsize=13, fontweight="bold")
    ax1.set_xlabel("X (Width, mm)")
    ax1.set_ylabel("Y (Height, mm)")
    ax1.set_aspect("equal")
    ax1.legend(loc="upper left")
    ax1.grid(True, linestyle=":", alpha=0.5)

    # Panel 2: Side View Overlay (Z-Y)
    ax2 = fig.add_subplot(1, 4, 2)
    ax2.scatter(pts_src[::4, 2], pts_src[::4, 1], s=0.8, c="royalblue", alpha=0.35, label="OBJ Reference")
    ax2.scatter(pts_rec[::4, 2], pts_rec[::4, 1], s=0.8, c="crimson", alpha=0.35, label="CAD Reconstruction")
    ax2.set_title("Side Profile (Z-Y Taper)", fontsize=13, fontweight="bold")
    ax2.set_xlabel("Z (Depth, mm)")
    ax2.set_ylabel("Y (Height, mm)")
    ax2.set_aspect("equal")
    ax2.legend(loc="upper left")
    ax2.grid(True, linestyle=":", alpha=0.5)

    # Panel 3: Deviation Heatmap
    ax3 = fig.add_subplot(1, 4, 3)
    clip_err = np.clip(dists_rec_to_src, 0.0, 1.5)
    sc = ax3.scatter(pts_rec[::3, 0], pts_rec[::3, 1], c=clip_err[::3], cmap="turbo", s=1.2, alpha=0.7)
    cbar = plt.colorbar(sc, ax=ax3, fraction=0.046, pad=0.04)
    cbar.set_label("Deviation to Reference OBJ (mm)", fontsize=10)
    ax3.set_title(f"CAD Deviation Map\nMean={mean_err:.3f} mm, P95={p95_err:.3f} mm", fontsize=13, fontweight="bold")
    ax3.set_xlabel("X (Width, mm)")
    ax3.set_ylabel("Y (Height, mm)")
    ax3.set_aspect("equal")
    ax3.grid(True, linestyle=":", alpha=0.5)

    # Panel 4: Cross-Section Comparison at Key Elevations
    ax4 = fig.add_subplot(1, 4, 4)
    elevations = [-85.0, -70.0, 0.0, 60.0, 85.0, 95.0]
    colors = plt.cm.plasma(np.linspace(0.1, 0.9, len(elevations)))
    for elev, col in zip(elevations, colors):
        sec_src = src_mesh.section(plane_origin=[0, elev, 0], plane_normal=[0, 1, 0])
        sec_rec = rec_mesh.section(plane_origin=[0, elev, 0], plane_normal=[0, 1, 0])
        if sec_src and sec_rec:
            p_src = sec_src.vertices
            p_rec = sec_rec.vertices
            ax4.scatter(p_src[:, 0], p_src[:, 2], s=1.5, color=col, alpha=0.6, label=f"Y={elev:.0f} OBJ")
            ax4.plot(p_rec[:, 0], p_rec[:, 2], color="black", linewidth=0.8, alpha=0.8)

    ax4.set_title("Cross-Sections (X-Z)\nBlack lines: CAD, Dots: OBJ", fontsize=13, fontweight="bold")
    ax4.set_xlabel("X (Width, mm)")
    ax4.set_ylabel("Z (Depth, mm)")
    ax4.set_aspect("equal")
    ax4.legend(loc="upper right", fontsize=8)
    ax4.grid(True, linestyle=":", alpha=0.5)

    plt.suptitle(
        f"Vaseline 5 Squeeze Tube: Siemens NX Parametric CAD vs OBJ Reference\n"
        f"Strict Geometry Match: Height={rec_ext[1]:.2f} mm | Width={rec_ext[0]:.2f} mm | Depth={rec_ext[2]:.2f} mm | Mean Dev={mean_err:.3f} mm",
        fontsize=15,
        fontweight="bold",
        y=0.98,
    )

    plt.tight_layout()
    fig.savefig(str(out_png), dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"\n[OK] Verification plot saved: {out_png} ({out_png.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
