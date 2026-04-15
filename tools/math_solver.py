from typing import Dict
from sympy import symbols, integrate, parse_expr


class MathSolverTool:
    def __init__(self):
        self.name = "math_solver"
        self.description = "用于数学积分计算的工具"
        
    
    def solve(self, problem: Dict[str,str]) -> str:
        try:
            text = problem["text"]
            expression_str = problem.get("expression", "")
            variable = problem.get("variable", "x")
            
            
            
            
            # 解析表达式
            x = symbols(variable)
            expression = parse_expr(expression_str)
            
            # 计算积分
            integral = integrate(expression, x)
            
            return f"原函数为：{integral}"
        except Exception as e:
            return f"解题出错：{str(e)}"
