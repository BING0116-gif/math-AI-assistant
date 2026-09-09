"""
ReActPromptTemplate — 精简版 ReAct 工具调用指令模板。

v2.0 精简版：
  - 去除与 SystemPromptManager 重复的角色定义
  - 去除与 SystemPromptManager 重复的教学风格指令
  - 仅保留工具调用格式、迭代规则和错误处理
  - 约15行指令，避免与 SystemPromptManager 冲突
"""

from __future__ import annotations

from typing import List, Optional


class ReActPromptTemplate:
    """
    精简版 ReAct Prompt 模板。

    仅负责工具调用相关指令，不涉及角色定义和输出模板。
    与 SystemPromptManager 的 LAYER3 动态注入层配合使用。
    """

    @staticmethod
    def build_instruction(tool_names: Optional[List[str]] = None) -> str:
        """
        构建精简的 ReAct 工具调用指令。

        Args:
            tool_names: 可用工具名称列表。

        Returns:
            纯工具调用指令字符串（约10行）。
        """
        names = tool_names or []
        tools_list = "、".join(names) if names else "无专用工具"
        ask_student_rules = """\n6. ask_student：仅在题目缺必要条件或需学生选择路径时使用；每轮最多 1 次，调用后停止推理等待回答
   禁止索要答案/确认计算结果/猜测缺失条件；题目信息完整时不要调用""" if "ask_student" in names else ""
        math_verify_rules = """\n7. math_verify：可程序验证的根、方程组解、导数、定积分、极限、函数值、矩阵或简单概率，发布前调用
   只传“结论 + 检查事实”，禁止传私有推理；failed 时最多重推并再验证 1 次，仍失败不得发布为已验证
   inconclusive 可保留答案但必须提示“未完全验证”，绝不能声称 verified""" if "math_verify" in names else ""

        return f"""【工具调用规范 — 必须严格遵守】

可用工具：{tools_list}

调用格式（严格遵循）：
Action: 工具名称
Action Input: {{"query": "具体问题", "parameters": {{}}}}

重要规则（违反将导致错误结果）：
1. **出题/推荐/练习/测试请求（T6场景）→ 必须调用 recommend_questions 工具，绝对禁止自己编造题目**
2. 简单问答（T1-T3场景）→ 直接回答，不使用工具
3. 计算/画图/识别（T4-T5场景）→ 按需使用工具
4. 工具失败时手动推导，不重复调用同一工具
5. 最多进行 3 次工具调用{ask_student_rules}{math_verify_rules}"""

    @staticmethod
    def build_observation(result_text: str) -> str:
        """
        构建 Observation 格式结果。

        Args:
            result_text: 工具执行结果。

        Returns:
            Observation 格式字符串。
        """
        return f"Observation: {result_text}"

    @staticmethod
    def parse_action(action_text: str) -> tuple:
        """
        解析 Action 行，提取工具名和参数。

        Args:
            action_text: "(ACTION): tool_name [[{params}]]" 格式文本。

        Returns:
            (tool_name, params_dict) 元组。
        """
        import json
        import re

        match = re.search(
            r"\(\s*ACTION\s*\)\s*:\s*(\w+)\s*\[\[\s*({.*?})\s*\]\]",
            action_text,
            re.DOTALL,
        )
        if match:
            tool_name = match.group(1).strip()
            try:
                params = json.loads(match.group(2))
            except json.JSONDecodeError:
                params = {}
            return tool_name, params

        match = re.search(
            r"\(\s*ACTION\s*\)\s*:\s*(\w+)",
            action_text,
        )
        if match:
            tool_name = match.group(1).strip()
            return tool_name, {}

        return "", {}
