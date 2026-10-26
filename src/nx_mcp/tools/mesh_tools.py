"""
mesh_tools.py
=============
MCP Tools for Wavefront OBJ Mesh Geometric Analysis.
Directly interfaces with nx_mcp.mesh_analyzer to provide AI agents with full
parametric reverse-engineering insights.
"""

from __future__ import annotations

import json
from pathlib import Path

from nx_mcp.mesh_analyzer import analyze_mesh
from nx_mcp.response import ToolError, ToolResult
from nx_mcp.tools.registry import mcp_tool


@mcp_tool(
    "analyze_obj_mesh",
    "Analyze a Wavefront OBJ mesh file to extract CAD features, topology, dimensions, and recommended parametric expressions",
)
def analyze_obj_mesh(
    file_path: str,
    num_slices: int = 21,
    detect_residuals: bool = True,
) -> ToolResult:
    """
    Analyze a Wavefront OBJ mesh file for parametric NX CAD reconstruction.

    Args:
        file_path (str): Absolute or relative path to the .obj file.
        num_slices (int): Number of cross-section slicing stations along height (default: 21).
        detect_residuals (bool): Whether to compute residual deviation map for secondary features (default: True).

    Returns:
        ToolResult: Comprehensive geometric analysis JSON string including topology, bounding box (mm),
                    cross-sections, detected secondary features (cap ribs, side ribs, panels, handles),
                    and recommended NX parametric expressions and tool sequence.
    """
    try:
        p = Path(file_path).resolve()
        if not p.exists():
            return ToolError(f"OBJ mesh file not found: {file_path}")

        report = analyze_mesh(p, num_slices=num_slices, detect_residuals=detect_residuals)
        return ToolResult(json.dumps(report, indent=2))
    except Exception as e:
        return ToolError(f"Failed to analyze OBJ mesh '{file_path}': {str(e)}")
