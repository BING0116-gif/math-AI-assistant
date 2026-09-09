"""关键数学结论的确定性验证服务（T05）。

本模块只接收结构化的“题目事实 + 候选结论”，不解析或保存模型的私有
推理文本。公开入口会隔离验证器自身异常：不能验证时返回 inconclusive，
绝不把异常伪装成 verified。
"""

from __future__ import annotations

import ast
import inspect
import logging
import math
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

import sympy as sp

logger = logging.getLogger(__name__)

VERIFIED = "verified"
FAILED = "failed"
INCONCLUSIVE = "inconclusive"
DEFAULT_ABS_TOL = 1e-7
DEFAULT_REL_TOL = 1e-6
MAX_EXPRESSION_CHARS = 1000
MAX_AST_NODES = 200


@dataclass(frozen=True)
class VerificationCheck:
    type: str
    passed: bool
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class VerificationResult:
    status: str
    checks: tuple[VerificationCheck, ...]
    confidence: float
    safe_to_publish: bool
    warning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "status": self.status,
            "checks": [check.to_dict() for check in self.checks],
            "confidence": self.confidence,
            "safe_to_publish": self.safe_to_publish,
        }
        if self.warning:
            result["warning"] = self.warning
        return result


@dataclass(frozen=True)
class VerifiedDraft:
    """一轮草稿验证的结果；retry_count 只允许 0 或 1。"""

    draft: str
    verification_request: Mapping[str, Any]
    verification: VerificationResult
    retry_count: int = 0

    @property
    def publication_text(self) -> str:
        if self.verification.status == INCONCLUSIVE:
            return self.draft.rstrip() + "\n\n> 提示：该结论未能被程序完全验证，请谨慎核对。"
        return self.draft


RedraftCallback = Callable[
    [str, Mapping[str, Any], VerificationResult],
    Awaitable[tuple[str, Mapping[str, Any]]] | tuple[str, Mapping[str, Any]],
]


class MathVerifier:
    """使用 SymPy 与数值采样验证第一版支持的数学结论。"""

    _TYPE_ALIASES = {
        "algebraic_equation": "equation",
        "equation_system": "system",
        "derivative_numeric": "derivative",
        "definite_integral": "integral",
        "function": "function_value",
        "matrix_operation": "matrix",
        "simple_probability": "probability",
    }

    def verify(self, request: Mapping[str, Any]) -> VerificationResult:
        """异常隔离的公开入口。"""
        # 某些应用/测试生命周期会用 dictConfig 禁用既有 logger；验证失败告警
        # 属于发布安全信号，公开入口必须恢复自身可观测性。
        logger.disabled = False
        logger.propagate = True
        conclusion = self._conclusion_summary(request)
        try:
            result = self._verify(request)
        except Exception as exc:  # fail-open for the main reply, never false-verify
            logger.warning(
                "MathVerifier 检查异常，降级为 inconclusive: conclusion=%s error=%s",
                conclusion,
                type(exc).__name__,
            )
            result = self._inconclusive("verifier_error", f"验证器检查失败：{type(exc).__name__}")

        # 只记录结论摘要与检查结果，不记录草稿或模型推理文本。
        logger.info(
            "MathVerifier result: conclusion=%s result=%s",
            conclusion,
            result.to_dict(),
        )
        return result

    def _verify(self, request: Mapping[str, Any]) -> VerificationResult:
        if not isinstance(request, Mapping):
            return self._inconclusive("input", "验证请求必须是对象")
        raw_type = str(request.get("type") or request.get("verification_type") or "").strip().lower()
        check_type = self._TYPE_ALIASES.get(raw_type, raw_type)
        handler = getattr(self, f"_verify_{check_type}", None)
        if not check_type or handler is None:
            return self._inconclusive("unsupported", f"暂不支持的验证类型：{raw_type or 'missing'}")
        return handler(request)

    def _verify_equation(self, request: Mapping[str, Any]) -> VerificationResult:
        equation = str(request.get("equation") or "")
        variables = self._variable_names(request, equation)
        candidates = request.get("solutions", request.get("solution"))
        normalized = self._normalize_solutions(candidates, variables)
        if not equation or not normalized:
            return self._inconclusive("substitution", "缺少方程或候选根")

        residual_expr = self._equation_residual(equation, variables)
        checks = []
        for index, solution in enumerate(normalized, start=1):
            substitutions = {sp.Symbol(k): self._parse_expression(v, variables) for k, v in solution.items()}
            residual = sp.simplify(residual_expr.subs(substitutions))
            passed = self._is_zero(residual)
            checks.append(
                VerificationCheck(
                    "substitution",
                    passed,
                    f"候选解 #{index} 代回后的残差为 {sp.sstr(residual)}",
                )
            )
        return self._from_checks(checks, confidence=0.99)

    def _verify_system(self, request: Mapping[str, Any]) -> VerificationResult:
        equations = request.get("equations")
        if not isinstance(equations, Sequence) or isinstance(equations, (str, bytes)) or not equations:
            return self._inconclusive("substitution", "缺少方程组")
        combined = " ".join(str(item) for item in equations)
        variables = self._variable_names(request, combined)
        normalized = self._normalize_solutions(request.get("solutions", request.get("solution")), variables)
        if not normalized:
            return self._inconclusive("substitution", "缺少方程组候选解")

        residuals = [self._equation_residual(str(item), variables) for item in equations]
        checks = []
        for index, solution in enumerate(normalized, start=1):
            substitutions = {sp.Symbol(k): self._parse_expression(v, variables) for k, v in solution.items()}
            evaluated = [sp.simplify(expr.subs(substitutions)) for expr in residuals]
            passed = all(self._is_zero(value) for value in evaluated)
            checks.append(
                VerificationCheck(
                    "substitution",
                    passed,
                    f"候选解 #{index} 的残差为 {[sp.sstr(value) for value in evaluated]}",
                )
            )
        return self._from_checks(checks, confidence=0.99)

    def _verify_derivative(self, request: Mapping[str, Any]) -> VerificationResult:
        variable = str(request.get("variable") or "x")
        expression = self._parse_expression(request.get("expression"), [variable])
        claimed = self._parse_expression(request.get("claimed", request.get("derivative")), [variable])
        symbol = sp.Symbol(variable)
        sample_points = request.get("sample_points") or (-1.5, -0.5, 0.5, 1.5)
        checks: List[VerificationCheck] = []

        for point in sample_points:
            x = float(point)
            h = 1e-5 * max(1.0, abs(x))
            try:
                numeric = float(sp.N((expression.subs(symbol, x + h) - expression.subs(symbol, x - h)) / (2 * h)))
                expected = float(sp.N(claimed.subs(symbol, x)))
            except (TypeError, ValueError, ZeroDivisionError, OverflowError):
                continue
            if not (math.isfinite(numeric) and math.isfinite(expected)):
                continue
            passed = self._close(numeric, expected, abs_tol=2e-4, rel_tol=2e-4)
            checks.append(
                VerificationCheck(
                    "finite_difference",
                    passed,
                    f"x={x:g}：数值差分={numeric:.10g}，候选导数={expected:.10g}",
                )
            )
        if len(checks) < 2:
            return self._inconclusive("finite_difference", "可用的导数采样点不足")
        return self._from_checks(checks, confidence=0.92)

    def _verify_integral(self, request: Mapping[str, Any]) -> VerificationResult:
        variable = str(request.get("variable") or "x")
        expression = self._parse_expression(request.get("expression", request.get("integrand")), [variable])
        lower = float(self._parse_expression(request.get("lower"), [variable]))
        upper = float(self._parse_expression(request.get("upper"), [variable]))
        claimed = float(self._parse_expression(request.get("claimed", request.get("value")), [variable]))
        if not all(math.isfinite(v) for v in (lower, upper, claimed)):
            return self._inconclusive("numeric_integral", "积分边界或候选值不是有限数")
        if lower == upper:
            return self._from_checks(
                [VerificationCheck("boundary", self._close(claimed, 0.0), "上下限相同，定积分应为 0")],
                confidence=0.99,
            )

        symbol = sp.Symbol(variable)
        interval = sp.Interval(min(lower, upper), max(lower, upper))
        try:
            from sympy.calculus.util import continuous_domain

            if continuous_domain(expression, symbol, interval) != interval:
                return self._inconclusive("boundary", "积分区间包含奇点或不连续点")
        except NotImplementedError:
            return self._inconclusive("boundary", "无法确认积分区间内的连续性")
        function = sp.lambdify(symbol, expression, modules="math")
        samples = int(request.get("samples") or 2048)
        samples = min(max(samples, 128), 8192)
        step = (upper - lower) / samples
        try:
            values = [float(function(lower + (i + 0.5) * step)) for i in range(samples)]
        except (TypeError, ValueError, ZeroDivisionError, OverflowError):
            return self._inconclusive("numeric_integral", "积分区间包含无法数值计算的点")
        if not all(math.isfinite(value) for value in values):
            return self._inconclusive("numeric_integral", "积分区间存在非有限函数值")
        numeric = step * math.fsum(values)
        tolerance = max(2e-5, abs(numeric) * 2e-4)
        check = VerificationCheck(
            "numeric_integral",
            abs(numeric - claimed) <= tolerance,
            f"中点采样={numeric:.10g}，候选值={claimed:.10g}，容差={tolerance:.3g}",
        )
        return self._from_checks([check], confidence=0.90)

    def _verify_limit(self, request: Mapping[str, Any]) -> VerificationResult:
        variable = str(request.get("variable") or "x")
        expression = self._parse_expression(request.get("expression"), [variable])
        point_expr = self._parse_expression(request.get("point"), [variable])
        claimed_expr = self._parse_expression(request.get("claimed", request.get("value")), [variable])
        direction = str(request.get("direction") or "both").lower()
        symbol = sp.Symbol(variable)

        try:
            exact = sp.limit(expression, symbol, point_expr, dir={"left": "-", "right": "+"}.get(direction, "+-"))
        except Exception:
            exact = None
        if exact is not None and exact not in (sp.nan, sp.zoo):
            passed = exact == claimed_expr or sp.simplify(exact - claimed_expr) == 0
            return self._from_checks(
                [VerificationCheck("limit", passed, f"符号极限={sp.sstr(exact)}，候选值={sp.sstr(claimed_expr)}")],
                confidence=0.98,
            )
        return self._inconclusive("limit", "极限无法稳定计算")

    def _verify_function_value(self, request: Mapping[str, Any]) -> VerificationResult:
        values = request.get("values", request.get("variables"))
        if not isinstance(values, Mapping) or not values:
            return self._inconclusive("function_value", "缺少变量取值")
        variables = [str(name) for name in values]
        expression = self._parse_expression(request.get("expression"), variables)
        claimed = self._parse_expression(request.get("claimed", request.get("value")), variables)
        substitutions = {sp.Symbol(name): self._parse_expression(value, variables) for name, value in values.items()}
        actual = sp.simplify(expression.subs(substitutions))
        expected = sp.simplify(claimed.subs(substitutions))
        check = VerificationCheck(
            "function_value",
            self._is_zero(actual - expected),
            f"函数计算值={sp.sstr(actual)}，候选值={sp.sstr(expected)}",
        )
        return self._from_checks([check], confidence=0.99)

    def _verify_matrix(self, request: Mapping[str, Any]) -> VerificationResult:
        operation = str(request.get("operation") or "").lower()
        operands = request.get("operands")
        claimed = request.get("claimed", request.get("value"))
        if not isinstance(operands, Sequence) or isinstance(operands, (str, bytes)) or not operands:
            return self._inconclusive("matrix", "缺少矩阵操作数")
        matrices = [self._matrix(item) for item in operands]
        if operation in {"add", "addition"} and len(matrices) == 2:
            actual: Any = matrices[0] + matrices[1]
        elif operation in {"multiply", "multiplication"} and len(matrices) == 2:
            actual = matrices[0] * matrices[1]
        elif operation in {"det", "determinant"} and len(matrices) == 1:
            actual = matrices[0].det()
        elif operation == "inverse" and len(matrices) == 1:
            actual = matrices[0].inv()
        else:
            return self._inconclusive("matrix", f"不支持的矩阵操作或操作数数量：{operation}")

        if isinstance(actual, sp.MatrixBase):
            expected = self._matrix(claimed)
            passed = actual.shape == expected.shape and all(self._is_zero(v) for v in (actual - expected))
            actual_text = str(actual.tolist())
            expected_text = str(expected.tolist())
        else:
            expected = self._parse_expression(claimed, [])
            passed = self._is_zero(sp.simplify(actual - expected))
            actual_text, expected_text = sp.sstr(actual), sp.sstr(expected)
        return self._from_checks(
            [VerificationCheck("matrix", passed, f"矩阵计算值={actual_text}，候选值={expected_text}")],
            confidence=0.99,
        )

    def _verify_probability(self, request: Mapping[str, Any]) -> VerificationResult:
        favorable = request.get("favorable")
        total = request.get("total")
        claimed = request.get("claimed", request.get("value"))
        if favorable is None or total is None or claimed is None:
            return self._inconclusive("probability", "简单概率验证需要 favorable、total 和 claimed")
        favorable_expr = self._parse_expression(favorable, [])
        total_expr = self._parse_expression(total, [])
        claimed_expr = self._parse_expression(claimed, [])
        if self._is_zero(total_expr):
            return self._inconclusive("probability", "样本总数不能为 0")
        actual = sp.simplify(favorable_expr / total_expr)
        range_ok = bool(actual.is_real and actual >= 0 and actual <= 1)
        passed = range_ok and self._is_zero(actual - claimed_expr)
        return self._from_checks(
            [VerificationCheck("probability", passed, f"有利数/总数={sp.sstr(actual)}，候选值={sp.sstr(claimed_expr)}")],
            confidence=0.99,
        )

    def _parse_expression(self, raw: Any, variables: Iterable[str]) -> sp.Expr:
        if raw is None:
            raise ValueError("缺少表达式")
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            return sp.sympify(raw)
        text = str(raw).strip().replace("^", "**")
        if not text or len(text) > MAX_EXPRESSION_CHARS:
            raise ValueError("表达式为空或过长")
        tree = ast.parse(text, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
            raise ValueError("表达式过于复杂")
        allowed_symbols = {name: sp.Symbol(name) for name in variables if name.isidentifier()}
        return self._ast_to_sympy(tree.body, allowed_symbols)

    def _ast_to_sympy(self, node: ast.AST, symbols: Mapping[str, sp.Symbol]) -> sp.Expr:
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return sp.sympify(node.value)
        if isinstance(node, ast.Name):
            if node.id in symbols:
                return symbols[node.id]
            constants = {"pi": sp.pi, "E": sp.E, "oo": sp.oo, "inf": sp.oo}
            if node.id in constants:
                return constants[node.id]
            raise ValueError(f"不允许的符号：{node.id}")
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = self._ast_to_sympy(node.operand, symbols)
            return value if isinstance(node.op, ast.UAdd) else -value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            left = self._ast_to_sympy(node.left, symbols)
            right = self._ast_to_sympy(node.right, symbols)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if right.is_number and abs(float(right)) > 100:
                raise ValueError("指数绝对值过大")
            return left**right
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            functions = {
                "sin": sp.sin,
                "cos": sp.cos,
                "tan": sp.tan,
                "asin": sp.asin,
                "acos": sp.acos,
                "atan": sp.atan,
                "exp": sp.exp,
                "log": sp.log,
                "sqrt": sp.sqrt,
                "abs": sp.Abs,
                "Abs": sp.Abs,
            }
            function = functions.get(node.func.id)
            if function is None or len(node.args) != 1:
                raise ValueError(f"不允许的函数调用：{node.func.id}")
            return function(self._ast_to_sympy(node.args[0], symbols))
        raise ValueError(f"不允许的表达式语法：{type(node).__name__}")

    def _equation_residual(self, equation: str, variables: Iterable[str]) -> sp.Expr:
        if equation.count("=") > 1:
            raise ValueError("方程只能包含一个等号")
        if "=" in equation:
            left, right = equation.split("=", 1)
        else:
            left, right = equation, "0"
        return sp.simplify(self._parse_expression(left, variables) - self._parse_expression(right, variables))

    def _variable_names(self, request: Mapping[str, Any], expression: str) -> List[str]:
        raw = request.get("variables", request.get("variable", "x"))
        names = [str(item) for item in raw] if isinstance(raw, (list, tuple)) else [str(raw)]
        names = [name.strip() for name in names if name and str(name).strip().isidentifier()]
        return names or ["x"]

    def _normalize_solutions(self, raw: Any, variables: Sequence[str]) -> List[Dict[str, Any]]:
        if raw is None:
            return []
        if isinstance(raw, Mapping):
            return [{str(k): v for k, v in raw.items()}]
        if isinstance(raw, (list, tuple)):
            if raw and all(isinstance(item, Mapping) for item in raw):
                return [{str(k): v for k, v in item.items()} for item in raw]
            if len(variables) == 1:
                return [{variables[0]: item} for item in raw]
            if len(raw) == len(variables):
                return [dict(zip(variables, raw))]
        if len(variables) == 1:
            return [{variables[0]: raw}]
        return []

    def _matrix(self, raw: Any) -> sp.Matrix:
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ValueError("矩阵必须是二维数组")
        rows = []
        for row in raw:
            if not isinstance(row, Sequence) or isinstance(row, (str, bytes)):
                raise ValueError("矩阵必须是二维数组")
            rows.append([self._parse_expression(value, []) for value in row])
        if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
            raise ValueError("矩阵行长度不一致")
        return sp.Matrix(rows)

    @staticmethod
    def _close(a: float, b: float, *, abs_tol: float = DEFAULT_ABS_TOL, rel_tol: float = DEFAULT_REL_TOL) -> bool:
        return math.isclose(a, b, abs_tol=abs_tol, rel_tol=rel_tol)

    @staticmethod
    def _is_zero(value: sp.Expr) -> bool:
        simplified = sp.simplify(value)
        if simplified == 0:
            return True
        try:
            numeric = complex(sp.N(simplified))
        except (TypeError, ValueError):
            return False
        return math.isfinite(numeric.real) and math.isfinite(numeric.imag) and abs(numeric) <= DEFAULT_ABS_TOL

    @staticmethod
    def _from_checks(checks: Sequence[VerificationCheck], *, confidence: float) -> VerificationResult:
        passed = bool(checks) and all(check.passed for check in checks)
        return VerificationResult(
            status=VERIFIED if passed else FAILED,
            checks=tuple(checks),
            confidence=confidence if passed else min(confidence, 0.05),
            safe_to_publish=passed,
        )

    @staticmethod
    def _inconclusive(check_type: str, detail: str) -> VerificationResult:
        return VerificationResult(
            status=INCONCLUSIVE,
            checks=(VerificationCheck(check_type, False, detail),),
            confidence=0.0,
            safe_to_publish=True,
            warning="未完全验证",
        )

    @staticmethod
    def _conclusion_summary(request: Any) -> Dict[str, str]:
        if not isinstance(request, Mapping):
            return {"type": "invalid"}
        summary = {"type": str(request.get("type") or request.get("verification_type") or "missing")[:40]}
        for key in ("equation", "expression", "claimed", "solution", "value"):
            if key in request:
                summary[key] = str(request[key])[:160]
        return summary


async def verify_draft_with_single_retry(
    draft: str,
    verification_request: Mapping[str, Any],
    *,
    redraft: Optional[RedraftCallback] = None,
    verifier: Optional[MathVerifier] = None,
) -> VerifiedDraft:
    """验证草稿；仅在 failed 时调用一次 redraft，硬性避免重推死循环。"""
    engine = verifier or get_math_verifier()
    first = engine.verify(verification_request)
    if first.status != FAILED or redraft is None:
        return VerifiedDraft(draft, verification_request, first, retry_count=0)

    revised = redraft(draft, verification_request, first)
    if inspect.isawaitable(revised):
        revised = await revised
    revised_draft, revised_request = revised
    second = engine.verify(revised_request)
    return VerifiedDraft(revised_draft, revised_request, second, retry_count=1)


_verifier: Optional[MathVerifier] = None


def get_math_verifier() -> MathVerifier:
    global _verifier
    if _verifier is None:
        _verifier = MathVerifier()
    return _verifier
