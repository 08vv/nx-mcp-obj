"""Safe deterministic math expression evaluator for CAD Spec $calc: references.

Uses ast.parse-based evaluation — no eval(), no exec(), no function calls,
no imports, no assignments. Supports basic arithmetic (+, -, *, /, //, %, **),
unary negation, comparisons, math constants (pi, e, tau), and parenthesized
sub-expressions.

Symbol references within calc expressions:
- "$nodeId.field" sub-references are pre-resolved from the executor's symbol_table
  before the expression reaches this evaluator.
- "$expr:NAME" sub-references require a bridge round-trip to read live NX expression
  values; the executor resolves these before calling safe_calc_eval.

Design decision: calc evaluation happens SERVER-SIDE in the MCP process. The executor
is responsible for resolving all symbolic sub-references (both $nodeId.field from the
symbol_table and $expr:NAME via a bridge call_nx("list_expressions") round-trip)
BEFORE passing the expression string to safe_calc_eval. This evaluator only sees
plain arithmetic with numeric literals.
"""

import ast
import math
import operator
from typing import Any, Dict, Optional, Union

# Allowed binary operators
_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

# Allowed unary operators
_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Allowed comparison operators
_CMPOPS = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}

# Allowed named constants
_CONSTANTS = {
    "pi": math.pi,
    "e": math.e,
    "tau": math.tau,
}

# Allowed safe math functions (single-argument)
_SAFE_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "atan2": math.atan2,
    "radians": math.radians,
    "degrees": math.degrees,
    "ceil": math.ceil,
    "floor": math.floor,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "hypot": math.hypot,
    "min": min,
    "max": max,
}


class CalcEvalError(Exception):
    """Raised when a calc expression cannot be safely evaluated."""
    pass


def safe_calc_eval(expression: str) -> Union[int, float]:
    """Safely evaluate an arithmetic expression string to a numeric result.

    Args:
        expression: A string containing a numeric arithmetic expression.
            Supports: +, -, *, /, //, %, **, parentheses, unary negation,
            numeric literals, math constants (pi, e, tau), and safe math
            functions (sin, cos, sqrt, etc.).

    Returns:
        The numeric result (int or float).

    Raises:
        CalcEvalError: If the expression contains disallowed constructs
            (imports, assignments, attribute access, arbitrary function calls,
            string literals, etc.) or if evaluation fails.
    """
    if not isinstance(expression, str) or not expression.strip():
        raise CalcEvalError("Empty or non-string expression")

    expression = expression.strip()

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise CalcEvalError(f"Syntax error in expression '{expression}': {e}")

    return _eval_node(tree.body)


def _eval_node(node: ast.AST) -> Union[int, float]:
    """Recursively evaluate a single AST node."""

    # Numeric literal
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise CalcEvalError(f"Non-numeric literal not allowed: {node.value!r}")

    # Named constant (pi, e, tau)
    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise CalcEvalError(f"Unknown variable '{node.id}' — only pi, e, tau are allowed as named constants")

    # Binary operation (a + b, a * b, etc.)
    if isinstance(node, ast.BinOp):
        op_fn = _BINOPS.get(type(node.op))
        if op_fn is None:
            raise CalcEvalError(f"Unsupported binary operator: {type(node.op).__name__}")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        try:
            return op_fn(left, right)
        except ZeroDivisionError:
            raise CalcEvalError("Division by zero")
        except Exception as e:
            raise CalcEvalError(f"Arithmetic error: {e}")

    # Unary operation (-x, +x)
    if isinstance(node, ast.UnaryOp):
        op_fn = _UNARYOPS.get(type(node.op))
        if op_fn is None:
            raise CalcEvalError(f"Unsupported unary operator: {type(node.op).__name__}")
        return op_fn(_eval_node(node.operand))

    # Comparison (a < b, a >= b, etc.)
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            op_fn = _CMPOPS.get(type(op))
            if op_fn is None:
                raise CalcEvalError(f"Unsupported comparison operator: {type(op).__name__}")
            right = _eval_node(comparator)
            if not op_fn(left, right):
                return 0  # False -> 0
            left = right
        return 1  # True -> 1

    # Safe function call (sin, cos, sqrt, etc.)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise CalcEvalError("Only named function calls are allowed (no attribute access, no methods)")
        fn_name = node.func.id
        if fn_name not in _SAFE_FUNCTIONS:
            raise CalcEvalError(f"Function '{fn_name}' is not allowed — permitted: {sorted(_SAFE_FUNCTIONS.keys())}")
        if node.keywords:
            raise CalcEvalError("Keyword arguments in calc expressions are not allowed")
        if node.starargs if hasattr(node, 'starargs') else False:
            raise CalcEvalError("Star arguments in calc expressions are not allowed")
        args = [_eval_node(arg) for arg in node.args]
        try:
            return _SAFE_FUNCTIONS[fn_name](*args)
        except Exception as e:
            raise CalcEvalError(f"Error calling {fn_name}({', '.join(str(a) for a in args)}): {e}")

    # Ternary / conditional expression (a if cond else b)
    if isinstance(node, ast.IfExp):
        cond = _eval_node(node.test)
        if cond:
            return _eval_node(node.body)
        return _eval_node(node.orelse)

    # Reject everything else
    raise CalcEvalError(
        f"Disallowed AST node type: {type(node).__name__}. "
        "Only arithmetic expressions with numeric literals, math constants, and safe functions are allowed."
    )
