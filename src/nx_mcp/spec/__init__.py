"""CAD Spec schema and graph executor package."""

from .schema import CADSpec, SpecNode, parse_symbolic_ref, is_symbolic_ref, is_expr_ref, is_calc_ref, is_fn_ref, parse_fn_ref
from .validator import validate_spec, ValidationError
from .executor import SpecExecutor, SpecExecutionError, execute_spec
from .calc import safe_calc_eval, CalcEvalError
from .geometry_math import GEOMETRY_FUNCTIONS

__all__ = [
    "CADSpec",
    "SpecNode",
    "parse_symbolic_ref",
    "is_symbolic_ref",
    "is_expr_ref",
    "is_calc_ref",
    "is_fn_ref",
    "parse_fn_ref",
    "validate_spec",
    "ValidationError",
    "SpecExecutor",
    "SpecExecutionError",
    "execute_spec",
    "safe_calc_eval",
    "CalcEvalError",
    "GEOMETRY_FUNCTIONS",
]

