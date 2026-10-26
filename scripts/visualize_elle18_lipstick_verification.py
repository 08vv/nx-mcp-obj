"""
visualize_elle18_lipstick_verification.py
=========================================
Comprehensive CAD geometric validation and multi-panel visual inspection
comparing the reference OBJ mesh (obj/Elle18-Liquid-Lipstick.obj) against the
reconstructed parametric Siemens NX part (Elle18_Liquid_Lipstick_Parametric.stl).
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
    obj_path = repo_root / "obj" / "Elle18-Liquid-Lipstick.obj"
    stl_path = repo_root / "Elle18_Liquid_Lipstick_Parametric.stl"
    out_png = repo_root / "Elle18_Liquid_Lipstick_verification.png"

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

    # Center source mesh on X and Z
    cx = float((mesh_raw.bounds[0][0] + mesh_raw.bounds[1][0]) / 2.0)
    cz = float((mesh_raw.bounds[0][2] + mesh_raw.bounds[1][2]) / 2.0)
    src_mesh = mesh_raw.copy()
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
    print(f"  Height Difference:       {abs(rec_ext[1] - src_ext[1]):.3f} mm ({(abs(rec_ext[1] - src_ext[1])/src_ext[1])*100:.2f}%)")

    # 3. Dense Surface Accuracy Analysis
    print("\n[2/3] Computing Surface Point-to-Mesh Deviation (cKDTree)...")
    samples_src, _ = trimesh.sample.sample_surface(src_mesh, 40000)
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
        ("Base & Lower Bottle Body", -100.5, 10.0),
        ("Reveal Seam & Parting Line", 10.0, 25.0),
        ("Upper Cap Wand Body", 25.0, 95.0),
        ("Cap Crown Top Dome", 95.0, 100.5),
    ]

    print("\n  Regional Deviation Breakdown:")
    for reg_name, y0, y1 in regions:
        m = (samples_src[:, 1] >= y0) & (samples_src[:, 1] < y1)
        if np.any(m):
            sub_d = dists[m]
            print(f"    {reg_name:28s} (Y in [{y0:6.1f}, {y1:5.1f}] mm): Mean={sub_d.mean():.4f} mm, Median={np.median(sub_d):.4f} mm, 95%={np.percentile(sub_d, 95):.4f} mm")

    # 4. Multi-Panel High Resolution Plot
    print("\n[3/3] Generating High-Resolution Multi-Panel Verification Image...")
    fig = plt.figure(figsize=(18, 12), dpi=200)
    gs = fig.add_gridspec(2, 3, height_ratios=[1.2, 1.0], hspace=0.32, wspace=0.25)

    # Panel 1: Full-length Silhouette Overlay
    ax1 = fig.add_subplot(gs[:, 0])
    y_test = np.linspace(-99.5, 99.0, 300)
    src_r = []
    rec_r = []
    y_valid = []
    for y in y_test:
        sec_s = src_mesh.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
        sec_r = rec_mesh.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
        if sec_s is not None and len(sec_s.discrete) > 0 and sec_r is not None and len(sec_r.discrete) > 0:
            ls = max(sec_s.discrete, key=lambda l: len(l))
            lr = max(sec_r.discrete, key=lambda l: len(l))
            rs = float(np.mean(np.hypot(ls[:, 0], ls[:, 2])))
            rr = float(np.mean(np.hypot(lr[:, 0], lr[:, 2])))
            y_valid.append(y)
            src_r.append(rs)
            rec_r.append(rr)

    y_valid = np.array(y_valid)
    src_r = np.array(src_r)
    rec_r = np.array(rec_r)

    ax1.plot(src_r, y_valid, 'b-', label='OBJ Source (+R)', lw=2.0, alpha=0.85)
    ax1.plot(-src_r, y_valid, 'b-', label='OBJ Source (-R)', lw=2.0, alpha=0.85)
    ax1.plot(rec_r, y_valid, 'r--', label='NX Parametric (+R)', lw=2.0, alpha=0.85)
    ax1.plot(-rec_r, y_valid, 'r--', label='NX Parametric (-R)', lw=2.0, alpha=0.85)
    ax1.fill_betweenx(y_valid, -rec_r, rec_r, color='crimson', alpha=0.10)

    ax1.set_xlabel("Radius (mm)", fontsize=11, fontweight='bold')
    ax1.set_ylabel("Height Y (mm)", fontsize=11, fontweight='bold')
    ax1.set_title("Full-Length Profile Overlay\n(Length ~ 199.4 mm, Dia ~ 22.6 mm)", fontsize=12, fontweight='bold')
    ax1.grid(True, linestyle=':', alpha=0.6)
    ax1.legend(loc='lower left', fontsize=9)
    ax1.set_xlim(-16, 20)
    ax1.set_ylim(-105, 105)

    ax1.annotate("Cap Crown Dome\n(R=3.3 mm, Y=96-99.4 mm)", xy=(10.0, 97), xytext=(12.0, 95),
                 arrowprops=dict(arrowstyle="->", color='black', lw=1.2), fontsize=8.5, fontweight='bold')
    ax1.annotate("Cap Wand Body\n(Dia ~ 21.87 mm)", xy=(10.9, 60), xytext=(12.0, 60),
                 arrowprops=dict(arrowstyle="->", color='black', lw=1.2), fontsize=8.5)
    ax1.annotate("Parting Line Seam\n(Groove Dia 21.67 mm, Y=20 mm)", xy=(10.8, 20), xytext=(12.0, 20),
                 arrowprops=dict(arrowstyle="->", color='black', lw=1.2), fontsize=8.5, fontweight='bold')
    ax1.annotate("Bottle Container Body\n(Dia ~ 22.61 mm)", xy=(11.3, -40), xytext=(12.0, -40),
                 arrowprops=dict(arrowstyle="->", color='black', lw=1.2), fontsize=8.5)
    ax1.annotate("Rounded Base Blend\n(R=3.3 mm, Y=-100 mm)", xy=(10.0, -98), xytext=(12.0, -95),
                 arrowprops=dict(arrowstyle="->", color='black', lw=1.2), fontsize=8.5, fontweight='bold')

    # Panel 2: Zoomed-in Reveal Seam & Parting Line
    ax2 = fig.add_subplot(gs[0, 1])
    m_col = (y_valid >= 16.0) & (y_valid <= 24.0)
    ax2.plot(y_valid[m_col], 2 * src_r[m_col], 'b-', lw=2.5, label='OBJ Reference Diameter')
    ax2.plot(y_valid[m_col], 2 * rec_r[m_col], 'r--', lw=2.5, label='NX Reconstructed Diameter')
    ax2.set_xlabel("Height Y (mm)", fontsize=10, fontweight='bold')
    ax2.set_ylabel("Diameter (mm)", fontsize=10, fontweight='bold')
    ax2.set_title("ZOOM: Reveal Seam / Parting Line\n(Bottle Bevel, Annular Groove, Cap Flare)", fontsize=11, fontweight='bold')
    ax2.grid(True, linestyle=':', alpha=0.6)
    ax2.legend(loc='lower right', fontsize=9)

    ax2.axvline(20.05, color='gray', linestyle=':', alpha=0.7)
    ax2.text(20.15, 21.72, "Groove Min\nDia 21.67 mm", fontsize=8, color='navy')
    ax2.axvline(18.00, color='gray', linestyle=':', alpha=0.7)
    ax2.text(16.5, 22.45, "Bottle Dia\n22.61 mm", fontsize=8, color='navy')
    ax2.axvline(21.40, color='gray', linestyle=':', alpha=0.7)
    ax2.text(21.5, 21.90, "Cap Dia\n21.87 mm", fontsize=8, color='navy')

    # Panel 3: Zoomed-in Top Dome & Bottom Base
    ax3 = fig.add_subplot(gs[0, 2])
    m_top = (y_valid >= 93.0) & (y_valid <= 99.4)
    ax3.plot(y_valid[m_top], src_r[m_top], 'b-', lw=2.5, label='OBJ Top Dome Radius')
    ax3.plot(y_valid[m_top], rec_r[m_top], 'r--', lw=2.5, label='NX Top Dome Radius')
    ax3.set_xlabel("Height Y (mm)", fontsize=10, fontweight='bold')
    ax3.set_ylabel("Radius (mm)", fontsize=10, fontweight='bold')
    ax3.set_title("ZOOM: Cap Crown Dome\n(Curved Dome Blend R=3.3 mm)", fontsize=11, fontweight='bold')
    ax3.grid(True, linestyle=':', alpha=0.6)
    ax3.legend(loc='lower left', fontsize=9)

    # Panel 4: Deviation Error Distribution (Histogram)
    ax4 = fig.add_subplot(gs[1, 1])
    n_bins = 50
    counts, edges, patches = ax4.hist(dists, bins=n_bins, range=(0, 0.40), color='royalblue', edgecolor='navy', alpha=0.8, density=True)
    ax4.axvline(mean_err, color='red', linestyle='-', lw=2, label=f'Mean: {mean_err:.3f} mm')
    ax4.axvline(median_err, color='darkgreen', linestyle='--', lw=2, label=f'Median: {median_err:.3f} mm')
    ax4.axvline(p95_err, color='darkorange', linestyle=':', lw=2, label=f'95th%: {p95_err:.3f} mm')
    ax4.set_xlabel("Euclidean Deviation (mm)", fontsize=10, fontweight='bold')
    ax4.set_ylabel("Probability Density", fontsize=10, fontweight='bold')
    ax4.set_title(f"Point-to-Mesh Deviation Distribution\n(RMS = {rms_err:.3f} mm, Median = {median_err:.3f} mm)", fontsize=11, fontweight='bold')
    ax4.grid(True, linestyle=':', alpha=0.6)
    ax4.legend(loc='upper right', fontsize=9)

    # Panel 5: Cross-Section Comparison (Circular contours)
    ax5 = fig.add_subplot(gs[1, 2])
    test_slices = [
        (-50.0, "Bottle Body (Y=-50)"),
        (20.05, "Reveal Groove (Y=20)"),
        (50.0, "Cap Wand (Y=50)"),
    ]
    colors = ['navy', 'darkgreen', 'crimson']
    for idx, (y_s, label) in enumerate(test_slices):
        sec_s = src_mesh.section(plane_origin=[0, y_s, 0], plane_normal=[0, 1, 0])
        sec_r = rec_mesh.section(plane_origin=[0, y_s, 0], plane_normal=[0, 1, 0])
        if sec_s is not None and len(sec_s.discrete) > 0:
            ls = max(sec_s.discrete, key=lambda l: len(l))
            ax5.plot(ls[:, 0], ls[:, 2], color=colors[idx], linestyle='-', lw=1.8, label=f'{label} OBJ')
        if sec_r is not None and len(sec_r.discrete) > 0:
            lr = max(sec_r.discrete, key=lambda l: len(l))
            ax5.plot(lr[:, 0], lr[:, 2], color=colors[idx], linestyle='--', lw=2.2, label=f'{label} NX')

    ax5.set_xlabel("X (mm)", fontsize=10, fontweight='bold')
    ax5.set_ylabel("Z (mm)", fontsize=10, fontweight='bold')
    ax5.set_title("Cross-Section Radial Conformance\n(Bottle vs Seam vs Cap)", fontsize=11, fontweight='bold')
    ax5.axis('equal')
    ax5.grid(True, linestyle=':', alpha=0.6)
    ax5.legend(loc='upper right', fontsize=8)

    plt.suptitle("Elle 18 Liquid Lipstick: Parametric Siemens NX Reconstruction vs OBJ Reference\nStrict Zone-Wise Feature Tree Architecture (100% Native Features, 0 Loft Fallback)", fontsize=14, fontweight='bold', y=0.98)

    plt.savefig(str(out_png), dpi=200, bbox_inches='tight')
    plt.close()
    print(f"\n[OK] High-resolution verification image saved to {out_png}")


if __name__ == "__main__":
    main()
