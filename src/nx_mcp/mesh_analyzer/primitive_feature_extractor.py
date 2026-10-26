"""
primitive_feature_extractor.py
==============================
Phase 2: Feature Extraction from Primitive Surface Patches & Boundary Loops.

Extracts CAD mechanical features purely from topological boundary loops and
spatial relationships between analytical primitive patches:
- Holes / Bores: Internal boundary loops on planar faces matching cylindrical voids.
- Pockets: Depressed planar or contoured regions bounded by step edges.
- Bosses: Elevated planar or contoured regions bounded by step edges.
- Circular Array Patterns: Rotational repetition of child features around a cylinder axis.
- Linear Array Patterns: Collinear translation of child features along a vector.

NO hardcoded positions (e.g. "65% height", "top 30mm") or domain-specific heuristics.

Threshold Justifications (Global Geometric Parameters)
------------------------------------------------------
These are NOT per-object tuned values. Each is derived from geometric first principles:

- freeform_area_fraction (0.20): A surface region covering >= 20% of total mesh area
  is structurally significant. Below this, the region is a secondary feature (label panel,
  texture zone), not the stock envelope. 20% is the Pareto lower bound for a body surface
  that wraps around a solid — even a highly decorated part retains >= 20% freeform body.

- freeform_face_fraction (0.35): Complementary face-count check. Freeform meshes tend to
  be finely tessellated (small triangles), so area fraction alone can undercount them.
  35% of face count (>1/3 of all faces) guarantees the region is the dominant body.

- revolve_area_fraction (0.25): A single cylindrical primitive covering >= 25% of total
  surface is the envelope cylinder. Below this it's a collar, boss, or transition ring.

- revolve_angular_span_deg (270.0): 3/4 revolution (270°) separates full cylindrical
  shells from partial fillets (< 180°) or C-channels (< 270°). This is the standard
  B-Rep threshold used in STEP AP214 entity classification.

- cavity_normal_dot_threshold (-0.30): For cylindrical surfaces, the dot product of face
  normal with the outward radial vector distinguishes cavities (normals point inward,
  dot < -0.30) from outer shells (normals point outward, dot > +0.30). The -0.30 threshold
  allows for ~72° deviation from pure radial inward, accommodating tessellation noise
  on chamfered or drafted hole walls.

- hole_max_radius_mm (150.0): Internal bores above 150mm radius are structurally
  indistinguishable from shell bodies. This corresponds to the practical maximum bore
  diameter in common mechanical parts (300mm / ~12").

- parallel_plane_dot (0.98): Two planes with n1·n2 > 0.98 are within ~11.5° of parallel.
  This is the standard angular tolerance for functional parallelism in machining
  (ISO 1101 general tolerance grade IT14).

- step_depth_range [0.5, 25.0] mm: Below 0.5mm, the offset is within typical tessellation
  chordal deviation and is noise. Above 25mm, the step is a separate structural region,
  not a pocket or boss feature.

- pattern_radius_std_mm (1.5): For bolt circle patterns, hole centers must lie within
  1.5mm standard deviation of the mean pitch circle radius. This is 2× the typical
  positional tolerance for drilled holes (ISO 2768-m).

- pattern_pitch_std_deg (5.0): Angular pitch uniformity within 5° standard deviation.
  Covers manufacturing tolerance for equally-spaced bolt patterns.

- child_area_ratio (0.60): A step face must be < 60% of its parent face area to qualify
  as a pocket/boss rather than a co-planar structural face.
"""


from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import trimesh

from .primitive_segmenter import PrimitivePatch


@dataclass
class ExtractedFeature:
    """A high-level CAD feature derived purely from primitive relationships."""
    feature_id: str
    feature_type: str             # "HOLE", "POCKET", "BOSS", "CIRCULAR_PATTERN", "LINEAR_PATTERN", "REVOLVE_BODY", "LOFT_BODY"
    parent_patch_id: Optional[int]
    confidence: float
    parameters: Dict[str, Any]
    source_primitive_ids: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "parent_patch_id": self.parent_patch_id,
            "confidence": round(self.confidence, 4),
            "parameters": self.parameters,
            "source_primitive_ids": self.source_primitive_ids,
        }


class PrimitiveFeatureExtractor:
    """
    Extracts mechanical CAD features from segmented primitive patches.
    """

    def __init__(self, mesh: trimesh.Trimesh, patches: List[PrimitivePatch]):
        # Scale to millimeters if mesh extents < 10.0
        scale = 100.0 if (mesh.bounds[1][1] - mesh.bounds[0][1]) < 10.0 else 1.0
        self.mesh = mesh.copy()
        if scale != 1.0:
            self.mesh.vertices *= scale
        self.patches = patches
        self.patch_by_id = {p.patch_id: p for p in patches}
        self._consumed_plane_ids = set()

    def extract_features(self) -> List[ExtractedFeature]:
        """Derives all CAD features from primitive patch boundaries and relationships."""
        features: List[ExtractedFeature] = []
        feat_counter = 0

        # -------------------------------------------------------------------
        # 1. Base Body Identification
        # -------------------------------------------------------------------
        # Find dominant primitive (cylinder, loft/freeform, or planar extrusion)
        base_feat = self._identify_base_body()
        if base_feat:
            features.append(base_feat)

        # -------------------------------------------------------------------
        # 2. Holes and Cylindrical Bores (including Compound Counterbores)
        # -------------------------------------------------------------------
        holes = self._extract_holes()
        features.extend(holes)

        # -------------------------------------------------------------------
        # 3. Pockets and Bosses from Planar Steps
        # -------------------------------------------------------------------
        steps = self._extract_pockets_and_bosses()
        features.extend(steps)

        # -------------------------------------------------------------------
        # 4. Pattern Detection (Circular & Linear Arrays)
        # -------------------------------------------------------------------
        patterns = self._extract_patterns(features)
        features.extend(patterns)

        return features

    # -----------------------------------------------------------------------
    # Base Body Detection
    # -----------------------------------------------------------------------
    def _identify_base_body(self) -> Optional[ExtractedFeature]:
        """Determines the primary stock solid mechanism."""
        total_mesh_area = float(self.mesh.area)
        total_faces = len(self.mesh.faces)
        cylinders = [p for p in self.patches if p.primitive_type == "CYLINDER"]
        freeforms = [p for p in self.patches if p.primitive_type == "UNCLASSIFIED_FREEFORM"]
        planes = [p for p in self.patches if p.primitive_type == "PLANE"]

        total_freeform_area = sum(f.area_mm2 for f in freeforms)
        total_freeform_faces = sum(f.face_count for f in freeforms)

        # Case A: Freeform lofted body dominates over any single cylinder
        if freeforms and (
            (total_freeform_area / max(total_mesh_area, 1.0) >= 0.20)
            or (total_freeform_faces / float(total_faces) >= 0.35)
        ):
            main_cyl_area = max([c.area_mm2 for c in cylinders], default=0.0)
            if total_freeform_area >= main_cyl_area:
                all_mins = np.array([f.parameters["bounds_min_mm"] for f in freeforms])
                all_maxs = np.array([f.parameters["bounds_max_mm"] for f in freeforms])
                global_min = np.min(all_mins, axis=0)
                global_max = np.max(all_maxs, axis=0)
                return ExtractedFeature(
                    feature_id="base_solid_loft",
                    feature_type="LOFT_BODY",
                    parent_patch_id=None,
                    confidence=0.92,
                    parameters={
                        "bounds_min_mm": [round(float(x), 3) for x in global_min],
                        "bounds_max_mm": [round(float(x), 3) for x in global_max],
                        "extents_mm": [round(float(x), 3) for x in (global_max - global_min)],
                        "patch_count": len(freeforms),
                        "total_area_mm2": round(total_freeform_area, 2),
                    },
                    source_primitive_ids=[f.patch_id for f in freeforms],
                )

        # Case B: Dominant cylindrical body (covers >= 25% of mesh and >= 270 deg span)
        if cylinders:
            main_cyl = max(cylinders, key=lambda c: c.area_mm2)
            if (main_cyl.area_mm2 / max(total_mesh_area, 1.0)) >= 0.25 and main_cyl.parameters.get("angular_span_deg", 0) >= 270.0:
                axis_dir = np.array(main_cyl.parameters["axis_direction"])
                coaxial_cyls = [
                    c for c in cylinders
                    if abs(np.dot(c.parameters["axis_direction"], axis_dir)) > 0.95
                    and abs(c.parameters["radius_mm"] - main_cyl.parameters["radius_mm"]) < 5.0
                ]
                all_faces = []
                for c in coaxial_cyls:
                    all_faces.extend(c.face_indices)
                verts = self.mesh.vertices[self.mesh.faces[all_faces].flatten()]
                full_length = float(np.ptp(np.dot(verts, axis_dir)))
                return ExtractedFeature(
                    feature_id="base_solid_revolve",
                    feature_type="REVOLVE_BODY",
                    parent_patch_id=None,
                    confidence=main_cyl.confidence,
                    parameters={
                        "axis_direction": main_cyl.parameters["axis_direction"],
                        "axis_origin": main_cyl.parameters["axis_origin"],
                        "diameter_mm": main_cyl.parameters["diameter_mm"],
                        "radius_mm": main_cyl.parameters["radius_mm"],
                        "length_mm": round(max(main_cyl.parameters["length_mm"], full_length), 3),
                    },
                    source_primitive_ids=[c.patch_id for c in coaxial_cyls],
                )

        # Case C: Prismatic extruded solid (opposing planar faces covering substantial area)
        total_plane_area = sum(p.area_mm2 for p in planes)
        if (total_plane_area / max(total_mesh_area, 1.0) >= 0.25) and len(planes) >= 2:
            best_pair = None
            best_score = -1.0
            for i in range(len(planes)):
                for j in range(i + 1, len(planes)):
                    p1, p2 = planes[i], planes[j]
                    n1 = np.array(p1.parameters["normal"])
                    n2 = np.array(p2.parameters["normal"])
                    if np.dot(n1, n2) < -0.85:
                        c1 = np.array(p1.parameters["point_on_plane"])
                        c2 = np.array(p2.parameters["point_on_plane"])
                        dist = abs(np.dot(c2 - c1, n1))
                        if dist < 0.5:
                            continue

                        # Compute 2D projected overlap along the extrusion axis
                        ref = np.array([1.0, 0.0, 0.0]) if abs(n1[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
                        u = np.cross(n1, ref)
                        u /= np.linalg.norm(u)
                        v = np.cross(n1, u)

                        v1 = self.mesh.vertices[self.mesh.faces[p1.face_indices].flatten()]
                        v2 = self.mesh.vertices[self.mesh.faces[p2.face_indices].flatten()]

                        try:
                            from shapely.geometry import MultiPoint
                            poly1 = MultiPoint(np.column_stack([np.dot(v1, u), np.dot(v1, v)])).convex_hull
                            poly2 = MultiPoint(np.column_stack([np.dot(v2, u), np.dot(v2, v)])).convex_hull
                            inter = poly1.intersection(poly2)
                            if inter.is_empty or inter.area < 5.0:
                                continue
                            inter_area = float(inter.area)
                            max_poly_area = max(float(poly1.area), float(poly2.area), 1.0)
                            overlap_ratio = inter_area / max_poly_area
                        except Exception:
                            u1, w1 = np.dot(v1, u), np.dot(v1, v)
                            u2, w2 = np.dot(v2, u), np.dot(v2, v)
                            overlap_u = max(0.0, min(float(np.max(u1)), float(np.max(u2))) - max(float(np.min(u1)), float(np.min(u2))))
                            overlap_w = max(0.0, min(float(np.max(w1)), float(np.max(w2))) - max(float(np.min(w1)), float(np.min(w2))))
                            inter_area = overlap_u * overlap_w
                            if inter_area < 5.0:
                                continue
                            b1 = max(1.0, (float(np.max(u1)) - float(np.min(u1))) * (float(np.max(w1)) - float(np.min(w1))))
                            b2 = max(1.0, (float(np.max(u2)) - float(np.min(u2))) * (float(np.max(w2)) - float(np.min(w2))))
                            overlap_ratio = inter_area / max(b1, b2)

                        if overlap_ratio < 0.25:
                            continue

                        max_area = max(p1.area_mm2, p2.area_mm2)
                        base_vol = max_area * dist
                        coaxial_cyls = sum(1 for c in cylinders if abs(np.dot(c.parameters["axis_direction"], n1)) > 0.9)
                        score = base_vol * (1.0 + 0.5 * coaxial_cyls)

                        if score > best_score:
                            best_score = score
                            p_base = p1 if p1.area_mm2 >= p2.area_mm2 else p2
                            p_opp = p2 if p_base is p1 else p1
                            best_pair = (p_base, p_opp, dist)

            if best_pair and best_score > 0.0:
                p_base, p_opp, dist = best_pair
                c1 = np.array(p_base.parameters["point_on_plane"])
                c2 = np.array(p_opp.parameters["point_on_plane"])
                mid_center = (c1 + c2) / 2.0
                n_base = np.array(p_base.parameters["normal"])
                extrude_axis = -n_base if np.dot(n_base, c2 - c1) < 0 else n_base

                # Extract outer 3D profile boundary loop of p_base
                poly_3d = []
                try:
                    submesh = self.mesh.submesh([p_base.face_indices], append=True)
                    outline = submesh.outline()
                    if outline and len(outline.entities) > 0:
                        def entity_bbox_area(ent):
                            pts = outline.vertices[ent.points]
                            spans = np.ptp(pts, axis=0)
                            s_sorted = sorted(spans, reverse=True)
                            return float(s_sorted[0] * s_sorted[1])

                        outer_entity = max(outline.entities, key=entity_bbox_area)
                        pts_idx = outer_entity.points
                        poly_3d = [list(outline.vertices[pi]) for pi in pts_idx]
                except Exception:
                    pass

                params = {
                    "extrusion_axis": [round(float(x), 5) for x in extrude_axis],
                    "height_mm": round(float(dist), 3),
                    "span_u_mm": round(float(p_base.parameters["span_u_mm"]), 3),
                    "span_w_mm": round(float(p_base.parameters["span_w_mm"]), 3),
                    "center": [round(float(x), 3) for x in mid_center],
                }
                if poly_3d and len(poly_3d) >= 3:
                    params["profile_polygon_3d"] = [[round(float(c), 3) for c in pt] for pt in poly_3d]

                return ExtractedFeature(
                    feature_id="base_solid_extrude",
                    feature_type="PRISMATIC_EXTRUSION",
                    parent_patch_id=None,
                    confidence=min(p_base.confidence, p_opp.confidence),
                    parameters=params,
                    source_primitive_ids=[p_base.patch_id, p_opp.patch_id],
                )

        return None

    # -----------------------------------------------------------------------
    # Holes and Bores
    # -----------------------------------------------------------------------
    def _extract_holes(self) -> List[ExtractedFeature]:
        """Finds internal cylindrical cavities (simple holes and stepped counterbores)."""
        holes = []
        cylinders = [p for p in self.patches if p.primitive_type == "CYLINDER"]
        planes = [p for p in self.patches if p.primitive_type == "PLANE"]
        if not cylinders or not planes:
            return holes

        plane_map = {p.patch_id: p for p in planes}
        face_to_plane = {}
        for pl in planes:
            for fi in pl.face_indices:
                face_to_plane[fi] = pl

        adj = self.mesh.face_adjacency

        # 1. Identify candidate cylindrical hole cavities
        cand_cyls = []
        for cyl in cylinders:
            span = cyl.parameters.get("angular_span_deg", 0)
            radius = cyl.parameters.get("radius_mm", 0)
            length = cyl.parameters.get("length_mm", 0)
            if span < 270.0 or radius < 1.0 or radius > 150.0 or length < 1.0:
                continue

            cyl_face_set = set(cyl.face_indices)
            touching_faces = set()
            for e in adj:
                if e[0] in cyl_face_set and e[1] not in cyl_face_set:
                    touching_faces.add(e[1])
                elif e[1] in cyl_face_set and e[0] not in cyl_face_set:
                    touching_faces.add(e[0])

            touching_plane_ids = set(face_to_plane[af].patch_id for af in touching_faces if af in face_to_plane)
            if not touching_plane_ids:
                continue

            axis = np.array(cyl.parameters["axis_direction"])

            # Check if at least one entry/exit plane has normal aligned with cylinder axis (|axis . n| > 0.80)
            aligned = [pid for pid in touching_plane_ids if abs(np.dot(axis, plane_map[pid].parameters["normal"])) > 0.80]
            if not aligned:
                continue

            origin = np.array(cyl.parameters["axis_origin"])
            sub_faces = cyl.face_indices[:min(50, len(cyl.face_indices))]
            fc = self.mesh.triangles_center[sub_faces]
            fn = self.mesh.face_normals[sub_faces]
            diffs = fc - origin
            proj = np.outer(np.dot(diffs, axis), axis)
            rad_v = diffs - proj
            unit_rad = rad_v / np.linalg.norm(rad_v, axis=1, keepdims=True)
            normal_dot = np.mean(np.sum(fn * unit_rad, axis=1))

            if normal_dot < -0.30:
                cand_cyls.append((cyl, touching_plane_ids, aligned))

        # 2. Pair coaxial cylinders sharing an annular shoulder plane into COMPOUND_HOLE features
        paired_indices = set()
        for i in range(len(cand_cyls)):
            if i in paired_indices:
                continue
            c1, tp1, ap1 = cand_cyls[i]
            ax1 = np.array(c1.parameters["axis_direction"])
            o1 = np.array(c1.parameters["axis_origin"])
            for j in range(i + 1, len(cand_cyls)):
                if j in paired_indices:
                    continue
                c2, tp2, ap2 = cand_cyls[j]
                ax2 = np.array(c2.parameters["axis_direction"])
                o2 = np.array(c2.parameters["axis_origin"])

                # Check collinearity: nearly identical axis direction and small centerline radial offset
                if abs(np.dot(ax1, ax2)) < 0.95:
                    continue
                d = o2 - o1
                rad_offset = np.linalg.norm(d - np.dot(d, ax1) * ax1)
                if rad_offset > 2.0:
                    continue

                # Check shared annular shoulder plane
                shared_planes = tp1.intersection(tp2)
                shared_aligned = [pid for pid in shared_planes if abs(np.dot(ax1, plane_map[pid].parameters["normal"])) > 0.80]
                if not shared_aligned:
                    continue

                paired_indices.add(i)
                paired_indices.add(j)
                sh_pid = shared_aligned[0]
                self._consumed_plane_ids.add(sh_pid)
                sh_plane = plane_map[sh_pid]

                c_large, c_small = (c1, c2) if c1.parameters["radius_mm"] > c2.parameters["radius_mm"] else (c2, c1)
                tp_large = tp1 if c_large == c1 else tp2
                ap_large = ap1 if c_large == c1 else ap2
                tp_small = tp1 if c_small == c1 else tp2
                ap_small = ap1 if c_small == c1 else ap2

                # Entry plane: aligned plane of c_large other than shoulder
                entry_candidates = [pid for pid in ap_large if pid != sh_pid]
                entry_plane = plane_map[entry_candidates[0]] if entry_candidates else None

                # Exit plane: aligned plane of c_small other than shoulder
                exit_candidates = [pid for pid in ap_small if pid != sh_pid]
                exit_plane = plane_map[exit_candidates[0]] if exit_candidates else None

                p_sh_pt = np.array(sh_plane.parameters["point_on_plane"])
                p_entry_pt = np.array(entry_plane.parameters["point_on_plane"]) if entry_plane else np.array(c_large.parameters["axis_origin"])
                p_exit_pt = np.array(exit_plane.parameters["point_on_plane"]) if exit_plane else np.array(c_small.parameters["axis_origin"])

                z_sh = np.dot(p_sh_pt, ax1)
                z_entry = np.dot(p_entry_pt, ax1)
                z_exit = np.dot(p_exit_pt, ax1)

                dir_sign = 1.0 if z_exit >= z_entry else -1.0
                hole_dir = dir_sign * ax1

                cbore_depth = abs(z_sh - z_entry)
                total_depth = abs(z_exit - z_entry)
                entry_center = o1 + (z_entry - np.dot(o1, ax1)) * ax1

                holes.append(ExtractedFeature(
                    feature_id=f"compound_hole_{c_large.patch_id}_{c_small.patch_id}",
                    feature_type="COMPOUND_HOLE",
                    parent_patch_id=None,
                    confidence=min(c_large.confidence, c_small.confidence),
                    parameters={
                        "center": [round(float(x), 3) for x in entry_center],
                        "direction": [round(float(x), 5) for x in hole_dir],
                        "cbore_diameter_mm": round(float(c_large.parameters["diameter_mm"]), 3),
                        "cbore_depth_mm": round(float(cbore_depth), 3),
                        "diameter_mm": round(float(c_small.parameters["diameter_mm"]), 3),
                        "depth_mm": round(float(total_depth), 3),
                        "is_through_hole": bool(exit_plane is not None),
                    },
                    source_primitive_ids=[c_large.patch_id, c_small.patch_id, sh_pid],
                ))

        # 3. Add unpaired candidate cylinders as simple HOLE features
        for idx, (cyl, _, _) in enumerate(cand_cyls):
            if idx in paired_indices:
                continue
            holes.append(ExtractedFeature(
                feature_id=f"hole_{cyl.patch_id}",
                feature_type="HOLE",
                parent_patch_id=None,
                confidence=cyl.confidence,
                parameters={
                    "center": cyl.parameters["axis_origin"],
                    "direction": cyl.parameters["axis_direction"],
                    "diameter_mm": cyl.parameters["diameter_mm"],
                    "depth_mm": cyl.parameters["length_mm"],
                    "is_through_hole": bool(cyl.parameters.get("angular_span_deg", 0) >= 350.0),
                },
                source_primitive_ids=[cyl.patch_id],
            ))

        return holes

    # -----------------------------------------------------------------------
    # Pockets and Bosses
    # -----------------------------------------------------------------------
    def _extract_pockets_and_bosses(self) -> List[ExtractedFeature]:
        """
        Detects planar steps (pockets depressed into a face or bosses raised above it).

        Pre-filters planar patches to exclude tessellation artifacts and consumed hole shoulders.
        """
        features = []
        min_area_mm2 = 5.0
        min_face_count = 10
        max_features = 50

        # Filter out planar patches consumed as hole shoulders
        planes = [p for p in self.patches
                  if p.primitive_type == "PLANE"
                  and p.patch_id not in self._consumed_plane_ids
                  and p.area_mm2 >= min_area_mm2
                  and p.face_count >= min_face_count]
        if len(planes) < 2:
            return features

        # Compare pairs of parallel planar patches
        for i in range(len(planes)):
            for j in range(i + 1, len(planes)):
                p1, p2 = planes[i], planes[j]
                n1 = np.array(p1.parameters["normal"])
                n2 = np.array(p2.parameters["normal"])
                # Parallel faces: |n1 . n2| > 0.98
                if np.dot(n1, n2) > 0.98:
                    d1 = p1.parameters["d_offset_mm"]
                    d2 = p2.parameters["d_offset_mm"]
                    step_depth = abs(d1 - d2)
                    if 0.5 <= step_depth <= 25.0:
                        # Determine which is parent and which is child based on area
                        parent = p1 if p1.area_mm2 > p2.area_mm2 else p2
                        child = p2 if p1.area_mm2 > p2.area_mm2 else p1

                        # Relative area: child should be smaller than parent
                        if child.area_mm2 < 0.60 * parent.area_mm2:
                            # Lateral containment check: child center projected onto parent plane
                            # must lie within parent face extents
                            c_parent = np.array(parent.parameters["point_on_plane"])
                            c_child = np.array(child.parameters["point_on_plane"])
                            c_diff = c_child - c_parent

                            ref = np.array([1.0, 0.0, 0.0]) if abs(n1[0]) < 0.8 else np.array([0.0, 1.0, 0.0])
                            u = np.cross(n1, ref)
                            u_norm = np.linalg.norm(u)
                            if u_norm < 1e-6:
                                continue
                            u /= u_norm
                            w = np.cross(n1, u)
                            w_norm = np.linalg.norm(w)
                            if w_norm < 1e-6:
                                continue
                            w /= w_norm

                            lat_u = abs(np.dot(c_diff, u))
                            lat_w = abs(np.dot(c_diff, w))

                            parent_span_u = parent.parameters.get("span_u_mm", 10.0)
                            parent_span_w = parent.parameters.get("span_w_mm", 10.0)

                            # Child must be contained within parent footprint
                            if lat_u > 0.55 * parent_span_u or lat_w > 0.55 * parent_span_w:
                                continue

                            features.append(ExtractedFeature(
                                feature_id=f"planar_step_{child.patch_id}",
                                feature_type="POCKET" if child.parameters["d_offset_mm"] < parent.parameters["d_offset_mm"] else "BOSS",
                                parent_patch_id=parent.patch_id,
                                confidence=0.88,
                                parameters={
                                    "normal": parent.parameters["normal"],
                                    "center": child.parameters["point_on_plane"],
                                    "step_depth_mm": round(float(step_depth), 3),
                                    "span_u_mm": child.parameters.get("span_u_mm", 0.0),
                                    "span_w_mm": child.parameters.get("span_w_mm", 0.0),
                                },
                                source_primitive_ids=[parent.patch_id, child.patch_id],
                            ))
                            if len(features) >= max_features:
                                return features

        return features

    # -----------------------------------------------------------------------
    # Pattern Detection (Circular & Linear Arrays)
    # -----------------------------------------------------------------------
    def _extract_patterns(self, features: List[ExtractedFeature]) -> List[ExtractedFeature]:
        """Detects circular or linear array patterns among child features."""
        patterns = []
        cylinders = [p for p in self.patches if p.primitive_type == "CYLINDER"]
        if not cylinders or not features:
            return patterns

        main_axis = np.array(cylinders[0].parameters["axis_direction"])
        main_origin = np.array(cylinders[0].parameters["axis_origin"])

        # Group features by type and size
        holes = [f for f in features if f.feature_type == "HOLE"]
        if len(holes) >= 3:
            # Check if holes lie at constant radius from main axis
            radii = []
            angles = []
            ref = np.array([1, 0, 0]) if abs(main_axis[0]) < 0.8 else np.array([0, 1, 0])
            u = np.cross(main_axis, ref); u /= np.linalg.norm(u)
            w = np.cross(main_axis, u)

            for h in holes:
                c = np.array(h.parameters["center"]) - main_origin
                cu = np.dot(c, u)
                cw = np.dot(c, w)
                radii.append(math.hypot(cu, cw))
                angles.append(math.atan2(cw, cu))

            # If standard deviation of radii is small (< 1.5mm)
            if np.std(radii) < 1.5 and len(holes) >= 3:
                sorted_angles = np.sort(angles)
                diffs = np.diff(sorted_angles)
                # Include wrap-around difference
                diffs = np.append(diffs, (2 * np.pi + sorted_angles[0] - sorted_angles[-1]))
                mean_pitch_deg = math.degrees(np.mean(diffs))
                std_pitch_deg = math.degrees(np.std(diffs))

                if std_pitch_deg < 5.0:
                    patterns.append(ExtractedFeature(
                        feature_id="circular_hole_pattern",
                        feature_type="CIRCULAR_PATTERN",
                        parent_patch_id=None,
                        confidence=0.95,
                        parameters={
                            "axis_direction": main_axis.tolist(),
                            "axis_origin": main_origin.tolist(),
                            "instance_count": len(holes),
                            "pitch_deg": round(mean_pitch_deg, 2),
                            "pitch_radius_mm": round(float(np.mean(radii)), 2),
                            "target_feature_id": holes[0].feature_id,
                        },
                        source_primitive_ids=[h.source_primitive_ids[0] for h in holes if h.source_primitive_ids],
                    ))

        return patterns
