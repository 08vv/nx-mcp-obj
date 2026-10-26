"""
test_benchmark_integrity.py
===========================
Automated integrity & anti-cheating verification:
1. Verifies that no mesh filename or part-specific token is hardcoded anywhere in src/.
2. Verifies that all generated CAD specification/feature plan JSON files in output/
   match their cryptographic SHA256 hashes recorded at initial generation time
   (detects manual hand-editing).
"""

import hashlib
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_no_mesh_filenames_in_src():
    """Confirms that no mesh filenames or part-specific stem names appear in src/."""
    obj_dir = REPO_ROOT / "obj"
    assert obj_dir.exists()
    
    mesh_names = [f.stem.lower() for f in obj_dir.glob("*.obj")]
    clean_stems = set()
    for m in mesh_names:
        clean_stems.add(m)
        clean = m.replace("_reduced", "").replace("-reduced", "")
        if len(clean) >= 4:
            clean_stems.add(clean)

    src_files = list((REPO_ROOT / "src").rglob("*.py"))
    assert len(src_files) > 0, "Expected Python source files in src/"

    violations = []
    for sf in src_files:
        content = sf.read_text(encoding="utf-8", errors="ignore").lower()
        for stem in clean_stems:
            if stem in content:
                violations.append((sf.relative_to(REPO_ROOT).as_posix(), stem))

    assert not violations, f"Forbidden hardcoded mesh names found in src/: {violations}"


def test_generated_plans_not_modified_after_generation():
    """Confirms that no specification or feature-plan file in output/ was hand-edited after generation."""
    output_dir = REPO_ROOT / "output"
    if not output_dir.exists():
        pytest.skip("output/ directory does not exist yet.")

    hash_files = list(output_dir.glob("*.sha256"))
    if not hash_files:
        pytest.skip("No plan hash files found in output/. Run benchmark to generate.")

    tampered = []
    for hf in hash_files:
        plan_file = hf.with_suffix("")
        if not plan_file.exists():
            continue
        expected_hash = hf.read_text(encoding="utf-8").strip()
        actual_hash = hashlib.sha256(plan_file.read_bytes()).hexdigest()
        if actual_hash != expected_hash:
            tampered.append((plan_file.name, expected_hash, actual_hash))

    assert not tampered, f"Hand-edited/modified plan files detected in output/: {tampered}"
