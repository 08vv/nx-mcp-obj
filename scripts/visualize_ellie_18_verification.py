"""
visualize_ellie_18_verification.py
==================================
Comprehensive CAD geometric validation and multi-panel visual inspection
comparing the reference OBJ mesh (obj/Ellie_18_eye_liner.obj) against the
reconstructed parametric Siemens NX part (Ellie_18_eye_liner_Parametric.stl).
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
    obj_path = repo_root / "obj" / "Ellie_18_eye_liner.obj"
    stl_path = repo_root / "Ellie_18_eye_liner_Parametric.stl"
    out_png = repo_root / "Ellie_18_eye_liner_verification.png"

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
        ("Base & Lower Main Body", -100.5, 10.0),
        ("Collar & Ring Transitions", 10.0, 35.0),
        ("Upper Taper & Wand Stem", 35.0, 83.0),
        ("Tapered Tip & Apex Dome", 83.0, 100.5),
    ]

    print("\n  Regional Deviation Breakdown:")
    for reg_name, y0, y1 in regions:
        m = (samples_src[:, 1] >= y0) & (samples_src[:, 1] < y1)
        if np.any(m):
            sub_d = dists[m]
            print(f"    {reg_name:26s} (Y in [{y0:6.1f}, {y1:5.1f}] mm): Mean={sub_d.mean():.4f} mm, Median={np.median(sub_d):.4f} mm, 95%={np.percentile(sub_d, 95):.4f} mm")

    # 4. Multi-Panel High Resolution Plot
    print("\n[3/3] Generating High-Resolution Multi-Panel Verification Image...")
    fig = plt.figure(figsize=(18, 12), dpi=200)
    gs = fig.add_gridspec(2, 3, height_ratios=[1.2, 1.0], hspace=0.3, wspace=0.25)

    # Panel 1: Full-length Silhouette Overlay
    ax1 = fig.add_subplot(gs[:, 0])
    # Extract silhouette slices from both meshes along Y
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

    # Plot symmetrical silhouette profile (+R and -R)
    ax1.plot(src_r, y_valid, 'b-', label='OBJ Source (+R)', lw=2.0, alpha=0.85)
    ax1.plot(-src_r, y_valid, 'b-', label='OBJ Source (-R)', lw=2.0, alpha=0.85)
    ax1.plot(rec_r, y_valid, 'r--', label='NX Parametric (+R)', lw=2.0, alpha=0.85)
    ax1.plot(-rec_r, y_valid, 'r--', label='NX Parametric (-R)', lw=2.0, alpha=0.85)
    ax1.fill_betweenx(y_valid, -rec_r, rec_r, color='crimson', alpha=0.10)

    ax1.set_xlabel("Radius (mm)", fontsize=11, fontweight='bold')
    ax1.set_ylabel("Height Y (mm)", fontsize=11, fontweight='bold')
    ax1.set_title("Full-Length Profile Overlay\n(Length ~ 199.5 mm, Aspect Ratio ~ 14:1)", fontsize=12, fontweight='bold')
    ax1.grid(True, linestyle=':', alpha=0.6)
    ax1.legend(loc='lower left', fontsize=9)
    ax1.set_xlim(-11, 16)
    ax1.set_ylim(-105, 105)

    # Add landmark annotations on right side with proper spacing
    ax1.annotate("Middle Collar & Rings\n(Y=10 to 35 mm)", xy=(7.11, 15), xytext=(8.5, 15),
                 arrowprops=dict(arrowstyle="->", color='black', lw=1.2), fontsize=8.5, fontweight='bold')
    ax1.annotate("Long Upper Taper\n(Y=35 to 58 mm)", xy=(5.0, 45), xytext=(8.5, 45),
                 arrowprops=dict(arrowstyle="->", color='black', lw=1.2), fontsize=8.5)
    ax1.annotate("Slender Wand Stem\n(Dia ~ 8.8 mm)", xy=(4.4, 70), xytext=(8.5, 70),
                 arrowprops=dict(arrowstyle="->", color='black', lw=1.2), fontsize=8.5)
    ax1.annotate("Tapered Tip & Apex", xy=(2.5, 95), xytext=(8.5, 95),
                 arrowprops=dict(arrowstyle="->", color='black', lw=1.2), fontsize=8.5)
    ax1.annotate("Rounded Bottom", xy=(6.5, -98), xytext=(8.5, -98),
                 arrowprops=dict(arrowstyle="->", color='black', lw=1.2), fontsize=8.5)

    # Panel 2: Zoomed-in Middle Collar & Ring Transitions (Defining Geometry)
    ax2 = fig.add_subplot(gs[0, 1])
    m_col = (y_valid >= 5.0) & (y_valid <= 38.0)
    ax2.plot(y_valid[m_col], 2 * src_r[m_col], 'b-', lw=2.5, label='OBJ Reference Diameter')
    ax2.plot(y_valid[m_col], 2 * rec_r[m_col], 'r--', lw=2.5, label='NX Reconstructed Diameter')
    ax2.set_xlabel("Height Y (mm)", fontsize=10, fontweight='bold')
    ax2.set_ylabel("Diameter (mm)", fontsize=10, fontweight='bold')
    ax2.set_title("ZOOM: Collar & Ring Transitions\n(Step, Annular Groove, Raised Ridge)", fontsize=11, fontweight='bold')
    ax2.grid(True, linestyle=':', alpha=0.6)
    ax2.legend(loc='upper right', fontsize=9)

    # Annotate collar features
    ax2.axvline(15.08, color='gray', linestyle=':', alpha=0.7)
    ax2.text(15.2, 14.1, "Max Collar\nDia 14.23 mm", fontsize=8, color='navy')
    ax2.axvline(22.3, color='gray', linestyle=':', alpha=0.7)
    ax2.text(22.5, 12.6, "Step Land\nDia 12.40 mm", fontsize=8, color='navy')
    ax2.axvline(27.06, color='gray', linestyle=':', alpha=0.7)
    ax2.text(27.2, 11.2, "Groove\n11.49 mm", fontsize=8, color='navy')
    ax2.axvline(29.46, color='gray', linestyle=':', alpha=0.7)
    ax2.text(29.6, 12.1, "Ridge\n11.92 mm", fontsize=8, color='navy')

    # Panel 3: Zoomed-in Upper Taper into Wand
    ax3 = fig.add_subplot(gs[0, 2])
    m_wand = (y_valid >= 32.0) & (y_valid <= 85.0)
    ax3.plot(y_valid[m_wand], 2 * src_r[m_wand], 'b-', lw=2.5, label='OBJ Reference')
    ax3.plot(y_valid[m_wand], 2 * rec_r[m_wand], 'r--', lw=2.5, label='NX Reconstructed')
    ax3.set_xlabel("Height Y (mm)", fontsize=10, fontweight='bold')
    ax3.set_ylabel("Diameter (mm)", fontsize=10, fontweight='bold')
    ax3.set_title("ZOOM: Long Tapered Upper Section\n(Collar Transition into Slender Wand)", fontsize=11, fontweight='bold')
    ax3.grid(True, linestyle=':', alpha=0.6)
    ax3.legend(loc='upper right', fontsize=9)

    # Panel 4: Zoomed-in Tip & Bottom Ends
    ax4 = fig.add_subplot(gs[1, 1])
    # Tip
    m_tip = (y_valid >= 80.0) & (y_valid <= 99.5)
    ax4.plot(y_valid[m_tip], 2 * src_r[m_tip], 'b-', lw=2.5, label='OBJ Tip')
    ax4.plot(y_valid[m_tip], 2 * rec_r[m_tip], 'r--', lw=2.5, label='NX Tip')
    ax4.set_xlabel("Height Y (mm)", fontsize=10, fontweight='bold')
    ax4.set_ylabel("Diameter (mm)", fontsize=10, fontweight='bold')
    ax4.set_title("ZOOM: Tapered Tip & Rounded Apex\n(Y = 80 to 100 mm)", fontsize=11, fontweight='bold')
    ax4.grid(True, linestyle=':', alpha=0.6)
    ax4.legend(loc='lower left', fontsize=9)

    # Panel 5: Quantitative Error Distribution & Summary
    ax5 = fig.add_subplot(gs[1, 2])
    ax5.hist(dists, bins=50, color='forestgreen', alpha=0.75, edgecolor='black')
    ax5.axvline(mean_err, color='red', linestyle='--', lw=2, label=f'Mean Error = {mean_err:.3f} mm')
    ax5.axvline(p95_err, color='orange', linestyle=':', lw=2, label=f'95th Percentile = {p95_err:.3f} mm')
    ax5.set_xlabel("Surface Deviation (mm)", fontsize=10, fontweight='bold')
    ax5.set_title(f"Surface Accuracy Distribution\n(Mean: {mean_err:.2f} mm, 95%: {p95_err:.2f} mm)", fontsize=11, fontweight='bold')
    ax5.grid(True, linestyle=':', alpha=0.6)
    ax5.legend(loc='upper right', fontsize=9)

    # Overall title
    plt.suptitle("SIEMENS NX PARAMETRIC RECONSTRUCTION VERIFICATION\nModel: Ellie_18_eye_liner_Parametric.prt | Reference: obj/Ellie_18_eye_liner.obj",
                 fontsize=14, fontweight='bold', y=0.98)

    plt.savefig(str(out_png), dpi=200, bbox_inches='tight')
    plt.close()

    print(f"[OK] Saved verification image: {out_png}")
    print("Verification completed successfully.")


if __name__ == "__main__":
    main()
