"""
Tool Router — Routes user requests to relevant tool categories.

This module implements keyword-based routing that reduces the number of MCP tool
schemas exposed per-call from 126 down to only the categories relevant to the
user's request. It does NOT execute any tools or call NX — it only decides which
tool schemas to expose.

Architecture:
    User request text → tokenize → score categories by keyword matches →
    return matching categories + their tools (with fallback to ALL tools).

Confidence Scoring Algorithm:
    For each category, a raw score is computed as the sum of matched keyword
    weights found in the user's request text:
        raw_score = sum(weight for each matched keyword in the category)

    Single-word keywords have weight 1.0.
    Multi-word phrases have weight 2.0 (they are more specific and less ambiguous).

    A category is included if its raw_score >= MIN_RAW_WEIGHT (default 1.0),
    meaning at least one keyword matched.

    The normalized confidence score (raw_score / max_possible_weight) is
    returned for ranking but is NOT used for inclusion gating.

    If NO category has any keyword match at all, ALL tools are returned (fallback).

    When multiple categories match, all are included (multi-category support).
"""

import json
import os
import re
import time
from pathlib import Path

# ── Constants ──

# A category is included if it has at least MIN_RAW_WEIGHT matched keyword weight.
# Single-word keyword = 1.0 weight, multi-word phrase = 2.0 weight.
# So MIN_RAW_WEIGHT=1.0 means "at least one keyword matched".
MIN_RAW_WEIGHT = 1.0

# ── Category → Tool mapping ──

CATEGORY_TOOLS = {
    "Assembly": [
        "add_component", "list_components", "mate_components",
        "reposition_component",
    ],
    "Edit Operations": [
        "reverse_normal", "local_untrim_extend", "replace_edge", "x_form",
        "i_form", "match_edge", "edge_symmetry", "global_shaping",
        "global_deformation", "flattening_forming", "heal_surface",
        "edit_uv_direction", "enlarge_face", "snip_into_patches",
        "smooth_poles", "refit_face", "variable_offset",
    ],
    "File Operations": [
        "create_part", "open_part", "save_part", "export_step", "export_stl",
    ],
    "Measurement": [
        "measure_distance", "measure_angle", "measure_volume",
        "get_bounding_box", "measure_body_volume",
    ],
    "Modeling": [
        "create_cube", "create_cuboid", "create_two_cuboids",
        "create_cylinder", "extrude", "revolve", "boolean_unite",
        "boolean_subtract", "add_fillet", "add_chamfer", "add_hole",
        "mirror_feature", "pattern_feature", "edit_expression",
        "create_real_sketch", "extrude_from_sketch", "add_hole_nx",
        "create_rib", "pattern_circular", "edge_blend", "chamfer",
        "revolve_cut", "extrude_cut", "mirror_body_feature",
        "boolean_combine", "split_body", "emboss_body", "create_gear",
        "extrude_profile", "loft", "pattern", "shell",
    ],
    "Sketch": [
        "create_sketch", "draw_line", "draw_rectangle", "draw_circle",
        "draw_arc", "draw_rounded_rectangle", "create_offset_linkage_arm",
        "create_offset_plane", "add_constraint_horizontal",
        "add_constraint_vertical", "add_constraint_fixed", "draw_spline",
        "offset_curve", "close_curve_region", "create_profile",
    ],
    "Surface Modeling": [
        "trim_sheet", "extend_sheet", "trim_and_extend", "sew_sheets",
        "divide_face", "snip_surface", "untrim_sheet", "delete_edge",
        "patch_body", "unsew_sheets", "make_solid",
        "sheet_boundary_analysis", "quilt_sheets", "create_base_surface",
        "extrude_surface", "create_swept", "create_through_curves",
        "create_through_curve_mesh", "add_face_blend", "offset_surface",
        "thicken_sheet", "sweep_along_guide", "variational_sweep",
        "create_tube", "swept_volume", "create_ruled", "n_sided_surface",
        "fill_surface", "bounded_plane", "patch_openings",
        "sheet_from_curve", "law_extension",
        "studio_surface", "styled_sweep", "section_surface",
        "aesthetic_face_blend", "bridge_surface", "blend_corner",
        "styled_corner", "four_point_surface", "rapid_surfacing",
        "fit_surface", "variable_offset_face", "extension_surface",
        "silhouette_flange", "face_pairs", "user_defined_surface",
        "offset_surface_advanced", "bisector_surface",
        "surface_from_poles", "surface_through_points", "ribbon_builder",
    ],
    "Utility": [
        "set_view", "fit_view", "reset_nx_bridge", "take_screenshot",
        "list_features", "get_active_part", "get_last_operation_status",
        "list_feature_edges", "run_recipe", "run_spec",
        "get_dependency_graph", "get_downstream", "get_upstream",
        "validate_dependency_graph",
    ],
}

# ── Keyword → Category mapping ──
# Multi-word phrases are matched first (weight 2.0), then single words (weight 1.0).

CATEGORY_KEYWORDS = {
    "Assembly": [
        "assembly", "component", "mate", "coincident",
        "concentric", "reposition", "insert", "attach", "fasten",
    ],
    "Edit Operations": [
        "deform", "reshape", "x-form", "i-form",
        "match edge", "symmetry", "shaping", "flatten", "heal",
        "uv direction", "enlarge", "smooth poles",
        "refit", "normal", "reverse", "replace edge",
    ],
    "File Operations": [
        "create part", "new part", "open", "save", "export",
        "step file", "stl file", "load", "import",
    ],
    "Measurement": [
        "measure", "distance", "angle", "volume", "bounding box",
        "dimension", "size", "length", "area", "weight",
    ],
    "Modeling": [
        "cube", "cuboid", "cylinder", "extrude", "revolve", "boolean",
        "unite", "subtract", "intersect", "fillet", "chamfer", "hole",
        "mirror", "pattern", "linear pattern", "circular pattern",
        "rib", "web", "edge blend", "expression", "parameter",
        "cut", "pocket", "boss", "solid", "block", "split", "emboss",
        "shell", "draft", "gear",
    ],
    "Sketch": [
        "sketch", "draw", "line", "rectangle", "circle", "arc",
        "rounded rectangle", "horizontal constraint", "vertical constraint",
        "fixed constraint", "profile", "contour", "offset plane",
        "datum plane", "linkage arm", "2d", "spline", "curve", "blade",
        "cam", "impeller", "variable width", "variable-width",
    ],
    "Surface Modeling": [
        "surface", "sheet", "loft", "sweep", "through curves", "mesh",
        "face blend", "offset surface", "thicken", "tube", "ruled",
        "n-sided", "fill surface", "bounded plane", "patch", "variable offset",
        "law extension", "studio", "styled", "section", "aesthetic",
        "bridge surface", "corner blend", "four point", "rapid",
        "fit surface", "flange", "silhouette", "face pairs", "bisector",
        "poles", "ribbon", "sew", "unsew", "quilt", "trim", "boundary",
        "make solid", "divide face", "delete edge",
    ],
    "Utility": [
        "viewport", "top view", "front view", "right view", "iso view",
        "screenshot", "capture", "fit view", "zoom", "reset bridge",
        "list features", "feature tree", "dependency graph", "dependencies",
        "upstream", "downstream", "graph integrity",
    ],
}


def _build_keyword_index():
    """Pre-build a sorted list of (phrase, category, weight) tuples.

    Multi-word phrases are sorted longest-first so they match before
    their constituent single words.
    """
    entries = []
    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            weight = 2.0 if " " in kw else 1.0
            entries.append((kw.lower(), category, weight))
    # Sort by phrase length descending so longer phrases match first
    entries.sort(key=lambda e: -len(e[0]))
    return entries


_KEYWORD_INDEX = _build_keyword_index()


def _tokenize(text):
    """Lowercase and strip punctuation for matching."""
    return re.sub(r"[^\w\s-]", " ", text.lower())


def route(request_text):
    """Route a user request to matching tool categories.

    Args:
        request_text (str): The user's natural-language request.

    Returns:
        dict with keys:
            categories: list of {"name": str, "score": float, "tools": list[str]}
            total_tools: int — number of tools exposed
            is_fallback: bool — True if fallback to all tools was triggered
            routing_time_ms: float — time taken for routing
    """
    start = time.perf_counter()
    normalized = _tokenize(request_text)

    # Score each category
    scores = {}  # category -> total matched weight
    max_weights = {}  # category -> max possible weight

    # Compute max possible weight per category
    for category, keywords in CATEGORY_KEYWORDS.items():
        total = 0.0
        for kw in keywords:
            total += 2.0 if " " in kw else 1.0
        max_weights[category] = total
        scores[category] = 0.0

    # Match keywords against normalized text
    # Use a working copy so matched phrases can be "consumed" to avoid
    # double-counting their constituent words
    matched_phrases = set()
    for phrase, category, weight in _KEYWORD_INDEX:
        if phrase in normalized:
            # Check this phrase hasn't been subsumed by a longer match
            already_covered = False
            for mp in matched_phrases:
                if phrase in mp and phrase != mp:
                    already_covered = True
                    break
            if not already_covered:
                scores[category] += weight
                matched_phrases.add(phrase)

    # Normalize scores to [0, 1] for ranking
    confidence = {}
    for category in scores:
        if max_weights[category] > 0:
            confidence[category] = scores[category] / max_weights[category]
        else:
            confidence[category] = 0.0

    # Determine which categories to include
    best_raw = max(scores.values()) if scores else 0.0

    # Fallback: if no keyword matched at all
    if best_raw < MIN_RAW_WEIGHT:
        all_tools = []
        for tools in CATEGORY_TOOLS.values():
            all_tools.extend(tools)
        elapsed = (time.perf_counter() - start) * 1000
        return {
            "categories": [
                {"name": cat, "score": round(confidence.get(cat, 0), 4), "tools": tools}
                for cat, tools in CATEGORY_TOOLS.items()
            ],
            "total_tools": len(all_tools),
            "is_fallback": True,
            "routing_time_ms": round(elapsed, 3),
        }

    # Include all categories with at least MIN_RAW_WEIGHT matched
    result_categories = []
    total_tools = 0
    for category, raw in sorted(scores.items(), key=lambda x: -x[1]):
        if raw >= MIN_RAW_WEIGHT:
            tools = CATEGORY_TOOLS[category]
            result_categories.append({
                "name": category,
                "score": round(confidence[category], 4),
                "tools": tools,
            })
            total_tools += len(tools)

    elapsed = (time.perf_counter() - start) * 1000
    return {
        "categories": result_categories,
        "total_tools": total_tools,
        "is_fallback": False,
        "routing_time_ms": round(elapsed, 3),
    }


def get_routed_tool_names(request_text):
    """Convenience: returns just the flat list of tool names for a request."""
    result = route(request_text)
    names = []
    for cat in result["categories"]:
        names.extend(cat["tools"])
    return names


def get_all_tool_names():
    """Returns all tool names across all categories."""
    names = []
    for tools in CATEGORY_TOOLS.values():
        names.extend(tools)
    return names
