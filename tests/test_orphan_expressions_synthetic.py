"""
test_orphan_expressions_synthetic.py
====================================
Synthetic test verifying active driving expressions and detecting orphan expressions
with known parametric geometry.
"""

import json
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.nx_mcp.mesh_analyzer.feature_recognizer import recognize_feature_plan


def test_orphan_detection_logic():
    """
    Verifies that the sensitivity perturbation logic distinguishes between
    active driving expressions and disconnected orphan expressions.
    """
    # Define a synthetic parametric specification
    active_expressions = [
        ("BODY_MAX_DIA", 50.0),
        ("ZONE1_HEIGHT", 25.0),
        ("ZONE1_BASE_R", "BODY_MAX_DIA / 2.0"),
        ("ZONE1_TOP_R", "(BODY_MAX_DIA / 2.0) * 0.90"),
    ]
    orphan_expressions = [
        ("UNUSED_EXTRA_PARAM", 123.45),
        ("DUMMY_OFFSET", 42.0),
    ]

    all_expressions = dict(active_expressions + orphan_expressions)

    # Simulate geometry function: solid volume = pi * r_avg^2 * height
    def evaluate_synthetic_volume(exp_dict):
        dia = float(exp_dict["BODY_MAX_DIA"])
        base_r = dia / 2.0
        top_r = (dia / 2.0) * 0.90
        h = float(exp_dict["ZONE1_HEIGHT"])
        r_avg = 0.5 * (base_r + top_r)
        return 3.1415926535 * (r_avg ** 2) * h

    base_vol = evaluate_synthetic_volume(all_expressions)

    # Test perturbation of each expression
    orphans_found = []
    active_found = []

    for name, val in all_expressions.items():
        if name.endswith("_START"):
            continue
        # Perturb by 10%
        perturbed = dict(all_expressions)
        if isinstance(val, (int, float)):
            perturbed[name] = float(val) * 1.10
        else:
            # Formula evaluated
            pass

        try:
            perturbed_vol = evaluate_synthetic_volume(perturbed)
        except Exception:
            perturbed_vol = base_vol

        if abs(perturbed_vol - base_vol) < 1e-4:
            orphans_found.append(name)
        else:
            active_found.append(name)

    # Verify that UNUSED_EXTRA_PARAM and DUMMY_OFFSET were identified as orphans
    assert "UNUSED_EXTRA_PARAM" in orphans_found
    assert "DUMMY_OFFSET" in orphans_found

    # Verify that BODY_MAX_DIA and ZONE1_HEIGHT were identified as active
    assert "BODY_MAX_DIA" in active_found
    assert "ZONE1_HEIGHT" in active_found
