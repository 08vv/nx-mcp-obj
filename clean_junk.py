"""Utility script to clean up temporary, session, scratch, and junk files from the workspace.

Safe by design:
- Protects git-tracked repository source files, core configs, and benchmark meshes.
- Protects canonical folders: src, tests, scripts, docs, .agents, examples, obj, img.
- Cleans all loose root scratch scripts (check_*, test_*, compare_*, find_*, measure_*, etc.).
- Cleans all root CAD models (*.prt, *.stl, *.step), root duplicate OBJs, renders (*.png), and JSON dumps.
- Cleans cache and scratch directories (scratch/, __pycache__, .pytest_cache, .ruff_cache, pytest_temp).
- Supports --all / -a (deep clean) to also purge generated CAD artifacts inside output/.
- Supports --output / -o to clean output/ artifacts only.
- Supports --dry-run / -n to preview files and disk space before deletion.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from typing import Set

ROOT_DIR = Path(__file__).resolve().parent

# Essential project files in the root that must NEVER be removed
PROTECTED_ROOT_FILES: Set[str] = {
    "pyproject.toml",
    "readme.md",
    "agents.md",
    ".env",
    ".env.example",
    ".gitignore",
    ".gitattributes",
    ".clineignore",
    ".clinerules",
    "config.json",
    "run.py",
    "verify.py",
    "prewarm_nx.py",
    "generate_docs_pdf.py",
    "clean_junk.bat",
    "clean_junk.py",
    "latest_nx_result.txt",
    "open_current_nx_result.cmd",
    "open_latest_nx_result.vbs",
}

# Protected subdirectories containing core code, tests, docs, canonical inputs, or environments
PROTECTED_DIRS: Set[str] = {
    ".git",
    "src",
    "tests",
    "scripts",
    "docs",
    ".agents",
    "examples",
    "obj",  # Canonical benchmark Wavefront OBJ mesh inputs
    "img",  # Canonical product reference photos and visual specs
    "venv",
    ".venv",
    "env",
}


def get_tracked_files() -> Set[str]:
    """Retrieve set of normalized relative paths tracked by git."""
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            check=True,
        )
        return {os.path.normpath(line.strip()) for line in res.stdout.splitlines() if line.strip()}
    except Exception:
        return set()


def is_root_junk_file(name: str, rel_file: str, tracked: Set[str]) -> bool:
    """Identifies any loose, non-essential junk file in the project root."""
    name_lower = name.lower()

    # Never delete git-tracked or protected essential files
    if rel_file in tracked or name_lower in PROTECTED_ROOT_FILES:
        return False

    suffix = Path(name_lower).suffix

    # 1. Image and render clutter in root (reference images belong in img/)
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
        return True

    # 2. CAD models, meshes, and geometry outputs in root
    if suffix in {".prt", ".stl", ".step", ".stp", ".obj", ".ply", ".iges", ".igs"}:
        return True

    # 3. Intermediate analysis, plan, and specification JSONs in root
    if suffix == ".json":
        return True

    # 4. Any root-level Python script not in PROTECTED_ROOT_FILES (scratch/check/test/debug scripts)
    if suffix == ".py":
        return True

    # 5. One-off batch or cmd scripts not in PROTECTED_ROOT_FILES
    if suffix in {".cmd", ".bat"}:
        return True

    # 6. Temp, logs, backups, locks, archives
    if suffix in {".log", ".tmp", ".bak", ".pyc", ".lock", ".zip", ".tar", ".gz", ".7z"}:
        return True

    junk_exact_names = {
        "bridge.lock",
        "bridge.launching.lock",
        "live_bridge_config.json",
        "stations_extracted.json",
        "feature_segmenter.cpython-313.pyc",
    }
    if name_lower in junk_exact_names:
        return True

    if name_lower.startswith("drive-download"):
        return True

    return False


def clean_workspace(
    deep_clean: bool = False,
    output_only: bool = False,
    dry_run: bool = False,
) -> None:
    tracked = get_tracked_files()
    removed_files: list[tuple[str, int]] = []
    removed_dirs: list[str] = []

    print("=" * 60)
    print("               NX-MCP WORKSPACE CLEANER")
    print("=" * 60)
    print(f"Target Root : {ROOT_DIR}")

    mode_str = "STANDARD CLEAN (Root scratch/CAD/JSON/PNG debris + caches)"
    if deep_clean:
        mode_str = "DEEP CLEAN (Standard clean + purge all 'output/' artifacts)"
    elif output_only:
        mode_str = "OUTPUT ONLY (Purge all 'output/' artifacts only)"

    print(f"Mode        : {mode_str}")
    if dry_run:
        print("Dry Run     : ACTIVE (No files will be deleted)")
    print("-" * 60)

    # 1. Clean root-level files (unless output_only)
    if not output_only:
        for item in ROOT_DIR.iterdir():
            if item.is_file():
                name = item.name
                rel_file = os.path.normpath(str(item.relative_to(ROOT_DIR)))

                if is_root_junk_file(name, rel_file, tracked):
                    try:
                        size = item.stat().st_size
                    except Exception:
                        size = 0
                    if not dry_run:
                        try:
                            item.unlink()
                            removed_files.append((rel_file, size))
                        except Exception as exc:
                            print(f"[WARN] Could not remove file {rel_file}: {exc}")
                    else:
                        removed_files.append((rel_file, size))

            elif item.is_dir():
                dname_lower = item.name.lower()
                rel_dir = os.path.normpath(str(item.relative_to(ROOT_DIR)))

                if dname_lower.startswith("drive-download") or dname_lower == "scratch":
                    if not dry_run:
                        try:
                            shutil.rmtree(item)
                            removed_dirs.append(rel_dir)
                        except Exception as exc:
                            print(f"[WARN] Could not remove directory {rel_dir}: {exc}")
                    else:
                        removed_dirs.append(rel_dir)

    # 2. Recursive cache and temporary directory cleanup (unless output_only)
    if not output_only:
        junk_dir_names = {".pytest_cache", ".ruff_cache", "pytest_temp", "scratch"}
        for root, dirs, _ in os.walk(ROOT_DIR, topdown=False):
            rel_root = os.path.relpath(root, ROOT_DIR)
            parts = Path(rel_root).parts
            if any(p in (".git", "venv", ".venv", "env") for p in parts):
                continue

            for d in dirs:
                dir_path = Path(root) / d
                rel_dir = os.path.normpath(str(dir_path.relative_to(ROOT_DIR)))

                if d in junk_dir_names:
                    if not dry_run:
                        try:
                            shutil.rmtree(dir_path)
                            removed_dirs.append(rel_dir)
                        except Exception as exc:
                            print(f"[WARN] Could not remove directory {rel_dir}: {exc}")
                    else:
                        removed_dirs.append(rel_dir)
                elif d == "__pycache__":
                    has_tracked = any(
                        os.path.normpath(str(p.relative_to(ROOT_DIR))) in tracked
                        for p in dir_path.glob("**/*")
                        if p.is_file()
                    )
                    if not has_tracked:
                        if not dry_run:
                            try:
                                shutil.rmtree(dir_path)
                                removed_dirs.append(rel_dir)
                            except Exception as exc:
                                print(f"[WARN] Could not remove pycache {rel_dir}: {exc}")
                        else:
                            removed_dirs.append(rel_dir)

    # 3. Clean output/ directory if deep_clean or output_only
    if deep_clean or output_only:
        output_dir = ROOT_DIR / "output"
        if output_dir.exists() and output_dir.is_dir():
            for child in output_dir.iterdir():
                rel_child = os.path.normpath(str(child.relative_to(ROOT_DIR)))
                if child.is_file():
                    try:
                        size = child.stat().st_size
                    except Exception:
                        size = 0
                    if not dry_run:
                        try:
                            child.unlink()
                            removed_files.append((rel_child, size))
                        except Exception as exc:
                            print(f"[WARN] Could not remove output file {rel_child}: {exc}")
                    else:
                        removed_files.append((rel_child, size))
                elif child.is_dir():
                    if not dry_run:
                        try:
                            shutil.rmtree(child)
                            removed_dirs.append(rel_child)
                        except Exception as exc:
                            print(f"[WARN] Could not remove output directory {rel_child}: {exc}")
                    else:
                        removed_dirs.append(rel_child)

    # 4. Reset dynamic watcher files if tracked
    if not dry_run and not output_only:
        try:
            subprocess.run(
                ["git", "checkout", "--", "latest_nx_result.txt", "open_current_nx_result.cmd", "open_latest_nx_result.vbs"],
                cwd=str(ROOT_DIR),
                capture_output=True,
                text=True,
            )
        except Exception:
            pass

    # Print summary
    prefix = "[DRY-RUN] Would remove" if dry_run else "[DELETED]"
    total_bytes = sum(size for _, size in removed_files)
    total_mb = total_bytes / (1024 * 1024)

    print(f"\n{prefix} {len(removed_files)} file(s) ({total_mb:.2f} MB):")
    for f, size in sorted(removed_files, key=lambda x: x[0]):
        size_kb = size / 1024
        print(f"  - {f:<60} ({size_kb:>8.1f} KB)")

    if removed_dirs:
        print(f"\n{prefix} {len(removed_dirs)} directory(ies):")
        for d in sorted(removed_dirs):
            print(f"  - {d}")

    status_msg = "Dry-run complete (no files touched)." if dry_run else "Workspace cleaned successfully!"
    print(f"\n[OK] {status_msg} Total reclaimed: {total_mb:.2f} MB across {len(removed_files)} file(s).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clean temporary, scratch, and junk files from the workspace."
    )
    parser.add_argument(
        "--all",
        "-a",
        dest="deep_clean",
        action="store_true",
        help="Deep clean: remove root debris AND all generated CAD outputs in output/.",
    )
    parser.add_argument(
        "--output",
        "-o",
        dest="output_only",
        action="store_true",
        help="Output clean: purge only the generated artifacts in output/.",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Simulate cleanup without deleting any files.",
    )
    args = parser.parse_args()

    clean_workspace(
        deep_clean=args.deep_clean,
        output_only=args.output_only,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()


