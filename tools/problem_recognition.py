from typing import Dict, Optional
import re


class ProblemRecognizer:
    """
    问题识别器，用于识别数学问题类型和提取表达式
    """
    
    def __init__(self):
        self.name = "problem_recognition"
        self.description = "用于识别数学问题类型和提取表达式"
    
    def recognize(self, text: str) -> Dict[str, str]:
        """
        识别问题类型并提取相关信息
        
        Args:
            text: 问题文本
            
        Returns:
            包含问题类型、表达式和变量的字典
        """
        # 标准化文本
        text = re.sub('\s+', ' ', text).strip()
        
        # 检查是否是积分问题
        if self._is_integration_problem(text):
            expression, variable = self._extract_integration_info(text)
            return {
                "type": "integration",
                "expression": expression,
                "variable": variable
            }
        
        # 其他类型的问题
        return {
            "type": "unknown",
            "expression": "",
            "variable": "x"
        }
    
    def _is_integration_problem(self, text: str) -> bool:
        """
        判断是否是积分问题
        """
        integration_keywords = ["积分", "∫", "integral", "积分计算", "求积分"]
        for keyword in integration_keywords:
            if keyword in text:
                return True
        return False
    
    def _extract_integration_info(self, text: str) -> tuple[str, str]:
        """
        提取积分表达式和变量
        """
        # 简单的表达式提取逻辑
        # 这里只是一个基础实现，实际应用中可能需要更复杂的逻辑
        
        # 尝试提取表达式
        expression = ""
        variable = "x"
        
        # 查找常见的积分表达式模式
        patterns = [
            r'∫\s*(.+?)\s*dx',
            r'积分\s*(.+?)\s*dx',
            r'∫\s*(.+?)\s*dy',
            r'积分\s*(.+?)\s*dy',
            r'∫\s*(.+?)\s*dt',
            r'积分\s*(.+?)\s*dt'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                expression = match.group(1).strip()
                variable = pattern[-1]
                break
        
        # 如果没有找到，尝试其他方式
        if not expression:
            # 简单处理：提取可能的表达式
            # 这里可以根据实际情况扩展
            expression = text
        
        return expression, variable
    
    def extract_math_expression(self, text: str) -> str:
        """
        从文本中提取数学表达式
        """
        # 简单的表达式提取
        text = re.sub('\s+', ' ', text).strip()
        
        # 尝试提取包含数学符号的部分
        math_symbols = '+-*/^()[]{}=<>≤≥≠√∫∑∏∪∩∈∉⊂⊃⊆⊇∂∇∞πθφλμνξηζω'
        pattern = f'[{re.escape(math_symbols)}0-9a-zA-Z\\s]+'
        
        matches = re.findall(pattern, text)
        if matches:
            # 选择最长的匹配作为表达式
            return max(matches, key=len).strip()
        
        return text
