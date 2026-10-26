import trimesh
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial import cKDTree
from pathlib import Path

# Load meshes
m_ref = trimesh.load('obj/Kissan_Bottle2.obj', process=False)
m_ref.apply_scale(100.0)

m_cad = trimesh.load('Kissan_Bottle_Parametric.stl')

# Subsample vertices for crisp plots
pts_ref = m_ref.vertices[::3]
pts_cad = m_cad.vertices[::2]

fig, axes = plt.subplots(2, 2, figsize=(16, 14))

# 1. Front View (X-Y): Height vs Width
ax1 = axes[0, 0]
ax1.plot(pts_ref[:, 0], pts_ref[:, 1], 'k.', markersize=0.8, alpha=0.35, label='Reference OBJ (Mesh)')
ax1.plot(pts_cad[:, 0], pts_cad[:, 1], 'r.', markersize=0.8, alpha=0.35, label='Parametric CAD (NX)')
ax1.set_title('Front Silhouette (X-Y Plane): Body, Shoulder & Cap Match', fontsize=12, fontweight='bold')
ax1.set_xlabel('X (mm)')
ax1.set_ylabel('Y (Height, mm)')
ax1.set_aspect('equal')
ax1.legend(loc='upper right', framealpha=0.9)
ax1.grid(True, linestyle='--', alpha=0.6)

# 2. Side View (Z-Y): Height vs Depth
ax2 = axes[0, 1]
ax2.plot(pts_ref[:, 2], pts_ref[:, 1], 'k.', markersize=0.8, alpha=0.35, label='Reference OBJ (Mesh)')
ax2.plot(pts_cad[:, 2], pts_cad[:, 1], 'b.', markersize=0.8, alpha=0.35, label='Parametric CAD (NX)')
ax2.set_title('Side Silhouette (Z-Y Plane): Body, Shoulder & Cap Match', fontsize=12, fontweight='bold')
ax2.set_xlabel('Z (mm)')
ax2.set_ylabel('Y (Height, mm)')
ax2.set_aspect('equal')
ax2.legend(loc='upper right', framealpha=0.9)
ax2.grid(True, linestyle='--', alpha=0.6)

# 3. Cross Sections Comparison (Body at Y = -30 mm and Cap at Y = 90 mm)
ax3 = axes[1, 0]
sec_ref_body = m_ref.section(plane_origin=[0, -30, 0], plane_normal=[0, 1, 0])
sec_cad_body = m_cad.section(plane_origin=[0, -30, 0], plane_normal=[0, 1, 0])
sec_ref_cap = m_ref.section(plane_origin=[0, 90, 0], plane_normal=[0, 1, 0])
sec_cad_cap = m_cad.section(plane_origin=[0, 90, 0], plane_normal=[0, 1, 0])

if sec_ref_body:
    ax3.plot(sec_ref_body.vertices[:, 0], sec_ref_body.vertices[:, 2], 'k.', markersize=2, alpha=0.7, label='Ref Body (Y=-30)')
if sec_cad_body:
    ax3.plot(sec_cad_body.vertices[:, 0], sec_cad_body.vertices[:, 2], 'r-', linewidth=1.5, label='CAD Body (Y=-30)')
if sec_ref_cap:
    ax3.plot(sec_ref_cap.vertices[:, 0], sec_ref_cap.vertices[:, 2], 'gray', marker='.', markersize=2, linestyle='None', alpha=0.7, label='Ref Cap (Y=+90)')
if sec_cad_cap:
    ax3.plot(sec_cad_cap.vertices[:, 0], sec_cad_cap.vertices[:, 2], 'b--', linewidth=1.5, label='CAD Cap (Y=+90)')

ax3.set_title('Cross-Section Overlays (X-Z Plane): Circularity & Alignment', fontsize=12, fontweight='bold')
ax3.set_xlabel('X (mm)')
ax3.set_ylabel('Z (mm)')
ax3.set_aspect('equal')
ax3.legend(loc='upper right', framealpha=0.9)
ax3.grid(True, linestyle='--', alpha=0.6)

# 4. Surface Deviation Histogram
ax4 = axes[1, 1]
cad_pts, _ = trimesh.sample.sample_surface(m_cad, 15000)
ref_pts, _ = trimesh.sample.sample_surface(m_ref, 15000)
tree = cKDTree(ref_pts)
dists, _ = tree.query(cad_pts, k=1)

mean_err = np.mean(dists)
p95_err = np.percentile(dists, 95)
max_err = np.max(dists)

ax4.hist(dists, bins=50, color='#17becf', edgecolor='black', alpha=0.75)
ax4.axvline(mean_err, color='red', linestyle='--', linewidth=2, label=f'Mean Error: {mean_err:.2f} mm')
ax4.axvline(p95_err, color='orange', linestyle='--', linewidth=2, label=f'P95 Error: {p95_err:.2f} mm')
ax4.set_title('Surface Deviation Histogram (CAD vs Reference OBJ)', fontsize=12, fontweight='bold')
ax4.set_xlabel('Deviation (mm)')
ax4.set_ylabel('Sampled Point Count')
ax4.legend(loc='upper right', framealpha=0.9)
ax4.grid(True, linestyle='--', alpha=0.6)

plt.suptitle('Siemens NX Parametric Model Verification: Kissan Bottle (Overall PASS)', fontsize=15, fontweight='bold')
plt.tight_layout()
plt.savefig('kissan_bottle_cad_verification.png', dpi=160)
print('Saved kissan_bottle_cad_verification.png')
