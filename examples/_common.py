"""Shared helper functions for NX CAD part creation journal scripts."""

import math
import os

def vec(x: float, y: float, z: float):
    """Create an NXOpen Vector3d object or tuple representation."""
    try:
        import NXOpen
        return NXOpen.Vector3d(x, y, z)
    except Exception:
        return (x, y, z)

def set_name(obj, name: str):
    """Safely set the string name attribute on an NXOpen CAD object."""
    if obj is None:
        return
    try:
        obj.SetName(name)
    except Exception:
        pass

def arc_points(cx: float, cy: float, r: float, start_deg: float, end_deg: float, n: int = 8):
    """Generate points along a circular arc in 2D."""
    start_rad = math.radians(start_deg)
    end_rad = math.radians(end_deg)
    pts = []
    for i in range(n + 1):
        t = start_rad + (end_rad - start_rad) * i / n
        pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    return pts

def unite(target_body, tool_bodies):
    """Unite target body with tool bodies in active NX session."""
    if target_body is None or not tool_bodies:
        return target_body
    try:
        import NXOpen
        session = NXOpen.Session.GetSession()
        workPart = session.Parts.Work
        null_builder = NXOpen.Features.BooleanBuilder.Null
        builder = workPart.Features.CreateBooleanBuilder(null_builder)
        builder.Operation = NXOpen.Features.FeatureBooleanType.Unite
        builder.Target = target_body
        for tb in tool_bodies:
            if tb:
                builder.ToolBody.Add(tb)
        builder.Commit()
        builder.Destroy()
        return target_body
    except Exception:
        return target_body

def write_launch_files(part_path: str):
    """Generate batch launch files open_current_nx_result.cmd and open_latest_nx_result.vbs."""
    try:
        root_dir = os.path.dirname(os.path.abspath(part_path))
        cmd_file = os.path.join(root_dir, "open_current_nx_result.cmd")
        vbs_file = os.path.join(root_dir, "open_latest_nx_result.vbs")

        cmd_content = f'@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe" -ug -use_file_dir "{part_path}"\n'
        vbs_content = f'Set shell = CreateObject("WScript.Shell")\nshell.Run """C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe"" -ug -use_file_dir ""{part_path}""", 0, False\n'

        with open(cmd_file, "w") as f:
            f.write(cmd_content)
        with open(vbs_file, "w") as f:
            f.write(vbs_content)
    except Exception:
        pass
