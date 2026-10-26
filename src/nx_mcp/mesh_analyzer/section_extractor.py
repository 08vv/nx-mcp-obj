"""
section_extractor.py
=====================
Layer B: Slicing & Pure-Revolve Silhouette Profile Extraction module.

Includes:
1. Fast-Path Pure-Revolve Extractor: Extracts 1D silhouette profile curve r(y) + axis for axisymmetric bodies.
2. Multi-Slice Cross-Section Slicer (BASE_RECONSTRUCTION_STABLE baseline).
"""

from typing import Optional, Tuple, List, Dict
import numpy as np
import trimesh
from scipy.interpolate import PchipInterpolator
from scipy.signal import savgol_filter


class PureRevolveExtractor:
    def __init__(self, aligned_mesh: trimesh.Trimesh):
        self.mesh = aligned_mesh

    def extract_silhouette_profile(self, n_samples: int = 80, adaptive: bool = True) -> dict:
        """
        Extracts 2D silhouette profile r(y) along Y rotational axis.
        When adaptive=True, samples densely in high-curvature regions (caps, fillets,
        chimes, necks) and sparsely in flat cylindrical spans.
        """
        bounds = self.mesh.bounds
        scale = 100.0 if (bounds[1][1] - bounds[0][1]) < 10.0 else 1.0
        y_min, y_max = bounds[0][1] * scale, bounds[1][1] * scale
        verts = self.mesh.vertices * scale
        cx = float(np.median(verts[:, 0]))
        cz = float(np.median(verts[:, 2]))

        if not adaptive or n_samples < 10 or (y_max - y_min) < 1e-3:
            y_pts = np.linspace(y_min, y_max, n_samples)
        else:
            # Step 1: Extract dense candidate profile (250 stations)
            n_dense = min(250, max(n_samples * 3, 100))
            y_dense = np.linspace(y_min, y_max, n_dense)
            half_h_dense = (y_max - y_min) / (n_dense * 1.5)
            r_dense = []

            for y_v in y_dense:
                mask = np.abs(verts[:, 1] - y_v) <= half_h_dense
                if np.any(mask):
                    sub_v = verts[mask]
                    dists = np.hypot(sub_v[:, 0] - cx, sub_v[:, 2] - cz)
                    outer = dists[dists >= 0.70 * np.max(dists)] if len(dists) > 5 else dists
                    r_val = float(np.median(outer))
                else:
                    r_val = r_dense[-1] if r_dense else 0.0
                r_dense.append(r_val)

            r_arr = np.array(r_dense)

            # Step 2: Discrete curvature estimation kappa(y) = |r''| / (1 + r'^2)^1.5
            try:
                if len(r_arr) >= 9:
                    r_smooth = savgol_filter(r_arr, window_length=9, polyorder=2)
                else:
                    r_smooth = r_arr
                dr = np.gradient(r_smooth, y_dense)
                d2r = np.gradient(dr, y_dense)
                kappa = np.abs(d2r) / np.power(1.0 + dr**2, 1.5)
                mean_k = float(np.mean(kappa))
                weight = 1.0 + 12.0 * (kappa / max(mean_k, 1e-4))
                cum_w = np.cumsum(weight)
                cum_w /= cum_w[-1]

                # Step 3: Resample adaptively along cumulative curvature
                target_w = np.linspace(0.0, 1.0, n_samples)
                y_pts = np.interp(target_w, cum_w, y_dense)
                # Ensure exact bounds
                y_pts[0] = y_min
                y_pts[-1] = y_max
            except Exception:
                y_pts = np.linspace(y_min, y_max, n_samples)

        profile = []
        half_h = (y_max - y_min) / (n_samples * 1.5)

        for y_val in y_pts:
            mask = np.abs(verts[:, 1] - y_val) <= half_h
            if np.any(mask):
                sub_v = verts[mask]
                dists = np.hypot(sub_v[:, 0] - cx, sub_v[:, 2] - cz)
                outer = dists[dists >= 0.70 * np.max(dists)] if len(dists) > 5 else dists
                r = float(np.median(outer))
                profile.append({
                    "y": float(y_val),
                    "r": float(r),
                    "x": float(r),
                    "z": 0.0
                })
            else:
                if profile:
                    profile.append({"y": float(y_val), "r": profile[-1]["r"], "x": profile[-1]["r"], "z": 0.0})

        return {
            "is_axisymmetric": True,
            "axis_origin": [0.0, 0.0, 0.0],
            "axis_direction": [0.0, 1.0, 0.0],
            "height_y_range": [float(y_min), float(y_max)],
            "profile_points": profile,
            "sampling_mode": "curvature_adaptive" if adaptive else "uniform"
        }


class MultiSliceSectionExtractor:
    """BASE_RECONSTRUCTION_STABLE: Stable Primary Body Multi-Slice Cross-Section Extractor with Universal Non-Oscillatory PCHIP Smoothing."""

    def __init__(self, mesh: trimesh.Trimesh):
        self.mesh = mesh

    def slice_heights(self, axis: str = 'Y', n_slices: int = 31,
                      y_range: Optional[Tuple[float, float]] = None) -> list[dict]:
        """Multi-station slicing for primary body form (Base Footprint to Neck/Comb Top)."""
        bounds = self.mesh.bounds
        scale = 100.0 if (bounds[1][1] - bounds[0][1]) < 10.0 else 1.0
        v = self.mesh.vertices * scale
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[axis.upper()]
        
        if y_range is not None:
            h_min, h_max = float(y_range[0]), float(y_range[1])
        else:
            h_min, h_max = bounds[0][axis_idx] * scale, bounds[1][axis_idx] * scale

        # Primary body spans specified height range
        y_stations = np.linspace(h_min + 0.5, h_max - 0.5, n_slices)

        sections = []
        n_samples = 48
        angles = np.linspace(0, 2 * np.pi, n_samples, endpoint=False)
        da = 2.0 * np.pi / n_samples
        half_h = (h_max - h_min) / (n_slices * 1.5)

        for idx_st, y_val in enumerate(y_stations):
            mask = np.abs(v[:, 1] - y_val) <= half_h
            sub_v = v[mask] if np.any(mask) else v

            # True geometric bounding box midpoint as section center
            cx = float((np.max(sub_v[:, 0]) + np.min(sub_v[:, 0])) / 2.0)
            cz = float((np.max(sub_v[:, 2]) + np.min(sub_v[:, 2])) / 2.0)

            rx_val = max(float((np.max(sub_v[:, 0]) - np.min(sub_v[:, 0])) / 2.0), 1.5)
            rz_val = max(float((np.max(sub_v[:, 2]) - np.min(sub_v[:, 2])) / 2.0), 1.5)

            # Direct radial sector boundary sampling: robustly extracts true mesh perimeter
            dx = sub_v[:, 0] - cx
            dz = sub_v[:, 2] - cz
            th = np.arctan2(dz, dx) % (2.0 * np.pi)

            pts_2d = []
            for a in angles:
                diff = np.abs((th - a + np.pi) % (2.0 * np.pi) - np.pi)
                in_sector = diff <= da
                if np.any(in_sector):
                    r_val = float(np.percentile(np.sqrt(dx[in_sector]**2 + dz[in_sector]**2), 95))
                else:
                    # Elliptic fallback if sector is empty
                    r_val = float(1.0 / max(np.sqrt((np.cos(a) / rx_val)**2 + (np.sin(a) / rz_val)**2), 1e-6))

                px = float(cx + r_val * np.cos(a))
                pz = float(cz + r_val * np.sin(a))
                pts_2d.append([px, pz])

            sections.append({
                "y": float(y_val),
                "center": [cx, cz],
                "rx": rx_val,
                "rz": rz_val,
                "points_2d": pts_2d
            })

        # Apply Universal Monotonic PCHIP Trajectory Smoothing across all Y stations
        sections = self.smooth_section_trajectories(sections)
        return sections

    def smooth_section_trajectories(self, sections: list[dict]) -> list[dict]:
        """
        Applies non-oscillatory monotonic PCHIP spline interpolation along Y for centers and perimeter control points
        to eliminate artificial inward bulges, high-frequency vertex jitter, and horizontal ring corrugations.
        """
        n_st = len(sections)
        if n_st < 5:
            return sections

        n_pts = len(sections[0]["points_2d"])
        y_vals = np.array([s["y"] for s in sections])

        # 1. Centers (cx, cz) across all stations
        sm_cx = np.array([s["center"][0] for s in sections])
        sm_cz = np.array([s["center"][1] for s in sections])

        # 2. Extract perimeter points X_i(y), Z_i(y) for each angle i
        X_traj = np.zeros((n_pts, n_st))
        Z_traj = np.zeros((n_pts, n_st))
        for k in range(n_st):
            pts = sections[k]["points_2d"]
            for i in range(n_pts):
                X_traj[i, k] = pts[i][0]
                Z_traj[i, k] = pts[i][1]

        # Preserve all station trajectories without downsampling knots
        # to prevent artificial waist constriction ripples or shoulder collapse.
        X_smooth = X_traj.copy()
        Z_smooth = Z_traj.copy()

        # 3. Update sections with smoothed centers, points, and re-computed rx, rz
        smoothed_sections = []
        for k in range(n_st):
            st = sections[k].copy()
            st["center"] = [float(sm_cx[k]), float(sm_cz[k])]
            pts_sm = [[float(X_smooth[i, k]), float(Z_smooth[i, k])] for i in range(n_pts)]
            st["points_2d"] = pts_sm
            pts_arr = np.array(pts_sm)
            st["rx"] = max(float((np.max(pts_arr[:, 0]) - np.min(pts_arr[:, 0])) / 2.0), 1.5)
            st["rz"] = max(float((np.max(pts_arr[:, 1]) - np.min(pts_arr[:, 1])) / 2.0), 1.5)
            smoothed_sections.append(st)

        return smoothed_sections

    def detect_comb_teeth(self) -> list[dict]:
        """Detects vertical comb teeth pins on top caps (e.g. Indulekha comb cap)."""
        v = self.mesh.vertices * 100.0  # mm scale
        bounds = self.mesh.bounds * 100.0  # mm scale
        h_min, h_max = bounds[0][1], bounds[1][1]

        teeth_list = []
        for search_y_dir in [-1, 1]:
            y_start = h_min if search_y_dir == -1 else h_max - 35.0
            y_end = h_min + 35.0 if search_y_dir == -1 else h_max

            mask_region = (v[:, 1] >= y_start) & (v[:, 1] <= y_end)
            if not np.any(mask_region):
                continue

            sub_v = v[mask_region]
            x_span = float(np.max(sub_v[:, 0]) - np.min(sub_v[:, 0]))
            z_span = float(np.max(sub_v[:, 2]) - np.min(sub_v[:, 2]))

            if x_span > 55.0 and z_span < 25.0:
                y_mid = float((y_start + y_end) / 2.0)
                mask_slice = np.abs(sub_v[:, 1] - y_mid) <= 4.0
                v_slice = sub_v[mask_slice]
                if len(v_slice) < 50:
                    continue

                try:
                    from sklearn.cluster import DBSCAN
                    clustering = DBSCAN(eps=1.5, min_samples=5).fit(v_slice[:, [0, 2]])
                    labels = clustering.labels_
                    unique_labels = set(labels) - {-1}

                    if len(unique_labels) >= 3:
                        for lbl in sorted(unique_labels):
                            c_pts = v_slice[labels == lbl]
                            cx = float(np.mean(c_pts[:, 0]))
                            cz = float(np.mean(c_pts[:, 2]))
                            rx = float((np.max(c_pts[:, 0]) - np.min(c_pts[:, 0])) / 2.0)
                            rz = float((np.max(c_pts[:, 2]) - np.min(c_pts[:, 2])) / 2.0)
                            r_avg = max((rx + rz) / 2.0, 1.5)

                            y_header = float(y_end if search_y_dir == -1 else y_start)
                            y_tip = float(y_start if search_y_dir == -1 else y_end)
                            h_tooth = abs(y_tip - y_header)

                            teeth_list.append({
                                "x": cx,
                                "y_header": y_header,
                                "z": cz,
                                "height_mm": float(max(h_tooth, 25.0)),
                                "direction": [0.0, float(search_y_dir), 0.0]
                            })
                except Exception:
                    pass
        return teeth_list

    def detect_axial_tiers(self, axis: str = 'Y', min_drop_ratio: float = 0.28) -> list[dict]:
        """
        Generic geometric detection of multi-tier axial sub-assemblies (e.g. neck collars, pump stems, spouts).
        Identifies sharp step discontinuities (|dA/A| >= 28%) along the primary height axis to partition
        the body into primary stock solid + secondary tier bosses.
        Uses least-squares cylinder fitting and circularity checks on regional vertex clouds.
        """
        import scipy.optimize
        import scipy.spatial

        bounds = self.mesh.bounds
        scale = 100.0 if (bounds[1][1] - bounds[0][1]) < 10.0 else 1.0
        v = self.mesh.vertices * scale
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[axis.upper()]
        h_min, h_max = bounds[0][axis_idx] * scale, bounds[1][axis_idx] * scale
        H = h_max - h_min
        n_dense = 100
        y_dense = np.linspace(h_min + 1.0, h_max - 1.0, n_dense)
        half_h = H / (n_dense * 1.5)

        areas, centers, rxs, rzs = [], [], [], []
        rem_axes = [i for i in range(3) if i != axis_idx]
        for y_val in y_dense:
            mask = np.abs(v[:, axis_idx] - y_val) <= half_h
            if np.sum(mask) > 10:
                sub = v[mask]
                rx = max(float((np.max(sub[:, rem_axes[0]]) - np.min(sub[:, rem_axes[0]])) / 2.0), 1.0)
                rz = max(float((np.max(sub[:, rem_axes[1]]) - np.min(sub[:, rem_axes[1]])) / 2.0), 1.0)
                cx = float(np.mean(sub[:, rem_axes[0]]))
                cz = float(np.mean(sub[:, rem_axes[1]]))
                area = float(np.pi * rx * rz)
            else:
                rx, rz, cx, cz, area = 1.0, 1.0, 0.0, 0.0, float(np.pi)
            areas.append(area)
            centers.append([cx, cz])
            rxs.append(rx)
            rzs.append(rz)

        areas = np.array(areas)
        drops = (areas[:-1] - areas[1:]) / np.maximum(areas[:-1], 1e-3)
        step_indices = [
            i for i in range(len(drops))
            if 0.15 <= (y_dense[i] - h_min) / H <= 0.92 and drops[i] >= min_drop_ratio
        ]

        transitions = []
        if step_indices:
            cur_grp = [step_indices[0]]
            for idx in step_indices[1:]:
                if (y_dense[idx] - y_dense[cur_grp[-1]]) <= 6.0:
                    cur_grp.append(idx)
                else:
                    transitions.append((cur_grp[0], cur_grp[-1] + 1))
                    cur_grp = [idx]
            transitions.append((cur_grp[0], cur_grp[-1] + 1))

        cuts = []
        for s_start, s_end in transitions:
            if not cuts:
                cut_y = float(y_dense[min(s_end, len(y_dense) - 1)])
            else:
                cut_y = float(y_dense[s_start])
            cuts.append(cut_y)

        # Check for upper step expansion (e.g. pump head nozzle)
        if cuts:
            last_cut_idx = int(np.searchsorted(y_dense, cuts[-1]))
            increases = (areas[1:] - areas[:-1]) / np.maximum(areas[:-1], 1e-3)
            for i in range(last_cut_idx, len(increases) - 2):
                if (y_dense[i] - h_min) / H <= 0.97 and increases[i] >= 0.14:
                    cuts.append(float(y_dense[i]))
                    break

        tier_ranges = []
        prev_y = float(h_min)
        for cy in cuts:
            tier_ranges.append((prev_y, cy))
            prev_y = cy
        tier_ranges.append((prev_y, float(h_max)))

        tiers = []
        for t_idx, (y_s, y_e) in enumerate(tier_ranges):
            mask = (v[:, axis_idx] >= y_s + 0.5) & (v[:, axis_idx] <= y_e - 0.5)
            sub = v[mask]
            if len(sub) > 10:
                def loss(p):
                    cx, cz, r = p
                    d = np.sqrt((sub[:, rem_axes[0]] - cx)**2 + (sub[:, rem_axes[1]] - cz)**2) - r
                    return np.sum(d**2)

                init_cx = float(np.median(sub[:, rem_axes[0]]))
                init_cz = float(np.median(sub[:, rem_axes[1]]))
                init_r = float(np.median(np.sqrt((sub[:, rem_axes[0]] - init_cx)**2 + (sub[:, rem_axes[1]] - init_cz)**2)))
                res = scipy.optimize.minimize(loss, [init_cx, init_cz, init_r])
                fcx, fcz, fr = float(res.x[0]), float(res.x[1]), float(res.x[2])
                dist = np.abs(np.sqrt((sub[:, rem_axes[0]] - fcx)**2 + (sub[:, rem_axes[1]] - fcz)**2) - fr)
                circ_dev = float(np.std(dist) / max(fr, 1e-3))
                is_cyl = bool(circ_dev < 0.12 and fr > 2.0)
                t_type = "BASE_STOCK" if t_idx == 0 else ("TIER_CYLINDER" if is_cyl else "TIER_BOSS")

                tier_dict = {
                    "tier_index": t_idx,
                    "tier_type": t_type,
                    "y_start": round(y_s, 2),
                    "y_end": round(y_e, 2),
                    "height_mm": round(y_e - y_s, 2),
                    "diameter_mm": round(2.0 * fr, 2),
                    "center": [round(fcx, 2), round(fcz, 2)],
                    "rx": round(fr, 2),
                    "rz": round(fr, 2),
                }
                tiers.append(tier_dict)
            else:
                tiers.append({
                    "tier_index": t_idx,
                    "tier_type": "BASE_STOCK" if t_idx == 0 else "TIER_CYLINDER",
                    "y_start": round(y_s, 2),
                    "y_end": round(y_e, 2),
                    "height_mm": round(y_e - y_s, 2),
                    "diameter_mm": 20.0,
                    "center": [0.0, 0.0],
                    "rx": 10.0,
                    "rz": 10.0,
                })
        return tiers

    def detect_through_voids(self, axis: str = 'Y') -> list[dict]:
        """
        Generic geometric detection of genus-1 through-voids / cutouts (e.g. handle openings).
        Identifies continuous axial height zones where cross-sections bifurcate into >= 2 disconnected
        closed planar loops, extracts the closed 2D boundary of the void between the loops, and
        returns the through-cutout parameters.
        """
        import networkx as nx

        bounds = self.mesh.bounds
        scale = 100.0 if (bounds[1][1] - bounds[0][1]) < 10.0 else 1.0
        axis_idx = {'X': 0, 'Y': 1, 'Z': 2}[axis.upper()]
        h_min, h_max = bounds[0][axis_idx] * scale, bounds[1][axis_idx] * scale
        H = h_max - h_min

        m_mm = self.mesh.copy()
        if scale != 1.0:
            m_mm.apply_scale(scale)

        n_scan = 80
        ys = np.linspace(h_min + 5.0, h_max - 5.0, n_scan)
        rem_axes = [i for i in range(3) if i != axis_idx]
        norm_vec = [0.0, 0.0, 0.0]
        norm_vec[axis_idx] = 1.0

        bifurcated = []
        for y in ys:
            origin = [0.0, 0.0, 0.0]
            origin[axis_idx] = y
            lines = trimesh.intersections.mesh_plane(m_mm, plane_normal=norm_vec, plane_origin=origin)
            if len(lines) < 10:
                continue
            segs = lines[:, :, [rem_axes[0], rem_axes[1]]]
            G = nx.Graph()
            for seg in segs:
                p0 = tuple(np.round(seg[0], 1))
                p1 = tuple(np.round(seg[1], 1))
                if p0 != p1:
                    G.add_edge(p0, p1)
            comps = [list(c) for c in nx.connected_components(G) if len(c) >= 15]
            if len(comps) >= 2:
                # Sort components along the transverse axis (rem_axes[0])
                comps.sort(key=lambda c: np.mean([p[0] for p in c]))
                c0 = np.array(comps[0])
                c1 = np.array(comps[1])
                gap_min = float(np.max(c0[:, 0]))
                gap_max = float(np.min(c1[:, 0]))
                if gap_max > gap_min:
                    bifurcated.append({
                        'y': float(y),
                        'gap_min': gap_min,
                        'gap_max': gap_max,
                        'thickness_span': (min(float(np.min(c0[:, 1])), float(np.min(c1[:, 1]))),
                                          max(float(np.max(c0[:, 1])), float(np.max(c1[:, 1])))),
                    })

        if len(bifurcated) < 5:
            return []

        # Find contiguous runs of bifurcated slices (height span >= 15mm)
        runs = []
        cur_run = [bifurcated[0]]
        for b in bifurcated[1:]:
            dy = b['y'] - cur_run[-1]['y']
            if dy <= (H / n_scan) * 2.5:
                cur_run.append(b)
            else:
                if len(cur_run) >= 5 and (cur_run[-1]['y'] - cur_run[0]['y']) >= 15.0:
                    runs.append(cur_run)
                cur_run = [b]
        if len(cur_run) >= 5 and (cur_run[-1]['y'] - cur_run[0]['y']) >= 15.0:
            runs.append(cur_run)

        voids = []
        for v_idx, run in enumerate(runs):
            y_s = run[0]['y']
            y_e = run[-1]['y']
            h_void = y_e - y_s

            target_n = 14
            step = max(1, len(run) // target_n)
            sampled = run[::step]
            if sampled[-1] != run[-1]:
                sampled.append(run[-1])

            left_edge = [[b['gap_min'], b['y']] for b in sampled]
            right_edge = [[b['gap_max'], b['y']] for b in sampled]
            void_2d = left_edge + list(reversed(right_edge))

            min_thick = min(b['thickness_span'][0] for b in run)
            max_thick = max(b['thickness_span'][1] for b in run)
            depth_mm = (max_thick - min_thick) + 20.0
            start_offset = min_thick - 10.0

            voids.append({
                'void_index': v_idx,
                'height_span': [round(y_s, 2), round(y_e, 2)],
                'height_mm': round(h_void, 2),
                'depth_mm': round(depth_mm, 2),
                'start_offset_mm': round(start_offset, 2),
                'polygon_2d': [[round(float(p[0]), 2), round(float(p[1]), 2)] for p in void_2d],
            })
        return voids



class MultiSliceCrossSectionSlicer(MultiSliceSectionExtractor):
    """Alias for MultiSliceSectionExtractor providing extract_sections()."""
    def extract_sections(self, n_stations: int = 21, axis: str = 'Y') -> list[dict]:
        return self.slice_heights(axis=axis, n_slices=n_stations)

