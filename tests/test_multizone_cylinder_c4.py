import json
import pytest
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

def test_multizone_cylinder_check4(tmp_path):
    """
    Synthetic test verifying that a multi-zone cylinder built with native sketch
    features and driving dimensions passes Check 4 (Multi-directional resizing).
    """
    spec = {
        "source_mesh": "synthetic_multizone_cylinder.obj",
        "primary_axis": "Y",
        "axis_idx": 1,
        "units_scale": 1.0,
        "circularity": 1.0,
        "zones": [
            {
                "zone_idx": 1,
                "name": "BASE_CYL",
                "role": "BODY",
                "segment_type": "LINE",
                "z_start": 0.0,
                "z_end": 40.0,
                "height": 40.0,
                "r_start": 20.0,
                "r_end": 20.0,
                "r_mid": 20.0,
                "z_mid": 20.0,
                "dia_start": 40.0,
                "dia_end": 40.0,
                "dia_max": 40.0,
                "max_dev_mm": 0.0
            },
            {
                "zone_idx": 2,
                "name": "TOP_CYL",
                "role": "BODY",
                "segment_type": "LINE",
                "z_start": 40.0,
                "z_end": 70.0,
                "height": 30.0,
                "r_start": 15.0,
                "r_end": 15.0,
                "r_mid": 15.0,
                "z_mid": 55.0,
                "dia_start": 30.0,
                "dia_end": 30.0,
                "dia_max": 30.0,
                "max_dev_mm": 0.0
            }
        ],
        "expressions": [
            ["BODY_MAX_DIA", "40.0000"],
            ["ZONE1_HEIGHT", "40.0000"],
            ["ZONE1_START", "0.0000"],
            ["ZONE1_BASE_R", "BODY_MAX_DIA / 2.0"],
            ["ZONE1_TOP_R", "BODY_MAX_DIA / 2.0"],
            ["ZONE2_HEIGHT", "30.0000"],
            ["ZONE2_START", "ZONE1_START + ZONE1_HEIGHT"],
            ["ZONE2_BASE_R", "(BODY_MAX_DIA / 2.0) * 0.75"],
            ["ZONE2_TOP_R", "(BODY_MAX_DIA / 2.0) * 0.75"]
        ]
    }

    spec_path = tmp_path / "multizone_cyl_spec.json"
    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2)

    prt_path = tmp_path / "multizone_cyl_Parametric.prt"
    run_journal_exe = Path(r"C:\Program Files\Siemens\NX2206\NXBIN\run_journal.exe")
    builder_script = REPO_ROOT / "src" / "nx_mcp" / "generic_nx_builder.py"
    
    # 1. Build PRT
    cmd_build = [str(run_journal_exe), str(builder_script), "-args", str(spec_path), str(prt_path)]
    p_b = subprocess.run(cmd_build, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
    assert p_b.returncode == 0, f"Builder failed: {p_b.stdout}"
    assert prt_path.exists(), "Output PRT was not generated."

    # 2. Check quality with check_parametric_quality.py
    checker_script = REPO_ROOT / "scripts" / "check_parametric_quality.py"
    cmd_chk = [sys.executable, str(checker_script), str(prt_path)]
    p_c = subprocess.run(cmd_chk, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
    
    # Check 4 must pass
    assert "[CHECK 4] Parametric Resizing & DoUpdate Check..." in p_c.stdout
    assert "PASS: Multi-directional resizing verified" in p_c.stdout, f"Check 4 failed in output:\n{p_c.stdout}"
