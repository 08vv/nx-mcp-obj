"""
mesh_analyzer
=============
Advanced Geometric & Topological Mesh Analysis Package for Siemens NX MCP.

Provides multi-layer geometric intelligence and Reconstruction Intent IR for
reverse-engineering 3D OBJ meshes into fully parametric Siemens NX CAD models:
- Layer A: Mesh ingestion, topological genus, PCA coordinate alignment, connected components.
- Layer B: Revolve silhouette extraction (curvature-adaptive), multi-slice cross-sections,
  per-region shape classification.
- Layer C: Base loft reconstruction, residual deviation mapping, directional periodic feature
  detection (longitudinal ribs vs circumferential grooves vs knurl), confidence gating.
- Layer D: Clean Reconstruction Intent IR and post-build surface residual validation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import trimesh

from .feature_schema import (
    CapRibFeature,
    FeatureIntent,
    FeatureOrientation,
    FeaturePatternType,
    HandleFeature,
    PeriodicRibFeature,
    ReconstructionIntent,
    RecessedPanelFeature,
    RegionIntent,
    RegionShapeType,
)
# FeatureSegmenter lazy-imported to save memory
from .mesh_analyzer import MeshCurvatureAnalyzer
from .obj_analyzer import ComponentInfo, OBJAnalysis, OBJAnalyzer
from .parser import MeshIngestionEngine
from .pca_align import PCAMeshAligner
from .region_decomposer import (
    AxialRegion,
    PerRegionShapeClassifier,
    RegionDecomposer,
    RegionDecomposition,
    UpperNeckRegionGeometry,
)
from .residual_analyzer import (
    ResidualAnalyzer,
    ResidualMap,
    ResidualVertex,
    SurfaceResidualValidator,
)
from .rib_detector import PeriodicFeatureDetector, SideRibDetector
from .section_extractor import MultiSliceSectionExtractor, PureRevolveExtractor
from .surface_patch_extractor import SurfacePatchExtractor
from .topology_detector import TopologyDetector
from .v_feature_detector import VFeatureDetector

__all__ = [
    "MeshIngestionEngine",
    "PCAMeshAligner",
    "OBJAnalyzer",
    "OBJAnalysis",
    "ComponentInfo",
    "TopologyDetector",
    "PureRevolveExtractor",
    "MultiSliceSectionExtractor",
    "ResidualAnalyzer",
    "ResidualMap",
    "ResidualVertex",
    "SurfaceResidualValidator",
    "PeriodicFeatureDetector",
    "SideRibDetector",
    "VFeatureDetector",
    "MeshCurvatureAnalyzer",
    "SurfacePatchExtractor",
    "FeatureSegmenter",
    "PerRegionShapeClassifier",
    "AxialRegion",
    "RegionDecomposer",
    "RegionDecomposition",
    "UpperNeckRegionGeometry",
    "CapRibFeature",
    "RecessedPanelFeature",
    "HandleFeature",
    "PeriodicRibFeature",
    "FeatureOrientation",
    "FeaturePatternType",
    "RegionShapeType",
    "FeatureIntent",
    "RegionIntent",
    "ReconstructionIntent",
    "ComprehensiveMeshAnalyzer",
    "analyze_mesh",
]


class ComprehensiveMeshAnalyzer:
    """
    Unified orchestrator for end-to-end geometric analysis of 3D OBJ meshes.
    Combines topology, PCA alignment, section slicing, residual deviation mapping,
    feature classification with orientation & confidence, and Reconstruction Intent IR.
    """

    def __init__(
        self,
        mesh_source: Union[str, Path, trimesh.Trimesh],
        num_slices: int = 21,
        detect_residuals: bool = True,
        adaptive_profile: bool = True,
    ):
        self.file_path: Optional[Path] = None
        if isinstance(mesh_source, (str, Path)):
            self.file_path = Path(mesh_source).resolve()
            ingestion = MeshIngestionEngine(self.file_path)
            self.raw_mesh = ingestion.raw_mesh
            self.mesh = ingestion.repair()
            self.mesh_info = ingestion.get_mesh_info()
        elif isinstance(mesh_source, trimesh.Trimesh):
            self.raw_mesh = mesh_source
            self.mesh = mesh_source.copy()
            self.mesh.merge_vertices()
            self.mesh.fix_normals()
            bounds = self.mesh.bounds
            dims = bounds[1] - bounds[0]
            self.mesh_info = {
                "file_path": "<in-memory>",
                "vertex_count": len(self.mesh.vertices),
                "face_count": len(self.mesh.faces),
                "is_watertight": bool(self.mesh.is_watertight),
                "bounds_min": bounds[0].tolist(),
                "bounds_max": bounds[1].tolist(),
                "dimensions": dims.tolist(),
            }
        else:
            raise TypeError(f"Unsupported mesh source: {type(mesh_source)}")

        self.num_slices = max(5, num_slices)
        self.detect_residuals = detect_residuals
        self.adaptive_profile = adaptive_profile

    def run(self) -> Dict[str, Any]:
        """Runs the complete analysis pipeline and returns structured CAD synthesis data."""
        # 1. Topological Analysis (Genus & Handle Detection)
        topo_detector = TopologyDetector(self.mesh)
        topology_res = topo_detector.analyze_topology()

        # 2. PCA Coordinate Alignment
        aligner = PCAMeshAligner(self.mesh)
        aligned_mesh, transform_matrix = aligner.align()
        alignment_info = aligner.get_alignment_info()

        # 3. Geometric & Component Analysis
        obj_analyzer = OBJAnalyzer(aligned_mesh)
        obj_analysis = obj_analyzer.analyze()

        bounds_mm = obj_analysis.bounds_mm
        dims_mm = [
            float(bounds_mm[1][0] - bounds_mm[0][0]),
            float(bounds_mm[1][1] - bounds_mm[0][1]),
            float(bounds_mm[1][2] - bounds_mm[0][2]),
        ]
        centroid_mm = [float(c) for c in obj_analysis.centroid_mm]

        # 4. Curvature-Adaptive Silhouette Profile & Cross-Section Extraction
        sections = []
        revolve_profile = None

        aspect_xz = abs(dims_mm[0] - dims_mm[2]) / max(dims_mm[0], dims_mm[2], 1e-6)
        if alignment_info.get("is_axisymmetric") or aspect_xz < 0.25:
            try:
                rev_extractor = PureRevolveExtractor(aligned_mesh)
                revolve_profile = rev_extractor.extract_silhouette_profile(
                    n_samples=max(60, self.num_slices * 3),
                    adaptive=self.adaptive_profile
                )
            except Exception:
                revolve_profile = None

        try:
            slicer = MultiSliceSectionExtractor(aligned_mesh)
            sections = slicer.slice_heights(axis="Y", n_slices=self.num_slices)
        except Exception:
            sections = []

        # 5. Residual Deviation Mapping
        residual_map: Optional[ResidualMap] = None
        residual_summary = {}
        if self.detect_residuals and sections:
            try:
                res_analyzer = ResidualAnalyzer(aligned_mesh, sections)
                residual_map = res_analyzer.compute()
                residual_summary = {
                    "total_vertices_sampled": len(residual_map.vertices),
                    "significant_deviation_count": len(residual_map.significant),
                    "inward_groove_vertices": len(residual_map.inward),
                    "outward_boss_vertices": len(residual_map.outward),
                    "threshold_mm": residual_map.threshold_mm,
                }
            except Exception:
                residual_map = None

        # 6. Secondary Feature Detection with True Orientation & Confidence Scoring
        secondary_features: Dict[str, Any] = {}

        # 6a. Periodic Features (Direction-Aware: Longitudinal Ribs vs Circumferential Grooves)
        if residual_map is not None:
            try:
                per_detector = PeriodicFeatureDetector(residual_map, bounds_mm, min_confidence=0.50)
                has_periodic, periodic_data = per_detector.detect()
                if has_periodic and periodic_data:
                    secondary_features["periodic_features"] = periodic_data
                    # Backwards compatibility key
                    secondary_features["side_ribs"] = periodic_data
            except Exception:
                pass

            # 6b. V-Shaped Feature (Emboss / Deboss)
            try:
                v_detector = VFeatureDetector(residual_map, bounds_mm)
                has_v, v_data = v_detector.detect()
                if has_v and v_data and v_data.get("confidence", 0.0) >= 0.50:
                    secondary_features["v_feature"] = v_data
            except Exception:
                pass

        # 6c. Curvature-based Features (Recessed Panels, Spout Caps, Handles)
        try:
            curv_analyzer = MeshCurvatureAnalyzer(aligned_mesh)
            has_panel, panel_feat = curv_analyzer.detect_recessed_panel()
            if has_panel and panel_feat and panel_feat.confidence >= 0.50:
                secondary_features["recessed_panel"] = panel_feat.to_dict()

            has_cap, cap_feat = curv_analyzer.detect_cap_ribs()
            if has_cap and cap_feat and cap_feat.confidence >= 0.50:
                secondary_features["cap_ribs"] = cap_feat.to_dict()

            has_handle_curv, handle_feat = curv_analyzer.detect_handle_details()
            if has_handle_curv and handle_feat and handle_feat.confidence >= 0.50:
                secondary_features["handle_curvature"] = handle_feat.to_dict()
        except Exception:
            pass

        # 6d. Discrete Feature Clustering via DBSCAN
        try:
            from .feature_segmenter import FeatureSegmenter
            segmenter = FeatureSegmenter(aligned_mesh)
            seg_data = segmenter.segment_features()
            if seg_data.get("features_found"):
                secondary_features["discrete_clusters"] = seg_data
        except Exception:
            pass

        # 7. Per-Region Shape Classification & Segmentation
        per_region_classifier = PerRegionShapeClassifier(aligned_mesh, n_slices=max(30, self.num_slices))
        has_patterned = bool("periodic_features" in secondary_features)
        axial_regions = per_region_classifier.segment_regions(has_patterned_feature=has_patterned)

        # 8. CAD Synthesis Recommendation & Parametric Expressions
        classification = self._determine_classification(
            dims_mm, alignment_info, topology_res, revolve_profile, sections, axial_regions
        )
        cad_recommendation = self._build_cad_recommendations(
            classification, dims_mm, secondary_features, topology_res, axial_regions
        )

        # 9. Build Clean Reconstruction Intent IR
        reconstruction_intent = self._build_reconstruction_intent(
            classification, dims_mm, axial_regions, secondary_features, cad_recommendation["expressions"],
            revolve_profile=revolve_profile,
            cross_sections=sections,
        )

        # 10. Assemble Full Report
        return {
            "mesh_info": self.mesh_info,
            "topology": {
                "euler_characteristic": topology_res.get("euler_characteristic"),
                "genus": topology_res.get("genus", 0),
                "has_handle_loop": topology_res.get("has_handle_loop", False),
                "handle_details": topology_res.get("handle_details", {}),
            },
            "alignment": {
                "is_axisymmetric": alignment_info.get("is_axisymmetric", False),
                "aligned_height_y_mm": dims_mm[1],
                "transform_matrix": transform_matrix.tolist(),
            },
            "dimensions": {
                "bounds_mm": bounds_mm.tolist(),
                "width_x_mm": round(dims_mm[0], 2),
                "height_y_mm": round(dims_mm[1], 2),
                "depth_z_mm": round(dims_mm[2], 2),
                "centroid_mm": [round(c, 2) for c in centroid_mm],
                "volume_mm3": round(obj_analysis.volume_mm3, 2),
                "surface_area_mm2": round(obj_analysis.total_surface_area_mm2, 2),
                "component_count": obj_analysis.source_component_count,
            },
            "cross_sections": sections,
            "revolve_profile": revolve_profile,
            "residual_summary": residual_summary,
            "secondary_features": secondary_features,
            "axial_regions": [r.to_region_intent().to_dict() for r in axial_regions],
            "reconstruction_intent": reconstruction_intent.to_dict(),
            "cad_synthesis": cad_recommendation,
        }

    def _determine_classification(
        self,
        dims_mm: List[float],
        alignment_info: Dict[str, Any],
        topology_res: Dict[str, Any],
        revolve_profile: Optional[Dict[str, Any]],
        sections: List[Dict[str, Any]],
        axial_regions: List[AxialRegion],
    ) -> str:
        dx, dy, dz = dims_mm
        aspect_xz = abs(dx - dz) / max(dx, dz, 1e-6)

        if topology_res.get("genus", 0) >= 1:
            return "body_with_handle_loop"

        # Check per-region consensus
        if axial_regions:
            revolve_count = sum(
                1 for r in axial_regions
                if r.shape_type in (RegionShapeType.PURE_REVOLVE.value, RegionShapeType.REVOLVE_WITH_PATTERNED_FEATURE.value)
            )
            if revolve_count / len(axial_regions) >= 0.60 and aspect_xz < 0.20:
                return "cylindrical_revolved_body"

        if alignment_info.get("is_axisymmetric") and aspect_xz < 0.15:
            return "cylindrical_revolved_body"

        if aspect_xz > 0.40:
            return "elliptical_or_flatted_profile_solid"

        return "freeform_lofted_solid"

    def _build_cad_recommendations(
        self,
        classification: str,
        dims_mm: List[float],
        secondary_features: Dict[str, Any],
        topology_res: Dict[str, Any],
        axial_regions: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        dx, dy, dz = dims_mm

        expressions = {
            "BODY_HEIGHT": round(dy, 2),
            "BODY_WIDTH": round(dx, 2),
            "BODY_DEPTH": round(dz, 2),
        }

        suggested_tools = []
        feature_sequence = []

        # Zone-wise plan: segment by axial zones
        if axial_regions and len(axial_regions) > 1:
            base_feature = "zone_wise_multi_feature_tree"
            for idx, r in enumerate(axial_regions):
                reg_intent = r.to_region_intent()
                tool = reg_intent.recommended_cad_tool
                y_min, y_max = reg_intent.axial_range_mm
                h = round(y_max - y_min, 2)
                expressions[f"ZONE_{idx+1}_START_Y"] = y_min if idx == 0 else f"ZONE_{idx}_START_Y + ZONE_{idx}_HEIGHT"
                expressions[f"ZONE_{idx+1}_HEIGHT"] = h
                feature_sequence.append(
                    f"Zone {idx+1} ({r.region_id}): {tool} (elevation {y_min} to {y_max} mm, H={h} mm)"
                )
                if idx > 0:
                    feature_sequence.append(f"Unite Zone {idx+1} into main body via boolean_unite")
                suggested_tools.append(tool)
            suggested_tools.append("boolean_unite")
        elif classification == "cylindrical_revolved_body":
            base_feature = "zone_wise_revolved_body"
            suggested_tools.extend(["create_sketch", "revolve_from_sketch"])
            feature_sequence.append("Zone-wise body profile via revolve_from_sketch")
        elif classification == "body_with_handle_loop":
            base_feature = "zone_wise_body_with_handle_cutout"
            suggested_tools.extend(["create_block", "extrude_from_sketch", "extrude_cut", "boolean_unite"])
            feature_sequence.append("Zone 1: Lower container body via extrude_from_sketch")
            feature_sequence.append("Zone 2: Upper handle arch via extrude_from_sketch")
            feature_sequence.append("Unite upper handle arch into lower body via boolean_unite")
            feature_sequence.append("Handle void pass-through cutout via extrude_cut")
        else:
            base_feature = "zone_wise_segmented_body"
            suggested_tools.extend(["create_cylinder", "create_cone", "extrude_from_sketch", "boolean_unite"])
            feature_sequence.append("Zone 1: Base pedestal via create_cylinder / create_cone")
            feature_sequence.append("Zone 2: Main body transition via create_cone / extrude_from_sketch")
            feature_sequence.append("Unite Zone 2 into Zone 1 via boolean_unite")

        # Periodic features with directional orientation
        p_feat = secondary_features.get("periodic_features") or secondary_features.get("side_ribs")
        if p_feat and p_feat.get("confidence", 0.0) >= 0.50:
            orientation = p_feat.get("orientation", FeatureOrientation.CIRCUMFERENTIAL_AZIMUTHAL.value)
            count = int(p_feat.get("rib_count", 0))

            if orientation == FeatureOrientation.AXIAL_LONGITUDINAL.value:
                expressions["LONGITUDINAL_RIB_COUNT"] = count
                expressions["LONGITUDINAL_RIB_PITCH_DEG"] = round(p_feat.get("pitch_deg", 360.0 / max(count, 1)), 2)
                expressions["RIB_DEPTH"] = round(p_feat.get("groove_depth_mm", 0.0), 2)
                expressions["RIB_WIDTH"] = round(p_feat.get("groove_width_mm", 0.0), 2)
                suggested_tools.extend(["create_sketch", "pattern_circular"])
                feature_sequence.append(f"Longitudinal flutes/ribs ({count} instances via circular pattern around axis)")
            else:
                expressions["SIDE_RIB_COUNT"] = count
                expressions["SIDE_RIB_PITCH"] = round(p_feat.get("pitch_mm", 0.0), 2)
                expressions["SIDE_GROOVE_DEPTH"] = round(p_feat.get("groove_depth_mm", 0.0), 2)
                expressions["SIDE_GROOVE_WIDTH"] = round(p_feat.get("groove_width_mm", 0.0), 2)
                suggested_tools.extend(["extrude_cut", "pattern_linear"])
                feature_sequence.append(f"Circumferential grooves ({count} rings along Y)")

        if "cap_ribs" in secondary_features:
            cap = secondary_features["cap_ribs"]
            if cap.get("confidence", 0.0) >= 0.50:
                expressions["CAP_DIAMETER"] = round(cap.get("cap_diameter_mm", 0.0), 2)
                expressions["CAP_HEIGHT"] = round(cap.get("cap_height_mm", 0.0), 2)
                expressions["COLLAR_DIAMETER"] = round(cap.get("collar_diameter_mm", 0.0), 2)
                expressions["COLLAR_HEIGHT"] = round(cap.get("collar_height_mm", 0.0), 2)
                expressions["RIB_COUNT"] = int(cap.get("rib_count", 0))
                expressions["RIB_PITCH"] = round(cap.get("rib_pitch_deg", 0.0), 2)
                suggested_tools.extend(["create_cylinder", "pattern_circular", "boolean_unite"])
                feature_sequence.append(f"Top assembly neck & cap ({cap.get('rib_count')} fluted ribs)")

        if "v_feature" in secondary_features:
            v_feat = secondary_features["v_feature"]
            if v_feat.get("confidence", 0.0) >= 0.50:
                expressions["V_WIDTH"] = round(v_feat.get("width_mm", 0.0), 2)
                expressions["V_HEIGHT"] = round(v_feat.get("height_mm", 0.0), 2)
                expressions["V_DEPTH"] = round(v_feat.get("depth_mm", 0.0), 2)
                suggested_tools.append("create_sketch")
                feature_sequence.append(f"Upper front {v_feat.get('direction', 'V')}-feature")

        if "recessed_panel" in secondary_features:
            panel = secondary_features["recessed_panel"]
            if panel.get("confidence", 0.0) >= 0.50:
                expressions["PANEL_WIDTH"] = round(panel.get("width_mm", 0.0), 2)
                expressions["PANEL_HEIGHT"] = round(panel.get("height_mm", 0.0), 2)
                expressions["PANEL_DEPTH"] = round(panel.get("recess_depth_mm", 0.0), 2)
                expressions["PANEL_RADIUS"] = round(panel.get("corner_radius_mm", 15.0), 2)
                suggested_tools.extend(["create_sketch", "extrude_cut", "add_fillet"])
                feature_sequence.append("Front recessed label panel")

        if topology_res.get("has_handle_loop") and topology_res.get("handle_details"):
            h = topology_res["handle_details"]
            expressions["HANDLE_VOID_WIDTH"] = round(h.get("width_mm", 0.0), 2)
            expressions["HANDLE_VOID_HEIGHT"] = round(h.get("height_mm", 0.0), 2)
            expressions["HANDLE_TILT_DEG"] = round(h.get("tilt_angle_deg", 0.0), 2)
            suggested_tools.extend(["create_sketch", "extrude_cut", "add_fillet"])
            feature_sequence.append("Handle void pass-through cutout")

        suggested_tools.extend(["add_fillet", "save_part"])

        dedup_tools = []
        for t in suggested_tools:
            if t not in dedup_tools:
                dedup_tools.append(t)

        return {
            "classification": classification,
            "base_feature": base_feature,
            "feature_sequence": feature_sequence,
            "suggested_tools": dedup_tools,
            "expressions": expressions,
        }

    def _build_reconstruction_intent(
        self,
        classification: str,
        dims_mm: List[float],
        axial_regions: List[AxialRegion],
        secondary_features: Dict[str, Any],
        expressions: Dict[str, float],
        revolve_profile: Optional[Dict[str, Any]] = None,
        cross_sections: Optional[List[Dict[str, Any]]] = None,
    ) -> ReconstructionIntent:
        """Constructs the formal Reconstruction Intent Intermediate Representation."""
        region_intents: List[RegionIntent] = []
        for ar in axial_regions:
            reg_intent = ar.to_region_intent()

            # Attach features belonging to this region
            p_feat = secondary_features.get("periodic_features") or secondary_features.get("side_ribs")
            if p_feat and p_feat.get("confidence", 0.0) >= 0.50:
                y_s = p_feat.get("y_start_mm", -1e9)
                y_e = p_feat.get("y_end_mm", 1e9)
                # Overlaps with region
                if not (y_e < ar.y_min_mm or y_s > ar.y_max_mm):
                    orientation = p_feat.get("orientation", FeatureOrientation.CIRCUMFERENTIAL_AZIMUTHAL.value)
                    pattern_type = (
                        FeaturePatternType.CIRCULAR_ARRAY.value
                        if orientation == FeatureOrientation.AXIAL_LONGITUDINAL.value
                        else FeaturePatternType.LINEAR_ARRAY.value
                    )
                    feat_intent = FeatureIntent(
                        feature_id="periodic_surface_feature",
                        intent_type=p_feat.get("feature_type", "PERIODIC_FEATURE"),
                        orientation=orientation,
                        pattern_type=pattern_type,
                        pattern_count=int(p_feat.get("rib_count", 0)),
                        pitch=float(p_feat.get("pitch", 0.0)),
                        parameters={
                            "depth_mm": p_feat.get("groove_depth_mm", 0.0),
                            "width_mm": p_feat.get("groove_width_mm", 0.0),
                            "axial_span_mm": [p_feat.get("y_start_mm"), p_feat.get("y_end_mm")],
                        },
                        confidence=float(p_feat.get("confidence", 0.8)),
                        fallback=p_feat.get("fallback_strategy", "OMIT_FEATURE"),
                        evidence=p_feat.get("source_evidence", ""),
                    )
                    reg_intent.subfeatures.append(feat_intent)

            region_intents.append(reg_intent)

        overall_conf = 0.90
        if region_intents:
            overall_conf = float(np.mean([r.confidence for r in region_intents]))

        return ReconstructionIntent(
            metadata={
                "source_file": str(self.file_path) if self.file_path else "<memory>",
                "dimensions_mm": [round(d, 2) for d in dims_mm],
            },
            global_shape_family=classification,
            primary_axis=[0.0, 1.0, 0.0],
            overall_confidence=round(overall_conf, 3),
            regions=region_intents,
            expressions=expressions,
            revolve_profile=revolve_profile,
            cross_sections=cross_sections or [],
            secondary_features=secondary_features,
        )


def analyze_mesh(
    mesh_source: Union[str, Path, trimesh.Trimesh],
    num_slices: int = 21,
    detect_residuals: bool = True,
    adaptive_profile: bool = True,
) -> Dict[str, Any]:
    """
    Convenience function to analyze an OBJ mesh file or trimesh instance.
    Returns structured geometric analysis dict and Reconstruction Intent IR.
    """
    analyzer = ComprehensiveMeshAnalyzer(
        mesh_source=mesh_source,
        num_slices=num_slices,
        detect_residuals=detect_residuals,
        adaptive_profile=adaptive_profile,
    )
    return analyzer.run()
