import trimesh
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np

m_cad = trimesh.load('Kissan_Bottle_Parametric.stl')

fig = plt.figure(figsize=(18, 12))

cad_simp = m_cad

# 1. 3D Isometric View
ax1 = fig.add_subplot(2, 2, 1, projection='3d')
# NX coordinate: X = width, Y = height, Z = depth.
# For matplotlib 3D standard (X horizontal, Y depth, Z vertical), map:
# X_plot = CAD_X, Y_plot = CAD_Z, Z_plot = CAD_Y
verts_plot = np.column_stack([cad_simp.vertices[:, 0], cad_simp.vertices[:, 2], cad_simp.vertices[:, 1]])
mesh_poly = Poly3DCollection(verts_plot[cad_simp.faces], alpha=0.9, edgecolor='none')
mesh_poly.set_facecolor('#d9534f')  # Kissan red / bottle styling
ax1.add_collection3d(mesh_poly)

ax1.set_xlim(-40, 40)
ax1.set_ylim(-40, 40)
ax1.set_zlim(-105, 105)
ax1.set_box_aspect((80, 80, 210))
ax1.view_init(elev=18, azim=45)
ax1.set_title('3D Isometric Shaded View: Reconstructed Parametric Model', fontsize=12, fontweight='bold')
ax1.set_xlabel('X (Width, mm)')
ax1.set_ylabel('Z (Depth, mm)')
ax1.set_zlabel('Y (Height, mm)')

# Annotations on 3D view
ax1.text(0, 25, 95, 'Cap Closure (D=22.4, H=17.8)', color='darkred', fontweight='bold', fontsize=9)
ax1.text(0, 32, 45, 'Conical Shoulder (Taper 14.8°)', color='darkblue', fontweight='bold', fontsize=9)
ax1.text(0, 38, -40, 'Cylindrical Body (D=58.5, H=108.0)', color='darkgreen', fontweight='bold', fontsize=9)
ax1.text(0, 32, -98, 'Heel Blend (R=5.0) & Punt Base', color='purple', fontweight='bold', fontsize=9)

# 2. Front Elevation (X-Y)
ax2 = fig.add_subplot(2, 2, 2)
# Outline contour from section
outline_xs = []
outline_ys = []
ys_step = np.linspace(-100, 99.4, 150)
for y in ys_step:
    sec = m_cad.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
    if sec:
        xs = sec.vertices[:, 0]
        outline_xs.append((np.min(xs), np.max(xs)))
        outline_ys.append(y)
outline_xs = np.array(outline_xs)
outline_ys = np.array(outline_ys)

ax2.fill_betweenx(outline_ys, outline_xs[:, 0], outline_xs[:, 1], color='#e67e22', alpha=0.35, label='CAD Solid Profile')
ax2.plot(outline_xs[:, 0], outline_ys, color='#d35400', linewidth=2)
ax2.plot(outline_xs[:, 1], outline_ys, color='#d35400', linewidth=2)
ax2.axvline(0, color='gray', linestyle='-.', alpha=0.7, label='Axis of Revolution')

# Dimensional lines
ax2.annotate('', xy=(35, -100.0), xytext=(35, 99.47), arrowprops=dict(arrowstyle='<->', color='blue', lw=1.5))
ax2.text(37, 0, 'Total Height: 199.47 mm', color='blue', fontweight='bold', rotation=90, verticalalignment='center')

ax2.annotate('', xy=(-35, -100.0), xytext=(-35, 8.0), arrowprops=dict(arrowstyle='<->', color='green', lw=1.5))
ax2.text(-44, -46, 'Body H: 108.0 mm', color='green', fontweight='bold', rotation=90, verticalalignment='center')

ax2.annotate('', xy=(-35, 8.0), xytext=(-35, 81.67), arrowprops=dict(arrowstyle='<->', color='purple', lw=1.5))
ax2.text(-44, 45, 'Shoulder H: 73.7 mm', color='purple', fontweight='bold', rotation=90, verticalalignment='center')

ax2.annotate('', xy=(-35, 81.67), xytext=(-35, 99.47), arrowprops=dict(arrowstyle='<->', color='red', lw=1.5))
ax2.text(-44, 90, 'Cap H: 17.8 mm', color='red', fontweight='bold', rotation=90, verticalalignment='center')

ax2.set_xlim(-50, 50)
ax2.set_ylim(-110, 110)
ax2.set_title('Front Elevation: Parametric Driving Heights', fontsize=12, fontweight='bold')
ax2.set_xlabel('X (mm)')
ax2.set_ylabel('Y (Height, mm)')
ax2.set_aspect('equal')
ax2.grid(True, linestyle='--', alpha=0.5)
ax2.legend(loc='upper right')

# 3. Top Plan View (X-Z)
ax3 = fig.add_subplot(2, 2, 3)
th = np.linspace(0, 2*np.pi, 200)
# Body circle
ax3.plot(29.25*np.cos(th), 29.25*np.sin(th), 'g-', linewidth=2, label='Body OD: Ø58.50 mm')
# Cap circle
ax3.plot(11.20*np.cos(th), 11.20*np.sin(th), 'r-', linewidth=2, label='Cap OD: Ø22.41 mm')
# Neck circle
ax3.plot(9.39*np.cos(th), 9.39*np.sin(th), 'b--', linewidth=1.5, label='Neck OD: Ø18.78 mm')
ax3.fill(11.20*np.cos(th), 11.20*np.sin(th), color='red', alpha=0.2)
ax3.set_title('Top Plan View (X-Z): Cap, Neck & Body Diameters', fontsize=12, fontweight='bold')
ax3.set_xlabel('X (mm)')
ax3.set_ylabel('Z (mm)')
ax3.set_aspect('equal')
ax3.grid(True, linestyle='--', alpha=0.5)
ax3.legend(loc='upper right')

# 4. Bottom View (X-Z Base Punt)
ax4 = fig.add_subplot(2, 2, 4)
# Outer body
ax4.plot(29.25*np.cos(th), 29.25*np.sin(th), 'g--', linewidth=1.5, label='Heel Outer: Ø58.50 mm')
# Standing contact ring
ax4.plot(23.20*np.cos(th), 23.20*np.sin(th), 'k-', linewidth=2.5, label='Standing Contact Ring: Ø46.40 mm')
# Recess pocket
ax4.plot(20.20*np.cos(th), 20.20*np.sin(th), 'purple', linestyle='-.', linewidth=1.5, label='Concave Punt Recess (Depth: 2.20 mm)')
ax4.fill(20.20*np.cos(th), 20.20*np.sin(th), color='purple', alpha=0.15)
ax4.set_title('Bottom View: Standing Ring & Recessed Punt', fontsize=12, fontweight='bold')
ax4.set_xlabel('X (mm)')
ax4.set_ylabel('Z (mm)')
ax4.set_aspect('equal')
ax4.grid(True, linestyle='--', alpha=0.5)
ax4.legend(loc='upper right')

plt.suptitle('Siemens NX Parametric Model: Multi-View Drawing & Engineering Inspection', fontsize=15, fontweight='bold')
plt.tight_layout()
plt.savefig('kissan_bottle_views.png', dpi=160)
print('Saved kissan_bottle_views.png')
