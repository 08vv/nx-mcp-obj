"""
region_decomposer.py
====================
Per-Region Shape Classification & Axial Decomposition Engine.

Analyzes cross-sections along the primary axis to segment geometry into discrete
functional regions, classifying each independently:
- PURE_REVOLVE: Circular cross-sections without significant surface variation.
- REVOLVE_WITH_PATTERNED_FEATURE: Circular cross-sections with periodic flutes/grooves.
- PRISMATIC_EXTRUSION: Polygonal/rectangular cross-sections invariant along axis.
- LOFTED_TRANSITION: Continuous cross-sections morphing between shapes.
- NON_AXISYMMETRIC / FREEFORM_NURBS: Irregular, multi-component, or asymmetric geometry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import trimesh

try:
    from .feature_schema import RegionIntent, RegionShapeType
    from .obj_analyzer import ComponentInfo, OBJAnalysis
except ImportError:
    from feature_schema import RegionIntent, RegionShapeType
    from obj_analyzer import ComponentInfo, OBJAnalysis


@dataclass
class SliceMetric:
    """Geometric metric for one axial station slice."""
    y: float
    center: Tuple[float, float]
    mean_radius: float
    aspect_ratio: float           # dx / dz
    roundness_deviation: float    # std(r) / mean(r)
    is_circular: bool
    point_count: int


@dataclass
class AxialRegion:
    """A segmented axial zone with independent shape classification."""
    region_id: str
    y_min_mm: float
    y_max_mm: float
    height_mm: float
    shape_type: str               # RegionShapeType value
    confidence: float
    mean_radius_mm: float
    aspect_ratio: float
    slice_count: int
    subfeatures: List[Dict[str, Any]] = field(default_factory=list)
    r_min_mm: float = 0.0
    r_max_mm: float = 0.0
    is_taper: bool = False

    def to_region_intent(self) -> RegionIntent:
        # Route by zone type:
        # constant radius -> cylinder
        # linear taper -> cone
        # grooves/dome -> revolve
        # rounded-rect -> extrude
        # non-axisymmetric -> through_curves
        r_mean = max(self.mean_radius_mm, 1e-3)
        r_span = abs(self.r_max_mm - self.r_min_mm)
        r_rel_var = r_span / r_mean if r_mean > 0 else 0.0

        if self.shape_type in (RegionShapeType.PURE_REVOLVE.value, RegionShapeType.REVOLVE_WITH_PATTERNED_FEATURE.value):
            if r_rel_var < 0.08:
                tool = "create_cylinder"
            elif self.is_taper:
                tool = "create_cone"
            else:
                tool = "revolve_from_sketch"
        elif self.shape_type == RegionShapeType.PRISMATIC_EXTRUSION.value:
            tool = "extrude_from_sketch"
        elif self.shape_type in (RegionShapeType.LOFTED_TRANSITION.value, RegionShapeType.NON_AXISYMMETRIC.value):
            if 0.85 <= self.aspect_ratio <= 1.18:
                tool = "create_cone" if self.is_taper else "revolve_from_sketch"
            elif abs(self.aspect_ratio - 1.0) > 0.30 and r_rel_var < 0.15:
                tool = "extrude_from_sketch"
            else:
                tool = "through_curves"
        else:
            tool = "create_cylinder"

        return RegionIntent(
            region_id=self.region_id,
            axial_range_mm=[round(self.y_min_mm, 2), round(self.y_max_mm, 2)],
            shape_type=self.shape_type,
            confidence=round(self.confidence, 3),
            base_parameters={
                "mean_radius_mm": round(self.mean_radius_mm, 2),
                "r_min_mm": round(self.r_min_mm, 2),
                "r_max_mm": round(self.r_max_mm, 2),
                "aspect_ratio": round(self.aspect_ratio, 2),
                "height_mm": round(self.height_mm, 2),
                "is_taper": self.is_taper,
            },
            subfeatures=[],
            recommended_cad_tool=tool,
        )


class PerRegionShapeClassifier:
    """
    Performs axial segmentation and independent per-region shape classification.
    """

    def __init__(self, mesh: trimesh.Trimesh, n_slices: int = 40):
        self.mesh = mesh
        self.n_slices = max(10, n_slices)

    def analyze_slices(self) -> List[SliceMetric]:
        """Scans axial stations and computes local roundness & aspect metrics."""
        scale = 100.0 if np.max(np.abs(self.mesh.bounds)) < 5.0 else 1.0
        bounds = self.mesh.bounds * scale
        y_min, y_max = float(bounds[0][1]), float(bounds[1][1])
        total_h = y_max - y_min

        if total_h < 1.0:
            return []

        y_stations = np.linspace(y_min + 0.01 * total_h, y_max - 0.01 * total_h, self.n_slices)
        half_h = total_h / (self.n_slices * 1.5)

        metrics: List[SliceMetric] = []
        v_scaled = self.mesh.vertices * scale

        for y_val in y_stations:
            pts = None
            # Fast path: try cross-section intersection
            try:
                sec = self.mesh.section(plane_origin=[0.0, y_val / scale, 0.0], plane_normal=[0.0, 1.0, 0.0])
                if sec and hasattr(sec, "vertices") and len(sec.vertices) >= 4:
                    pts = sec.vertices * scale
            except Exception:
                pts = None

            # Fallback to vertex band if section didn't intersect
            if pts is None or len(pts) < 4:
                mask = np.abs(v_scaled[:, 1] - y_val) <= half_h
                if np.any(mask):
                    pts = v_scaled[mask]

            if pts is None or len(pts) < 4:
                continue

            cx = float(np.mean(pts[:, 0]))
            cz = float(np.mean(pts[:, 2]))
            radii = np.hypot(pts[:, 0] - cx, pts[:, 2] - cz)
            mean_r = float(np.mean(radii))
            std_r = float(np.std(radii))
            round_dev = std_r / max(mean_r, 1e-3)

            span_x = float(np.max(pts[:, 0]) - np.min(pts[:, 0]))
            span_z = float(np.max(pts[:, 2]) - np.min(pts[:, 2]))
            aspect = span_x / max(span_z, 1e-3)

            is_circ = bool(round_dev < 0.12 and 0.80 <= aspect <= 1.25)

            metrics.append(SliceMetric(
                y=float(y_val),
                center=(cx, cz),
                mean_radius=mean_r,
                aspect_ratio=aspect,
                roundness_deviation=round_dev,
                is_circular=is_circ,
                point_count=len(pts),
            ))

        return metrics

    def segment_regions(self, has_patterned_feature: bool = False) -> List[AxialRegion]:
        """
        Groups axial stations into distinct regions based on cross-section properties.
        """
        metrics = self.analyze_slices()
        if not metrics:
            return []

        regions: List[AxialRegion] = []
        cur_slices: List[SliceMetric] = [metrics[0]]

        for m in metrics[1:]:
            prev = cur_slices[-1]
            # Check if shape family changed (circular vs non-circular or sudden aspect shift)
            shape_shifted = (m.is_circular != prev.is_circular) or (abs(m.aspect_ratio - prev.aspect_ratio) > 0.45)

            if shape_shifted and len(cur_slices) >= 3:
                regions.append(self._build_region(len(regions), cur_slices, has_patterned_feature))
                cur_slices = [m]
            else:
                cur_slices.append(m)

        if cur_slices:
            regions.append(self._build_region(len(regions), cur_slices, has_patterned_feature))

        # Merge tiny adjacent regions (< 5% of height) to prevent over-segmentation
        merged: List[AxialRegion] = []
        bounds = self.mesh.bounds * 100.0
        total_h = float(bounds[1][1] - bounds[0][1])
        min_region_h = max(total_h * 0.06, 5.0)

        for reg in regions:
            if not merged:
                merged.append(reg)
            elif reg.height_mm < min_region_h and reg.shape_type == merged[-1].shape_type:
                # Merge into previous region
                prev_reg = merged[-1]
                prev_reg.y_max_mm = reg.y_max_mm
                prev_reg.height_mm = prev_reg.y_max_mm - prev_reg.y_min_mm
                prev_reg.slice_count += reg.slice_count
            else:
                merged.append(reg)

        return merged

    def _build_region(
        self,
        index: int,
        slices: List[SliceMetric],
        has_patterned_feature: bool
    ) -> AxialRegion:
        y_min = slices[0].y
        y_max = slices[-1].y
        height = max(y_max - y_min, 1e-3)
        mean_r = float(np.mean([s.mean_radius for s in slices]))
        mean_aspect = float(np.mean([s.aspect_ratio for s in slices]))
        circ_fraction = float(np.mean([1.0 if s.is_circular else 0.0 for s in slices]))

        if circ_fraction >= 0.70:
            if has_patterned_feature:
                shape_type = RegionShapeType.REVOLVE_WITH_PATTERNED_FEATURE.value
            else:
                shape_type = RegionShapeType.PURE_REVOLVE.value
            conf = min(0.98, max(0.60, 0.50 + 0.45 * circ_fraction))
        elif mean_aspect > 1.35 or mean_aspect < 0.74:
            # Check if aspect ratio is stable along length (prismatic) or changing (lofted)
            aspect_std = float(np.std([s.aspect_ratio for s in slices]))
            if aspect_std < 0.15:
                shape_type = RegionShapeType.PRISMATIC_EXTRUSION.value
                conf = 0.85
            else:
                shape_type = RegionShapeType.LOFTED_TRANSITION.value
                conf = 0.80
        else:
            shape_type = RegionShapeType.LOFTED_TRANSITION.value
            conf = 0.75

        r_vals = [s.mean_radius for s in slices]
        r_min = float(min(r_vals)) if r_vals else mean_r
        r_max = float(max(r_vals)) if r_vals else mean_r
        is_taper = False
        if len(r_vals) >= 3:
            diffs = np.diff(r_vals)
            if np.all(diffs >= -0.15) or np.all(diffs <= 0.15):
                if (r_max - r_min) > 0.08 * max(mean_r, 1e-3):
                    is_taper = True

        return AxialRegion(
            region_id=f"region_{index}_{shape_type.lower()}",
            y_min_mm=y_min,
            y_max_mm=y_max,
            height_mm=height,
            shape_type=shape_type,
            confidence=round(conf, 3),
            mean_radius_mm=round(mean_r, 2),
            aspect_ratio=round(mean_aspect, 2),
            slice_count=len(slices),
            r_min_mm=round(r_min, 2),
            r_max_mm=round(r_max, 2),
            is_taper=is_taper,
        )


# ---------------------------------------------------------------------------
# Preserved Legacy RegionDecomposer for Backward Compatibility
# ---------------------------------------------------------------------------

@dataclass
class UpperNeckRegionGeometry:
    has_upper_region: bool
    y_min_mm: float
    y_max_mm: float
    height_mm: float
    stations: List[dict] = field(default_factory=list)


@dataclass
class RegionDecomposition:
    main_body_height_range: Tuple[float, float]
    upper_neck_region: Optional[UpperNeckRegionGeometry] = None
    separate_components: List[ComponentInfo] = field(default_factory=list)


class RegionDecomposer:
    """Decomposes mesh into main body vs upper neck region vs separate components."""

    def __init__(self, mesh: trimesh.Trimesh, analysis: OBJAnalysis):
        self.mesh = mesh
        self.analysis = analysis

    def extract_upper_neck_stations(
        self, y_body_top: float, st_top_base: dict, st_prev_base: dict = None, n_stations: int = 6
    ) -> list[dict]:
        v = self.mesh.vertices * 100.0
        y_max = float(self.analysis.bounds_mm[1][1])
        if (y_max - y_body_top) < 4.0:
            return []

        pts_base = np.array(st_top_base['points_2d'])
        cx_base, cz_base = st_top_base['center'][0], st_top_base['center'][1]
        rx_base = (np.max(pts_base[:, 0]) - np.min(pts_base[:, 0])) / 2.0
        rz_base = (np.max(pts_base[:, 1]) - np.min(pts_base[:, 1])) / 2.0

        if st_prev_base:
            pts_prev = np.array(st_prev_base['points_2d'])
            rx_prev = (np.max(pts_prev[:, 0]) - np.min(pts_prev[:, 0])) / 2.0
            rz_prev = (np.max(pts_prev[:, 1]) - np.min(pts_prev[:, 1])) / 2.0
            dy_base = max(st_top_base['y'] - st_prev_base['y'], 1e-3)
            drx_top = (rx_base - rx_prev) / dy_base
            drz_top = (rz_base - rz_prev) / dy_base
        else:
            drx_top, drz_top = -0.3, 0.0

        up_mask = v[:, 1] >= (y_max - 3.0)
        up_v = v[up_mask] if np.any(up_mask) else v
        rx_target = float((np.max(up_v[:, 0]) - np.min(up_v[:, 0])) / 2.0)
        rz_target = float((np.max(up_v[:, 2]) - np.min(up_v[:, 2])) / 2.0)

        ratio_x = rx_target / max(rx_base, 1e-6)
        ratio_z = rz_target / max(rz_base, 1e-6)
        if ratio_x >= 0.85 and ratio_z >= 0.85:
            return []

        y_stations = np.linspace(y_body_top + 1.0, y_max - 0.5, n_stations)
        upper_sections = []

        for idx_st, y_val in enumerate(y_stations):
            t = (y_val - y_body_top) / max(y_max - 0.5 - y_body_top, 1e-3)
            rx_hermite = rx_base + drx_top * (y_val - y_body_top) * (1.0 - t)**2 + (rx_target - rx_base) * t**2
            rz_hermite = rz_base + drz_top * (y_val - y_body_top) * (1.0 - t)**2 + (rz_target - rz_base) * t**2
            rx = min(rx_hermite, rx_base + drx_top * (y_val - y_body_top))
            rz = min(rz_hermite, rz_base + drz_top * (y_val - y_body_top))

            scale_x = rx / max(rx_base, 1e-6)
            scale_z = rz / max(rz_base, 1e-6)

            pts_2d = []
            for p in pts_base:
                px = cx_base + (p[0] - cx_base) * scale_x
                pz = cz_base + (p[1] - cz_base) * scale_z
                pts_2d.append([px, pz])

            upper_sections.append({
                "y": float(y_val),
                "center": [cx_base, cz_base],
                "rx": max(rx, 1.0),
                "rz": max(rz, 1.0),
                "points_2d": pts_2d
            })

        return upper_sections

    def decompose(self, y_body_top: float, st_top_base: dict, st_prev_base: dict = None) -> RegionDecomposition:
        y_min = float(self.analysis.bounds_mm[0][1])
        main_body_range = (y_min, y_body_top)

        upper_stations = self.extract_upper_neck_stations(y_body_top, st_top_base, st_prev_base, n_stations=6)
        upper_geom = None

        if upper_stations:
            upper_geom = UpperNeckRegionGeometry(
                has_upper_region=True,
                y_min_mm=float(upper_stations[0]["y"]),
                y_max_mm=float(upper_stations[-1]["y"]),
                height_mm=float(upper_stations[-1]["y"] - upper_stations[0]["y"]),
                stations=upper_stations
            )

        separate_comps = [c for c in self.analysis.components if not c.is_main_body]

        return RegionDecomposition(
            main_body_height_range=main_body_range,
            upper_neck_region=upper_geom,
            separate_components=separate_comps
        )
