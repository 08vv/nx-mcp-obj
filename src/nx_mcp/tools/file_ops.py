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



@mcp_tool("create_part", "Create a new in-memory NX part file (requires save_part to persist to disk)")
def create_part(filename: str, overwrite: bool = True):
    """
    Creates a new in-memory NX part file with the specified filename.

    NOTE: This creates and displays the part in NX session memory only. It does NOT
    write the .prt file to disk until save_part() is explicitly called.

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
                return ToolResult(
                    f"Created in-memory part: {filename} (NOTICE: Not yet written to disk; call save_part() to persist).\n\n"
                    f"Auto-opened {filename} in NX (runner script: {cmd_path})."
                )
            except Exception as e:
                return ToolResult(
                    f"Created in-memory part: {filename} (NOTICE: Not yet written to disk; call save_part() to persist).\n\n"
                    f"(Auto-open failed: {e}. You can manually run: {cmd_path})"
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


@mcp_tool("save_part", "Save the current active work part to disk (mandatory final step)")
def save_part():
    """
    Saves the current active work part in the NX session to disk.
    This is the MANDATORY final step for every CAD build sequence to persist features to the .prt file.
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
                    f"Part saved to disk: {filepath}\n\nTo manually open in NX, run:\n{cmd_path}"
                )
            return ToolResult("Part saved to disk")
        return _bridge_result(runner.call_nx("save_part", {}))
    except Exception as e:
        return ToolError(str(e))


@mcp_tool("save_part_as", "Save the current work part under a new filename/path")
def save_part_as(filename: str, overwrite: bool = True):
    """
    Saves the active work part in the NX session under a new filename or file path.

    NOTE: To save the current work part under its existing filename, use save_part() instead.
    save_part_as requires a target name distinct from the active session part name.

    :param filename: The new name or path for the part file (e.g. 'new_model.prt').
    :param overwrite: If True (default), overwrite any existing file on disk with that name.
    """
    try:
        if _use_mock_nxopen():
            part = NXSession.work_part()
            target_abs = os.path.abspath(filename if os.path.splitext(filename)[1] else f"{filename}.prt")
            wp_path = os.path.abspath(getattr(part, "FullPath", "")).lower()
            if wp_path == target_abs.lower():
                part.Save()
                runner._update_watcher_files(target_abs)
                cmd_path = _cmd_path()
                return ToolResult(
                    f"Saved part: {target_abs}\n\nTo manually open in NX, run:\n{cmd_path}"
                )
            if hasattr(part, "SaveAs"):
                part.SaveAs(filename)
            elif hasattr(part, "Save"):
                part.Save()
            filepath = target_abs
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
