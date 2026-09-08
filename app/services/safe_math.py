"""Restricted mathematical-expression parsing for deterministic grading.

This module never evaluates user supplied Python.  It parses a deliberately
small expression grammar with :mod:`ast` and constructs SymPy objects directly.
"""

from __future__ import annotations

import ast
import re
from typing import Iterable

import sympy


MAX_EXPRESSION_LENGTH = 256
MAX_AST_NODES = 64
MAX_AST_DEPTH = 16
MAX_VARIABLES = 8
MAX_RESULT_OPS = 100
MAX_POWER = 20

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
_FUNCTIONS = {
    "sin": sympy.sin,
    "cos": sympy.cos,
    "tan": sympy.tan,
    "asin": sympy.asin,
    "acos": sympy.acos,
    "atan": sympy.atan,
    "sinh": sympy.sinh,
    "cosh": sympy.cosh,
    "tanh": sympy.tanh,
    "exp": sympy.exp,
    "log": sympy.log,
    "ln": sympy.log,
    "sqrt": sympy.sqrt,
    "Abs": sympy.Abs,
}
_CONSTANTS = {"pi": sympy.pi, "E": sympy.E}


class SafeExpressionError(ValueError):
    """The expression is outside the deterministic grading grammar."""


def _tree_depth(node: ast.AST) -> int:
    children = list(ast.iter_child_nodes(node))
    return 1 if not children else 1 + max(_tree_depth(child) for child in children)


def _normalise_variables(variables: Iterable[str] | None) -> dict[str, sympy.Symbol]:
    names = list(variables or [])
    if len(names) > MAX_VARIABLES or len(set(names)) != len(names):
        raise SafeExpressionError("invalid variable list")
    if any(not isinstance(name, str) or not _IDENTIFIER.fullmatch(name) for name in names):
        raise SafeExpressionError("invalid variable name")
    if any(name in _FUNCTIONS or name in _CONSTANTS for name in names):
        raise SafeExpressionError("reserved variable name")
    return {name: sympy.Symbol(name) for name in names}


def _numeric_value(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _numeric_value(node.operand)
        if value is not None:
            return value if isinstance(node.op, ast.UAdd) else -value
    return None


def _convert(node: ast.AST, symbols: dict[str, sympy.Symbol]):
    if isinstance(node, ast.Expression):
        return _convert(node.body, symbols)
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SafeExpressionError("only numeric literals are allowed")
        if isinstance(value, int):
            if len(str(abs(value))) > 20:
                raise SafeExpressionError("numeric literal is too large")
            return sympy.Integer(value)
        if not (-1e100 <= value <= 1e100):
            raise SafeExpressionError("numeric literal is too large")
        return sympy.Float(value)
    if isinstance(node, ast.Name):
        if node.id in symbols:
            return symbols[node.id]
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        raise SafeExpressionError("unknown variable")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _convert(node.operand, symbols)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _convert(node.left, symbols)
        right = _convert(node.right, symbols)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            exponent = _numeric_value(node.right)
            if exponent is None or abs(exponent) > MAX_POWER:
                raise SafeExpressionError("power is too complex")
            return left ** right
        raise SafeExpressionError("operator is not allowed")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCTIONS:
            raise SafeExpressionError("function is not allowed")
        if node.keywords or len(node.args) not in ({1, 2} if node.func.id in {"log"} else {1}):
            raise SafeExpressionError("invalid function arguments")
        return _FUNCTIONS[node.func.id](*[_convert(arg, symbols) for arg in node.args])
    raise SafeExpressionError("expression construct is not allowed")


def parse_safe_expression(expression: str, variables: Iterable[str] | None = None):
    text = str(expression or "").strip()
    if not text or len(text) > MAX_EXPRESSION_LENGTH:
        raise SafeExpressionError("expression length is invalid")
    symbols = _normalise_variables(variables)
    try:
        tree = ast.parse(text.replace("^", "**"), mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise SafeExpressionError("invalid expression syntax") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_AST_NODES or _tree_depth(tree) > MAX_AST_DEPTH:
        raise SafeExpressionError("expression is too complex")
    result = _convert(tree, symbols)
    if int(sympy.count_ops(result)) > MAX_RESULT_OPS:
        raise SafeExpressionError("expression has too many operations")
    return result


def expressions_equivalent(student: str, canonical: str, variables: Iterable[str] | None = None) -> bool:
    left = parse_safe_expression(student, variables)
    right = parse_safe_expression(canonical, variables)
    return bool(sympy.simplify(left - right) == 0)

