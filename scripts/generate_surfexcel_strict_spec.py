import json
import math
from pathlib import Path
from typing import List, Tuple
import numpy as np
import trimesh
from shapely.geometry import Polygon
from shapely.ops import unary_union
from scipy.interpolate import splprep, splev
import networkx as nx

REPO_ROOT = Path(r'c:\Users\HP\Downloads\nx-mcp-obj')
OBJ_PATH = REPO_ROOT / 'obj' / 'Surfexcel2_reduced.obj'
OUT_JSON = REPO_ROOT / 'Surfexcel2_strict_spec.json'
S = 110.0

def resample_loop(pts_2d: List[Tuple[float, float]], n_samples: int = 64) -> List[Tuple[float, float]]:
    pts = list(pts_2d)
    if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) > 1e-4:
        pts.append(pts[0])
    dists = [0.0]
    for i in range(len(pts) - 1):
        seg = math.hypot(pts[i+1][0] - pts[i][0], pts[i+1][1] - pts[i][1])
        dists.append(dists[-1] + seg)
    total_len = dists[-1]
    if total_len < 1e-4:
        return [(0.0, 0.0)] * n_samples
    target_dists = [float(k) * total_len / float(n_samples) for k in range(n_samples)]
    resampled = []
    seg_idx = 0
    for td in target_dists:
        while seg_idx < len(dists) - 2 and dists[seg_idx + 1] < td:
            seg_idx += 1
        d0, d1 = dists[seg_idx], dists[seg_idx + 1]
        p0, p1 = pts[seg_idx], pts[seg_idx + 1]
        t = (td - d0) / (d1 - d0) if (d1 - d0) > 1e-9 else 0.0
        rx = p0[0] + t * (p1[0] - p0[0])
        rz = p0[1] + t * (p1[1] - p0[1])
        resampled.append((rx, rz))
    
    area = sum((resampled[i][0] * resampled[(i+1)%n_samples][1] - resampled[i][1] * resampled[(i+1)%n_samples][0]) for i in range(n_samples))
    if area < 0:
        resampled = resampled[::-1]
    
    best_idx = int(min(range(len(resampled)), key=lambda i: resampled[i][0]))
    resampled = resampled[best_idx:] + resampled[:best_idx]
    return resampled

def extract_station(mesh, y_val, n_samples=64):
    sec = mesh.section(plane_origin=[0, y_val, 0], plane_normal=[0, 1, 0])
    if sec is None or len(sec.discrete) == 0:
        return None
    if len(sec.discrete) == 1:
        pts = [(p[0], p[2]) for p in sec.discrete[0]]
    else:
        polys = [Polygon([(p[0], p[2]) for p in d]) for d in sec.discrete if len(d) >= 3]
        u = unary_union(polys).convex_hull
        pts = list(u.exterior.coords)
    
    res = resample_loop(pts, n_samples)
    return [(round(x * S, 4), round(y_val * S, 4), round(z * S, 4)) for x, z in res]

def main():
    print(f'Loading OBJ: {OBJ_PATH}')
    mesh = trimesh.load(str(OBJ_PATH), process=False)
    
    zones = {}
    print('Extracting Zone 1: Lower Reservoir...')
    z1_ys = np.linspace(-0.98, -0.32, 16)
    zones['zone1_lower'] = [extract_station(mesh, y) for y in z1_ys]
    
    print('Extracting Zone 2: Handle & Mid Body...')
    z2_ys = np.linspace(-0.32, 0.22, 14)
    zones['zone2_handle'] = [extract_station(mesh, y) for y in z2_ys]
    
    print('Extracting Zone 3: Shoulder Sweep...')
    z3_ys = np.linspace(0.22, 0.72, 14)
    zones['zone3_shoulder'] = [extract_station(mesh, y) for y in z3_ys]
    
    print('Extracting Zone 4: Neck Collar...')
    z4_ys = np.linspace(0.72, 0.78, 5)
    zones['zone4_neck'] = [extract_station(mesh, y) for y in z4_ys]
    
    print('Extracting Zone 5: Organic Cap...')
    z5_ys = np.linspace(0.78, 0.990, 14)
    zones['zone5_cap'] = [extract_station(mesh, y) for y in z5_ys]
    
    print('Extracting Handle Opening Curve...')
    sec_z = mesh.section(plane_origin=[0, 0, 0], plane_normal=[0, 0, 1])
    hole = sec_z.discrete[1] * S
    tck, u = splprep([hole[:, 0], hole[:, 1]], s=0, per=True)
    u_new = np.linspace(0, 1, 64, endpoint=False)
    rx, ry = splev(u_new, tck)
    handle_opening_pts = [[round(x, 4), round(y, 4)] for x, y in zip(rx, ry)]
    
    print('Extracting Recessed Label Field Outline...')
    fc = mesh.triangles.mean(axis=1)
    fn = mesh.face_normals
    floor_f_idx = np.where((fc[:, 2] > 0.08) & (fc[:, 2] < 0.118) & (fc[:, 1] >= -0.78) & (fc[:, 1] <= 0.38) & (fn[:, 2] > 0.8))[0]
    floor_mesh = mesh.submesh([floor_f_idx], append=True)
    edges = floor_mesh.edges
    edge_tuples = [tuple(sorted(e)) for e in edges]
    from collections import Counter
    counts = Counter(edge_tuples)
    b_edges = [e for e, c in counts.items() if c == 1]
    G = nx.Graph()
    for u, v in b_edges:
        G.add_edge(u, v)
    cycles = sorted(nx.cycle_basis(G), key=len, reverse=True)
    c = cycles[0]
    pts = floor_mesh.vertices[c] * S
    tck, u = splprep([pts[:, 0], pts[:, 1]], s=15.0, per=True)
    u_new = np.linspace(0, 1, 64, endpoint=False)
    rx, ry = splev(u_new, tck)
    recess_pts = [[round(x, 4), round(y, 4)] for x, y in zip(rx, ry)]
    
    data = {
        'metadata': {
            'source_obj': str(OBJ_PATH),
            'scale': S,
            'description': 'High-fidelity zone specification for Surf Excel detergent jug',
        },
        'zones': zones,
        'handle_opening': handle_opening_pts,
        'recess_profile': recess_pts,
    }
    
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f'Successfully wrote specification to {OUT_JSON} ({OUT_JSON.stat().st_size:,} bytes)')

if __name__ == '__main__':
    main()
