"""Deterministic symbolic solver tool used by the tutoring agent.

The model supplies a small structured request; all expression parsing stays in
the existing safe grammar so this tool never evaluates arbitrary Python.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict

import sympy as sp
from pydantic import BaseModel, ConfigDict, Field

from app.services.safe_math import parse_safe_expression
from tools.base_tool import BaseTool, ToolCapability, ToolInput, ToolOutput


class MathSolverParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str = Field("simplify", description="simplify, solve, derivative, integral, limit, or equation")
    expression: str = ""
    variable: str = "x"
    equation: str = ""
    point: str = ""
    lower: str = ""
    upper: str = ""


class MathSolverArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(..., description="简短说明要计算的数学目标")
    parameters: MathSolverParameters


class MathSolverTool(BaseTool):
    name = "math_solver"
    description = (
        "对已经明确的数学表达式做安全符号计算。必须传 parameters，支持 "
        "simplify、solve、equation、derivative、integral、limit；不要传自然语言推理过程。"
    )
    version = "1.0.0"
    capabilities = [ToolCapability.SYMBOLIC_COMPUTATION, ToolCapability.VERIFICATION]
    args_schema = MathSolverArgs

    def get_info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [cap.value for cap in self.capabilities],
            "input_schema": self.args_schema.model_json_schema(),
        }

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        request = dict(input_data.parameters or {})
        nested = request.get("parameters")
        if isinstance(nested, BaseModel):
            nested = nested.model_dump(exclude_none=True)
        if isinstance(nested, dict):
            request = nested
        kind = str(request.get("type") or "simplify").lower()
        raw_variable = str(request.get("variable") or "x")
        # Models sometimes copy the destination from natural language (for
        # example ``x→∞``).  The safe parser accepts identifiers only, so keep
        # the first valid symbol and fall back to x instead of sending prose
        # into the symbolic layer.
        variable_match = re.search(r"[A-Za-z][A-Za-z0-9_]*", raw_variable)
        variable = variable_match.group(0) if variable_match else "x"
        expr_text = str(request.get("expression") or "")
        # Models occasionally omit ``variable`` or send a different symbol in
        # a generated expression. Infer a small symbol allow-list before the
        # safe parser runs; the parser still rejects functions, constants and
        # arbitrary names.
        inferred = [name for name in re.findall(r"[A-Za-z][A-Za-z0-9_]*", expr_text)
                    if name not in {"sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh", "exp", "log", "ln", "sqrt", "Abs", "pi", "E"}]
        variables = list(dict.fromkeys([variable, *inferred]))[:8]
        if kind in {"equation", "solve"}:
            equation = str(request.get("equation") or expr_text)
            if "=" not in equation:
                raise ValueError("equation must contain '='")
            left, right = equation.split("=", 1)
            result = sp.solve(parse_safe_expression(left, variables) - parse_safe_expression(right, variables), sp.Symbol(variable))
        else:
            expr = parse_safe_expression(expr_text, variables)
            symbol = sp.Symbol(variable)
            if kind == "derivative":
                result = sp.diff(expr, symbol)
            elif kind == "integral":
                result = sp.integrate(expr, symbol)
            elif kind == "limit":
                raw_point = str(request.get("point") or "0").strip().lower()
                point = sp.oo if raw_point in {"∞", "infinity", "inf", "oo"} else parse_safe_expression(raw_point)
                result = sp.limit(expr, symbol, point)
            elif kind == "simplify":
                result = sp.simplify(expr)
            else:
                raise ValueError(f"unsupported solver type: {kind}")
        payload = {"type": kind, "result": str(result), "latex": sp.latex(result)}
        return ToolOutput(
            success=True,
            result=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            data=payload,
            tool_name=self.name,
            metadata={"solver_type": kind},
        )
