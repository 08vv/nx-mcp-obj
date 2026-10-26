"""
feature_schema.py
=================
Dataclasses and schemas representing geometric features and the
Reconstruction Intent Intermediate Representation (IR) extracted from 3D meshes:
- FeatureOrientation & FeaturePatternType enums
- RegionShapeType enum
- PeriodicRibFeature: Longitudinal ribs vs circumferential grooves vs knurl
- CapRibFeature, RecessedPanelFeature, HandleFeature
- FeatureIntent, RegionIntent, ReconstructionIntent (Clean IR)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class FeatureOrientation(str, Enum):
    AXIAL_LONGITUDINAL = "AXIAL_LONGITUDINAL"       # Varies around axis, extends along axis (ribs/flutes -> pattern circular)
    CIRCUMFERENTIAL_AZIMUTHAL = "CIRCUMFERENTIAL_AZIMUTHAL" # Varies along axis, uniform around axis (rings/grooves -> revolve cut / pattern linear)
    HELICAL_KNURL = "HELICAL_KNURL"                 # Varies in both theta and Z/Y (knurl/threads)
    RADIAL_PLANAR = "RADIAL_PLANAR"                 # Features on end-caps or planar faces
    UNKNOWN = "UNKNOWN"


class FeaturePatternType(str, Enum):
    CIRCULAR_ARRAY = "CIRCULAR_ARRAY"
    LINEAR_ARRAY = "LINEAR_ARRAY"
    SINGLE_INSTANCE = "SINGLE_INSTANCE"
    NONE = "NONE"


class RegionShapeType(str, Enum):
    PURE_REVOLVE = "PURE_REVOLVE"
    REVOLVE_WITH_PATTERNED_FEATURE = "REVOLVE_WITH_PATTERNED_FEATURE"
    PRISMATIC_EXTRUSION = "PRISMATIC_EXTRUSION"
    LOFTED_TRANSITION = "LOFTED_TRANSITION"
    FREEFORM_NURBS = "FREEFORM_NURBS"
    NON_AXISYMMETRIC = "NON_AXISYMMETRIC"


@dataclass
class PeriodicRibFeature:
    """Periodic ribs / flutes / grooves feature."""
    feature_type: str                            # "LONGITUDINAL_RIB" or "CIRCUMFERENTIAL_GROOVE" or "HELICAL_KNURL"
    orientation: str                             # FeatureOrientation value
    pattern_type: str                            # FeaturePatternType value
    rib_count: int
    pitch: float                                 # angular pitch (deg) if longitudinal, axial pitch (mm) if circumferential
    depth_mm: float
    width_mm: float
    axial_span_mm: List[float]                   # [y_start, y_end]
    confidence: float
    fallback_strategy: str                       # safe fallback if confidence is low
    source_evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CapRibFeature:
    """Top neck / fluted cap assembly feature."""
    cap_center: List[float]
    cap_diameter_mm: float
    cap_height_mm: float
    collar_diameter_mm: float
    collar_height_mm: float
    cap_top_diameter_mm: float
    rib_count: int
    rib_pitch_deg: float
    rib_width_mm: float
    rib_depth_mm: float
    confidence: float = 0.90
    source_evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RecessedPanelFeature:
    """Inset / debossed front or back label panel feature."""
    center_position: List[float]
    width_mm: float
    height_mm: float
    recess_depth_mm: float
    corner_radius_mm: float = 15.0
    panel_shape: str = "PLANAR_STADIUM"
    confidence: float = 0.90
    source_evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HandleFeature:
    """Through-hole or pass-through handle grip feature."""
    position: List[float]
    orientation_tilt_deg: float
    outer_width_mm: float
    inner_void_width_mm: float
    height_span_mm: float
    depth_mm: float
    blend_radius_mm: float = 3.0
    confidence: float = 0.90
    source_evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Clean Reconstruction Intent Intermediate Representation (IR)
# ---------------------------------------------------------------------------

@dataclass
class FeatureIntent:
    """A single detected feature intent to be synthesized in CAD."""
    feature_id: str
    intent_type: str
    orientation: str
    pattern_type: str
    pattern_count: int
    pitch: float
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    fallback: str = "OMIT_FEATURE"
    evidence: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RegionIntent:
    """A spatial / axial region with an independent shape strategy."""
    region_id: str
    axial_range_mm: List[float]                  # [y_min, y_max]
    shape_type: str                              # RegionShapeType value
    confidence: float
    base_parameters: Dict[str, Any] = field(default_factory=dict)
    subfeatures: List[FeatureIntent] = field(default_factory=list)
    recommended_cad_tool: str = "revolve_from_sketch"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "region_id": self.region_id,
            "axial_range_mm": self.axial_range_mm,
            "shape_type": self.shape_type,
            "confidence": self.confidence,
            "base_parameters": self.base_parameters,
            "subfeatures": [f.to_dict() for f in self.subfeatures],
            "recommended_cad_tool": self.recommended_cad_tool,
        }


@dataclass
class ReconstructionIntent:
    """
    Root document of the Reconstruction Intent Intermediate Representation.
    Completely decouples mesh perception from NX tool operations.
    """
    metadata: Dict[str, Any]
    global_shape_family: str                     # "AXISYMMETRIC_REVOLVE", "LOFTED_SOLID", "PRISMATIC", "HYBRID"
    primary_axis: List[float]
    overall_confidence: float
    regions: List[RegionIntent] = field(default_factory=list)
    expressions: Dict[str, float] = field(default_factory=dict)
    revolve_profile: Optional[Dict[str, Any]] = None
    cross_sections: List[Dict[str, Any]] = field(default_factory=list)
    secondary_features: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "$schema": "nx_mcp_reconstruction_intent_v1",
            "metadata": self.metadata,
            "global_shape_family": self.global_shape_family,
            "primary_axis": self.primary_axis,
            "overall_confidence": self.overall_confidence,
            "regions": [r.to_dict() for r in self.regions],
            "expressions": self.expressions,
            "revolve_profile": self.revolve_profile,
            "cross_sections": self.cross_sections,
            "secondary_features": self.secondary_features,
        }
