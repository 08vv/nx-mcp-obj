import os

from ..bridge import runner
from ..nx_session import NXSession
from ..response import ToolError, ToolResult
from ..tools.registry import mcp_tool


def _cmd_path():
    return str(runner.ROOT_DIR / "open_current_nx_result.cmd")


import subprocess
import os
from nx_mcp.tools._common import _bridge_result, _use_mock_nxopen



@mcp_tool("create_part", "Create a new empty NX part file")
def create_part(filename: str, overwrite: bool = True):
    """
    Creates a new empty NX part file with the specified filename.

    :param filename: The name or path for the new part file (e.g. 'model1.prt').
    :param overwrite: If True (default), overwrite/delete any existing file to ensure a clean empty part.
    """
    try:
        if _use_mock_nxopen():
            nxopen = NXSession.nxopen()
            NXSession.get().Parts.NewDisplay(filename, nxopen.Part.Units.Millimeters)
            runner._update_watcher_files(filename)
            cmd_path = _cmd_path()
            try:
                subprocess.Popen([cmd_path], shell=True)
                return ToolResult(f"Created part: {filename}\n\nAuto-opened {filename} in NX (runner script: {cmd_path}).")
            except Exception as e:
                return ToolResult(
                    f"Created part: {filename}\n\n(Auto-open failed: {e}. You can manually run: {cmd_path})"
                )
        return _bridge_result(runner.call_nx("create_part", {"filename": filename, "overwrite": overwrite}), auto_open=True)
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("open_part", "Open an existing NX part file by full path")
def open_part(filepath: str):
    """
    Opens an existing NX part file using its full absolute file path.

    :param filepath: The absolute file path to the existing '.prt' file.
    """
    try:
        if _use_mock_nxopen():
            NXSession.get().Parts.OpenDisplay(filepath)
            runner._update_watcher_files(filepath)
            cmd_path = _cmd_path()
            try:
                subprocess.Popen([cmd_path], shell=True)
                return ToolResult(f"Opened part: {filepath}\n\nAuto-opened {os.path.basename(filepath)} in NX (runner script: {cmd_path}).")
            except Exception as e:
                return ToolResult(
                    f"Opened part: {filepath}\n\n(Auto-open failed: {e}. You can manually run: {cmd_path})"
                )
        return _bridge_result(runner.call_nx("open_part", {"filepath": filepath}), auto_open=True)
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("save_part", "Save the current work part")
def save_part():
    """
    Saves the current active work part in the NX session.
    """
    try:
        if _use_mock_nxopen():
            part = NXSession.work_part()
            part.Save()
            filepath = getattr(part, "FullPath", "")
            if filepath:
                runner._update_watcher_files(filepath)
                cmd_path = _cmd_path()
                return ToolResult(
                    f"Part saved\n\nTo manually open in NX, run:\n{cmd_path}"
                )
            return ToolResult("Part saved")
        return _bridge_result(runner.call_nx("save_part", {}))
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("save_part_as", "Save the current work part under a new filename/path")
def save_part_as(filename: str, overwrite: bool = True):
    """
    Saves the active work part in the NX session under a new filename or file path.

    :param filename: The new name or path for the part file (e.g. 'new_model.prt').
    :param overwrite: If True (default), overwrite any existing file with that name.
    """
    try:
        if _use_mock_nxopen():
            part = NXSession.work_part()
            if hasattr(part, "SaveAs"):
                part.SaveAs(filename)
            elif hasattr(part, "Save"):
                part.Save()
            filepath = os.path.abspath(filename if os.path.splitext(filename)[1] else f"{filename}.prt")
            runner._update_watcher_files(filepath)
            cmd_path = _cmd_path()
            return ToolResult(
                f"Saved part as: {filepath}\n\nTo manually open in NX, run:\n{cmd_path}"
            )
        return _bridge_result(
            runner.call_nx("save_part_as", {"filename": filename, "overwrite": overwrite}),
            auto_open=True,
        )
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("export_step", "Export current part as STEP file")
def export_step(output_path: str):
    """
    Exports the current work part geometry to a STEP format file.

    :param output_path: Destination file path for the STEP export.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("export_step", {"output_path": output_path})
            )
        exp = NXSession.get().DexManager.CreateStepCreator()
        exp.ObjectTypes.Solids = True
        exp.OutputFile = output_path
        exp.Commit()
        exp.Destroy()
        return ToolResult(f"Exported STEP: {output_path}")
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("export_stl", "Export current part as STL file")
def export_stl(output_path: str):
    """
    Exports the current work part geometry to an STL format file.

    :param output_path: Destination file path for the STL export.
    """
    try:
        if not _use_mock_nxopen():
            return _bridge_result(
                runner.call_nx("export_stl", {"output_path": output_path})
            )
        exp = NXSession.get().DexManager.CreateStlCreator()
        exp.OutputFile = output_path
        exp.Commit()
        exp.Destroy()
        return ToolResult(f"Exported STL: {output_path}")
    except Exception as e:
        return ToolError(str(e))
