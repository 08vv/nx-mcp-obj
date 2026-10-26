"""
visualize_cif3_verification.py
==============================
Visual verification and surface deviation analysis comparing Cif3_jerry_can_reduced.obj
with the reconstructed parametric CAD STL (Cif3_Parametric.stl).
"""

from __future__ import annotations

import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import cKDTree
import trimesh


def main():
    repo_root = Path(__file__).resolve().parent.parent
    obj_path = repo_root / "obj" / "Cif3_jerry_can_reduced.obj"
    stl_path = repo_root / "Cif3_Parametric.stl"
    out_img = repo_root / "cif3_cad_verification.png"

    print(f"Loading reference mesh: {obj_path.name}")
    mesh_ref = trimesh.load(str(obj_path), process=False)
    mesh_ref.apply_scale(100.0)

    # Transform reference mesh to NX coordinate system:
    # OBJ: X = width, Y = height (-100 to +99.47), Z = depth (-27 to +27)
    # NX:  X = width, Y = depth (-27 to +27), Z = height (0 to 199.47)
    v_ref = np.zeros_like(mesh_ref.vertices)
    v_ref[:, 0] = mesh_ref.vertices[:, 0]
    v_ref[:, 1] = mesh_ref.vertices[:, 2]
    v_ref[:, 2] = mesh_ref.vertices[:, 1] + 100.0
    mesh_ref.vertices = v_ref

    print(f"Loading CAD STL: {stl_path.name}")
    mesh_cad = trimesh.load(str(stl_path), process=False)

    print("Reference Bounds:", mesh_ref.bounds)
    print("CAD STL Bounds:  ", mesh_cad.bounds)

    # Sample points for surface deviation
    n_pts = 40000
    pts_ref, _ = trimesh.sample.sample_surface(mesh_ref, n_pts)
    pts_cad, _ = trimesh.sample.sample_surface(mesh_cad, n_pts)

    tree_cad = cKDTree(pts_cad)
    dists, _ = tree_cad.query(pts_ref)

    mean_dev = np.mean(dists)
    median_dev = np.median(dists)
    p95_dev = np.percentile(dists, 95)
    max_dev = np.max(dists)

    print(f"Surface Deviation Stats:")
    print(f"  Mean Deviation:   {mean_dev:.3f} mm")
    print(f"  Median Deviation: {median_dev:.3f} mm")
    print(f"  95th Percentile:  {p95_dev:.3f} mm")
    print(f"  Max Deviation:    {max_dev:.3f} mm")

    # Generate multi-view comparison figure
    fig = plt.figure(figsize=(18, 12), constrained_layout=True)
    gs = fig.add_gridspec(2, 3)

    # 1. Front View (X-Z)
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.scatter(mesh_ref.vertices[::2, 0], mesh_ref.vertices[::2, 2], s=0.2, c="silver", label="Reference OBJ")
    ax1.scatter(mesh_cad.vertices[::2, 0], mesh_cad.vertices[::2, 2], s=0.2, c="crimson", alpha=0.5, label="Parametric NX CAD")
    ax1.set_title("Front View (X-Z Silhouette)", fontsize=13, fontweight="bold")
    ax1.set_xlabel("X (Width, mm)")
    ax1.set_ylabel("Z (Height, mm)")
    ax1.axis("equal")
    ax1.legend(loc="upper right", markerscale=10)
    ax1.grid(True, alpha=0.3)

    # 2. Side View (Y-Z)
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.scatter(mesh_ref.vertices[::2, 1], mesh_ref.vertices[::2, 2], s=0.2, c="silver", label="Reference OBJ")
    ax2.scatter(mesh_cad.vertices[::2, 1], mesh_cad.vertices[::2, 2], s=0.2, c="royalblue", alpha=0.5, label="Parametric NX CAD")
    ax2.set_title("Side View (Y-Z Silhouette)", fontsize=13, fontweight="bold")
    ax2.set_xlabel("Y (Depth, mm)")
    ax2.set_ylabel("Z (Height, mm)")
    ax2.axis("equal")
    ax2.legend(loc="upper right", markerscale=10)
    ax2.grid(True, alpha=0.3)

    # 3. Top View (X-Y)
    ax3 = fig.add_subplot(gs[0, 2])
    ax3.scatter(mesh_ref.vertices[::2, 0], mesh_ref.vertices[::2, 1], s=0.2, c="silver", label="Reference OBJ")
    ax3.scatter(mesh_cad.vertices[::2, 0], mesh_cad.vertices[::2, 1], s=0.2, c="forestgreen", alpha=0.5, label="Parametric NX CAD")
    ax3.set_title("Top View (X-Y Section)", fontsize=13, fontweight="bold")
    ax3.set_xlabel("X (Width, mm)")
    ax3.set_ylabel("Y (Depth, mm)")
    ax3.axis("equal")
    ax3.legend(loc="upper right", markerscale=10)
    ax3.grid(True, alpha=0.3)

    # 4. Handle & Neck Detail View
    ax4 = fig.add_subplot(gs[1, 0])
    mask_ref = mesh_ref.vertices[:, 2] > 150.0
    mask_cad = mesh_cad.vertices[:, 2] > 150.0
    ax4.scatter(mesh_ref.vertices[mask_ref, 0], mesh_ref.vertices[mask_ref, 2], s=0.4, c="silver", label="Reference OBJ")
    ax4.scatter(mesh_cad.vertices[mask_cad, 0], mesh_cad.vertices[mask_cad, 2], s=0.4, c="crimson", alpha=0.6, label="CAD Handle & Neck")
    ax4.set_title("Upper Shoulder, Handle & Offset Neck Detail", fontsize=13, fontweight="bold")
    ax4.set_xlabel("X (Width, mm)")
    ax4.set_ylabel("Z (Height, mm)")
    ax4.axis("equal")
    ax4.legend(loc="lower right", markerscale=8)
    ax4.grid(True, alpha=0.3)

    # 5. Surface Deviation Heatmap (Front)
    ax5 = fig.add_subplot(gs[1, 1])
    sc = ax5.scatter(pts_ref[:, 0], pts_ref[:, 2], c=dists, s=0.8, cmap="turbo", vmin=0.0, vmax=2.5)
    ax5.set_title("Surface Deviation Heatmap (Front, 0-2.5 mm)", fontsize=13, fontweight="bold")
    ax5.set_xlabel("X (Width, mm)")
    ax5.set_ylabel("Z (Height, mm)")
    ax5.axis("equal")
    cbar = fig.colorbar(sc, ax=ax5, fraction=0.046, pad=0.04)
    cbar.set_label("Deviation (mm)")
    ax5.grid(True, alpha=0.3)

    # 6. Surface Deviation Histogram
    ax6 = fig.add_subplot(gs[1, 2])
    ax6.hist(dists, bins=50, color="teal", edgecolor="black", alpha=0.7)
    ax6.axvline(mean_dev, color="red", linestyle="--", linewidth=2, label=f"Mean: {mean_dev:.2f} mm")
    ax6.axvline(median_dev, color="orange", linestyle="--", linewidth=2, label=f"Median: {median_dev:.2f} mm")
    ax6.axvline(p95_dev, color="purple", linestyle="--", linewidth=2, label=f"95th %ile: {p95_dev:.2f} mm")
    ax6.set_title("Surface Deviation Error Distribution", fontsize=13, fontweight="bold")
    ax6.set_xlabel("Deviation (mm)")
    ax6.set_ylabel("Sample Point Count")
    ax6.legend(loc="upper right")
    ax6.grid(True, alpha=0.3)

    plt.suptitle("Cif3 Jerry Can Container: Parametric NX CAD Reconstruction Verification", fontsize=16, fontweight="bold")
    fig.savefig(str(out_img), dpi=200)
    plt.close(fig)
    print(f"[OK] Verification graphic saved: {out_img}")


if __name__ == "__main__":
    main()
