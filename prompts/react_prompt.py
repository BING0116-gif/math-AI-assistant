"""
ReActPromptTemplate — ReAct (Reasoning-Acting) 提示词模板。

实现"思考-行动-观察"循环的标准化 Prompt 模板，
为 Agent 提供结构化的思维链引导。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Callable
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


class ReActPromptTemplate:
    """
    ReAct 思维链提示词模板。

    实现 ZeroShot-ReAct 风格的 Prompt，为 LLM 提供：
    1. 明确的思考-行动-观察循环指令
    2. 结构化的输出格式要求
    3. 工具调用的标准格式

    Example:
        template = ReActPromptTemplate()
        prompt = template.build_prompt(tools_description="...")
        messages = prompt.format_messages(
            tools_section="...",
            input="求∫x²dx",
        )
    """

    REACT_SYSTEM_PROMPT = """你是一个智能数学解题助手，具备使用工具进行深度推理的能力。

【核心思维模式 — 严格遵循 ReAct 循环】

当你面对问题时，必须遵循以下思考流程：

## 第一步：分析问题（Thought）
仔细分析用户的问题，判断：
1. 这是一道什么类型的数学题？（求导/积分/证明/应用）
2. 需要用到哪些数学知识和技巧？
3. 是否需要调用工具？（计算/画图/识别图片）

## 第二步：决定行动（Action）
如果没有现成的答案，确定下一步行动：
- 直接回答（简单概念问题）
- 调用工具（计算题、复杂问题）
- 请求用户提供更多信息

## 第三步：观察结果（Observation）
从工具返回的结果中提取关键信息。

## 第四步：得出结论（Final Answer）
综合所有信息，给出完整解答。

【重要约束】
1. 每次思考最多进行 3 步 ReAct 循环，避免无限循环
2. 工具调用格式必须严格遵守，参数必须是合法的 JSON
3. 如果工具执行失败，说明原因并尝试替代方案
4. 最终答案必须包含详细的解题步骤和依据

【输出格式 — 直接输出，不要在 Thought/Action 之前加任何前缀】

Thought: [你的思考过程]
Action: [工具名称，如果不需要工具则写 "Final Answer"]
Action Input: {{"query": "问题描述", "parameters": {{"参数名": "参数值"}}}}
Observation: [工具返回的结果，如果 Action 是 "Final Answer" 则省略]
...（Thought/Action/Observation 可以重复多次）

Final Answer: [最终解答，包含完整的解题步骤和答案]

"""

    REACT_WITH_TOOLS_PROMPT = """你是一个智能数学解题助手，可以通过调用工具来解决问题。

【可用工具】
{tools_section}

【ReAct 思维链 — 严格遵循以下格式】

每次回答必须遵循"思考-行动-观察"循环：

Thought: [分析问题，确定是否需要工具以及使用哪个工具]
Action: [工具名称，或 "Final Answer" 表示直接回答]
Action Input: [JSON格式的工具输入，例如 {{"query": "用户问题", "parameters": {{}}}}]
Observation: [工具执行结果的简要描述]

【重要规则】
1. 最多执行 5 次工具调用（Thought/Action/Observation 循环）
2. 工具调用失败时，说明错误原因并尝试替代方案
3. 如果问题很简单，可以直接输出 Final Answer 而不使用工具
4. 最终答案必须包含详细的解题步骤、依据和使用 LaTeX 公式

【输出格式 — 直接输出，不要加任何前缀标记】

Thought: [你的思考]
Action: [工具名或 Final Answer]
Action Input: {{"query": "...", "parameters": {{}}}}
Observation: [结果]

[如需更多循环，继续上述格式]

Final Answer: [最终解答]

"""

    def __init__(self):
        self._max_iterations: int = 5
        self._include_examples: bool = True

    def build_prompt(
        self,
        tools_description: str = "",
        base_system_prompt: str = "",
        extra_instructions: Optional[str] = None,
    ) -> ChatPromptTemplate:
        """
        构建完整的 ReAct Prompt。

        Args:
            tools_description: 工具描述文本。
            base_system_prompt: 基础 System Prompt。
            extra_instructions: 额外指令。

        Returns:
            LangChain ChatPromptTemplate。
        """
        if tools_description:
            system_content = self._build_tools_prompt(tools_description, extra_instructions)
        else:
            system_content = base_system_prompt or self.REACT_SYSTEM_PROMPT
            if extra_instructions:
                system_content += f"\n\n【额外约束】\n{extra_instructions}"

        return ChatPromptTemplate.from_messages([
            ("system", system_content),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad", optional=True),
        ])

    def _build_tools_prompt(
        self, tools_description: str, extra_instructions: Optional[str] = None
    ) -> str:
        """构建包含工具的 ReAct Prompt。"""
        prompt = self.REACT_WITH_TOOLS_PROMPT.format(
            tools_section=tools_description
        )
        if extra_instructions:
            prompt += f"\n\n【额外约束】\n{extra_instructions}"
        return prompt

    def build_with_examples(
        self,
        tools_description: str,
        examples: Optional[List[Dict[str, str]]] = None,
    ) -> ChatPromptTemplate:
        """
        构建带示例的 ReAct Prompt。

        Args:
            tools_description: 工具描述文本。
            examples: 示例对话列表，每项包含 input/Thought/Action/Observation/Final Answer。

        Returns:
            ChatPromptTemplate。
        """
        prompt = self.build_prompt(tools_description=tools_description)

        if examples is None:
            examples = [
                {
                    "input": "求 $\\int x^2 dx$",
                    "Thought": "这是一个不定积分问题，需要计算 x² 的原函数。根据基本积分公式，∫xⁿdx = x^(n+1)/(n+1) + C。",
                    "Action": "Final Answer",
                    "Observation": "",
                    "Final Answer": "$\\int x^2 dx = \\frac{x^3}{3} + C$\n\n**依据**：幂函数积分公式 $\\int x^n dx = \\frac{x^{n+1}}{n+1} + C$ (n≠-1)",
                },
                {
                    "input": "求 $\\lim_{x \\to 0} \\frac{\\sin x}{x}$",
                    "Thought": "这是一个重要极限问题。标准方法是使用洛必达法则或夹逼定理。",
                    "Action": "Final Answer",
                    "Observation": "",
                    "Final Answer": "$\\lim_{x \\to 0} \\frac{\\sin x}{x} = 1$\n\n**依据**：第一个重要极限，可用夹逼定理 $\\cos x \\leq \\frac{\\sin x}{x} \\leq 1$ 证明。",
                },
            ]

        example_messages = []
        for ex in examples:
            example_messages.append(HumanMessage(content=ex["input"]))
            thought = ex.get("Thought", "")
            action = ex.get("Action", "")
            obs = ex.get("Observation", "")
            final = ex.get("Final Answer", "")

            parts = [f"Thought: {thought}"]
            if action:
                parts.append(f"Action: {action}")
            if obs:
                parts.append(f"Observation: {obs}")
            if final:
                parts.append(f"Final Answer: {final}")

            example_messages.append(AIMessage(content="\n\n".join(parts)))

        existing_messages = list(prompt.messages)
        return ChatPromptTemplate.from_messages(existing_messages[:-2] + example_messages + existing_messages[-2:])

    @property
    def max_iterations(self) -> int:
        """最大迭代次数。"""
        return self._max_iterations

    @max_iterations.setter
    def max_iterations(self, value: int) -> None:
        """设置最大迭代次数。"""
        self._max_iterations = max(1, min(value, 20))

    @property
    def system_prompt(self) -> str:
        """获取纯 ReAct System Prompt。"""
        return self.REACT_SYSTEM_PROMPT

    @property
    def tools_prompt(self) -> str:
        """获取带工具的 ReAct System Prompt（不含占位符）。"""
        return self.REACT_WITH_TOOLS_PROMPT
