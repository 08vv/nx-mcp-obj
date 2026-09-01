# NX Journal Templates Library

This directory contains successful `run_nx_journal_code` (which runs `exec_python_code` under the hood) Python scripts, saved for reuse, organized by part type.

## Execution Context

Unlike the standalone, socket-connected example files, these templates are designed to execute directly within the active NX session. The environment pre-injects the following variables before execution:

*   `NXOpen`: The main Siemens NX API.
*   `SESSION` (`NXOpen.Session`): The active NX session.
*   `UF_SESSION` (`NXOpen.UF.UFSession`): The active User Function session.
*   `work_part` (`NXOpen.Part`): The currently active/work part in which features should be created.
*   `math`: The Python standard library `math` module.
*   `Point3d`: `NXOpen.Point3d` (convenience shortcut).
*   `Vector3d`: `NXOpen.Vector3d` (convenience shortcut).

## Writing Rules for Templates

1.  **No Boilerplate**: Do not create a new session or display part (e.g., `Parts.NewDisplay(...)`), and do not save or close parts. The host system manages part lifecycle.
2.  **Use Active Context**: Construct all geometry and expressions directly on `work_part`.
3.  **Self-Contained Logic**: Do not use sockets, standard input/output redirection, or external subprocess launches for step/stl exports inside the core logic.
4.  **Descriptive Naming**: Name files by their `<part_type>.py` (e.g., `clevis_mount.py`, `impeller_disk.py`).
