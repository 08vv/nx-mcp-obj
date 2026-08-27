"""Unit tests for the calc expression evaluator — no NX, no mocking."""

import math
import pytest
from nx_mcp.spec.calc import safe_calc_eval, CalcEvalError


class TestBasicArithmetic:
    def test_addition(self):
        assert safe_calc_eval("2 + 3") == 5

    def test_subtraction(self):
        assert safe_calc_eval("10 - 4") == 6

    def test_multiplication(self):
        assert safe_calc_eval("6 * 7") == 42

    def test_division(self):
        assert abs(safe_calc_eval("22 / 7") - 22 / 7) < 1e-10

    def test_floor_division(self):
        assert safe_calc_eval("7 // 2") == 3

    def test_modulo(self):
        assert safe_calc_eval("10 % 3") == 1

    def test_power(self):
        assert safe_calc_eval("2 ** 10") == 1024

    def test_parenthesized(self):
        assert safe_calc_eval("(2 + 3) * 4") == 20

    def test_nested_parens(self):
        assert safe_calc_eval("((1 + 2) * (3 + 4)) / 7") == 3.0

    def test_unary_negation(self):
        assert safe_calc_eval("-5") == -5

    def test_unary_positive(self):
        assert safe_calc_eval("+3") == 3

    def test_float_literal(self):
        assert abs(safe_calc_eval("3.14159") - 3.14159) < 1e-10

    def test_complex_expression(self):
        # Bolt circle radius: PCD / 2
        assert safe_calc_eval("100 / 2") == 50.0


class TestMathConstants:
    def test_pi(self):
        assert abs(safe_calc_eval("pi") - math.pi) < 1e-10

    def test_e(self):
        assert abs(safe_calc_eval("e") - math.e) < 1e-10

    def test_tau(self):
        assert abs(safe_calc_eval("tau") - math.tau) < 1e-10

    def test_pi_arithmetic(self):
        assert abs(safe_calc_eval("2 * pi * 25") - 2 * math.pi * 25) < 1e-9


class TestSafeFunctions:
    def test_sqrt(self):
        assert abs(safe_calc_eval("sqrt(144)") - 12.0) < 1e-10

    def test_sin(self):
        assert abs(safe_calc_eval("sin(pi / 2)") - 1.0) < 1e-10

    def test_cos(self):
        assert abs(safe_calc_eval("cos(0)") - 1.0) < 1e-10

    def test_atan2(self):
        assert abs(safe_calc_eval("atan2(1, 1)") - math.pi / 4) < 1e-10

    def test_radians(self):
        assert abs(safe_calc_eval("radians(180)") - math.pi) < 1e-10

    def test_degrees(self):
        assert abs(safe_calc_eval("degrees(pi)") - 180.0) < 1e-10

    def test_abs_negative(self):
        assert safe_calc_eval("abs(-42)") == 42

    def test_round(self):
        assert safe_calc_eval("round(3.7)") == 4

    def test_ceil(self):
        assert safe_calc_eval("ceil(3.1)") == 4

    def test_floor(self):
        assert safe_calc_eval("floor(3.9)") == 3

    def test_min_max(self):
        assert safe_calc_eval("min(3, 5)") == 3
        assert safe_calc_eval("max(3, 5)") == 5

    def test_hypot(self):
        assert abs(safe_calc_eval("hypot(3, 4)") - 5.0) < 1e-10

    def test_nested_function(self):
        # sin(radians(30)) = 0.5
        assert abs(safe_calc_eval("sin(radians(30))") - 0.5) < 1e-10


class TestDivisionByZero:
    def test_integer_division(self):
        with pytest.raises(CalcEvalError, match="Division by zero"):
            safe_calc_eval("1 / 0")

    def test_floor_division(self):
        with pytest.raises(CalcEvalError, match="Division by zero"):
            safe_calc_eval("10 // 0")


class TestSecurityRejections:
    def test_import_rejected(self):
        with pytest.raises(CalcEvalError):
            safe_calc_eval("__import__('os')")

    def test_attribute_access_rejected(self):
        with pytest.raises(CalcEvalError):
            safe_calc_eval("().__class__")

    def test_unknown_function_rejected(self):
        with pytest.raises(CalcEvalError, match="not allowed"):
            safe_calc_eval("exec('print(1)')")

    def test_string_literal_rejected(self):
        with pytest.raises(CalcEvalError):
            safe_calc_eval("'hello'")

    def test_list_rejected(self):
        with pytest.raises(CalcEvalError):
            safe_calc_eval("[1, 2, 3]")

    def test_dict_rejected(self):
        with pytest.raises(CalcEvalError):
            safe_calc_eval("{'a': 1}")

    def test_lambda_rejected(self):
        with pytest.raises(CalcEvalError):
            safe_calc_eval("lambda: 1")

    def test_keyword_args_rejected(self):
        with pytest.raises(CalcEvalError, match="Keyword arguments"):
            safe_calc_eval("round(3.14, ndigits=1)")

    def test_unknown_variable_rejected(self):
        with pytest.raises(CalcEvalError, match="Unknown variable"):
            safe_calc_eval("x + 1")

    def test_empty_string(self):
        with pytest.raises(CalcEvalError, match="Empty"):
            safe_calc_eval("")

    def test_none_input(self):
        with pytest.raises(CalcEvalError, match="Empty"):
            safe_calc_eval(None)

    def test_assignment_rejected(self):
        with pytest.raises(CalcEvalError):
            safe_calc_eval("x = 5")


class TestConditionalExpressions:
    def test_ternary_true(self):
        assert safe_calc_eval("10 if 1 else 20") == 10

    def test_ternary_false(self):
        assert safe_calc_eval("10 if 0 else 20") == 20


class TestCADUseCases:
    def test_bolt_circle_angle(self):
        # Angle step for 6 holes
        result = safe_calc_eval("360 / 6")
        assert result == 60.0

    def test_offset_from_center(self):
        # Half of width minus wall thickness
        result = safe_calc_eval("100 / 2 - 5")
        assert result == 45.0

    def test_polar_x_coordinate(self):
        # x = radius * cos(angle_rad)
        result = safe_calc_eval("25 * cos(radians(45))")
        assert abs(result - 25 * math.cos(math.radians(45))) < 1e-10

    def test_polar_y_coordinate(self):
        result = safe_calc_eval("25 * sin(radians(45))")
        assert abs(result - 25 * math.sin(math.radians(45))) < 1e-10
