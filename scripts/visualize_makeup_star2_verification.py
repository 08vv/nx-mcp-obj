#!/usr/bin/env python3
"""
visualize_makeup_star2_verification.py
======================================
Visualizes side-by-side and overlay comparison between the source OBJ mesh
and the reconstructed Siemens NX CAD STL model.
"""

import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import trimesh
from pathlib import Path

def main():
    repo_root = Path(r"c:\Users\HP\Downloads\nx-mcp-obj")
    obj_path = repo_root / "obj" / "makeup_cosmetic_star2.obj"
    stl_path = repo_root / "Makeup_Cosmetic_Star2_Parametric.stl"
    out_png = repo_root / "scratch" / "makeup_star2_verification_render.png"

    print("Loading meshes...")
    mesh_obj = trimesh.load(str(obj_path))
    mesh_obj.apply_scale(100.0)

    mesh_cad = trimesh.load(str(stl_path))

    # CAD coordinates: X=CAD_X, Y=CAD_Y, Z=CAD_Z (Z is height)
    # OBJ coordinates: X=OBJ_X, Y=OBJ_HEIGHT, Z=OBJ_Z (Y is height)
    # Align OBJ to CAD coordinates: OBJ_Z_CAD = OBJ_Y + 25.5, OBJ_Y_CAD = OBJ_Z
    v_obj_aligned = np.column_stack([
        mesh_obj.vertices[:, 0],
        mesh_obj.vertices[:, 2],
        mesh_obj.vertices[:, 1] + 25.5
    ])

    fig = plt.figure(figsize=(18, 6))

    # 1. Source OBJ
    ax1 = fig.add_subplot(1, 3, 1, projection='3d')
    faces_obj = mesh_obj.faces[::4]
    p1 = Poly3DCollection(v_obj_aligned[faces_obj], alpha=0.85, edgecolor='black', linewidths=0.1)
    p1.set_facecolor('skyblue')
    ax1.add_collection3d(p1)
    ax1.set_xlim(-100, 100); ax1.set_ylim(-100, 100); ax1.set_zlim(0, 55)
    ax1.view_init(elev=35, azim=45)
    ax1.set_title('Source OBJ Mesh (Scaled to mm)')

    # 2. Reconstructed CAD PRT (Exported STL)
    ax2 = fig.add_subplot(1, 3, 2, projection='3d')
    faces_cad = mesh_cad.faces[::4]
    p2 = Poly3DCollection(mesh_cad.vertices[faces_cad], alpha=0.85, edgecolor='black', linewidths=0.1)
    p2.set_facecolor('lightgreen')
    ax2.add_collection3d(p2)
    ax2.set_xlim(-100, 100); ax2.set_ylim(-100, 100); ax2.set_zlim(0, 55)
    ax2.view_init(elev=35, azim=45)
    ax2.set_title('Reconstructed Siemens NX CAD Model')

    # 3. Top View Overlay Comparison
    ax3 = fig.add_subplot(1, 3, 3)
    # Slice both at mid-crimp height (Z = 30.5 mm)
    sec_obj = mesh_obj.section(plane_origin=[0, 5.0, 0], plane_normal=[0, 1, 0])
    if sec_obj:
        for ent in sec_obj.entities:
            pts = sec_obj.vertices[ent.points]
            ax3.plot(pts[:, 0], pts[:, 2], 'b-', lw=1.8, label='Source OBJ (Crimp Z=30.5)')
            break

    sec_cad = mesh_cad.section(plane_origin=[0, 0, 30.5], plane_normal=[0, 0, 1])
    if sec_cad:
        for ent in sec_cad.entities:
            pts = sec_cad.vertices[ent.points]
            ax3.plot(pts[:, 0], pts[:, 1], 'g--', lw=1.8, label='Reconstructed CAD (Crimp Z=30.5)')
            break

    # Also top flat cap
    sec_obj_top = mesh_obj.section(plane_origin=[0, 24.5, 0], plane_normal=[0, 1, 0])
    if sec_obj_top:
        for ent in sec_obj_top.entities:
            pts = sec_obj_top.vertices[ent.points]
            ax3.plot(pts[:, 0], pts[:, 2], 'r-', lw=1.5, label='Source OBJ (Top Z=50.0)')
            break

    sec_cad_top = mesh_cad.section(plane_origin=[0, 0, 50.0], plane_normal=[0, 0, 1])
    if sec_cad_top:
        for ent in sec_cad_top.entities:
            pts = sec_cad_top.vertices[ent.points]
            ax3.plot(pts[:, 0], pts[:, 1], 'm--', lw=1.5, label='Reconstructed CAD (Top Z=50.0)')
            break

    ax3.set_title('Cross-Section Contour Overlay Comparison')
    ax3.set_xlabel('X (mm)'); ax3.set_ylabel('Y (mm)')
    ax3.axis('equal'); ax3.grid(True); ax3.legend(loc='upper right', fontsize=8)

    plt.tight_layout()
    plt.savefig(str(out_png), dpi=200)
    print(f"[OK] Verification render saved: {out_png}")

if __name__ == "__main__":
    main()
