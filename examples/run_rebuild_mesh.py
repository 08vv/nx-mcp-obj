#!/usr/bin/env python3
"""
examples/run_rebuild_mesh.py
============================
Clean example demonstrating programmatic invocation of the generic NX CAD
reverse-engineering pipeline on any Wavefront OBJ mesh file.

Usage:
    python examples/run_rebuild_mesh.py [path_to_mesh.obj] [--output out.prt]

Example:
    python examples/run_rebuild_mesh.py Axe3.obj
    python examples/run_rebuild_mesh.py TRESemme6.obj
    python examples/run_rebuild_mesh.py Surfexcel2_reduced.obj
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILDER_SCRIPT = REPO_ROOT / "scripts" / "build_from_intent.py"


def run_rebuild(mesh_path: Path, output_prt: Path | None = None) -> bool:
    """Executes the unified parametric rebuild pipeline for the given mesh."""
    if not mesh_path.exists():
        print(f"[ERROR] Mesh file does not exist: {mesh_path}")
        return False

    cmd = [sys.executable, str(BUILDER_SCRIPT), str(mesh_path)]
    if output_prt:
        cmd.extend(["--output", str(output_prt)])

    print("=" * 70)
    print("RUNNING GENERIC NX PARAMETRIC REBUILD")
    print(f"  Input Mesh: {mesh_path.name}")
    print(f"  Target PRT: {output_prt or (mesh_path.stem + '_Parametric.prt')}")
    print("=" * 70)

    # Ensure license server is set if not already present
    env = os.environ.copy()
    env.setdefault("SPLM_LICENSE_SERVER", "28000@192.168.1.29")

    result = subprocess.run(cmd, env=env)
    if result.returncode == 0:
        print("\n[SUCCESS] Parametric CAD model created successfully.")
        return True
    else:
        print(f"\n[FAIL] Rebuild process exited with code {result.returncode}.")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Programmatic example of generic NX CAD reverse-engineering."
    )
    parser.add_argument(
        "mesh_path",
        type=str,
        nargs="?",
        default=str(REPO_ROOT / "Axe3.obj"),
        help="Path to .obj file to rebuild (defaults to Axe3.obj).",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Optional path for the output .prt file.",
    )
    args = parser.parse_args()

    input_file = Path(args.mesh_path).resolve()
    out_file = Path(args.output).resolve() if args.output else None

    success = run_rebuild(input_file, out_file)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
