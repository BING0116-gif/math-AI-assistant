"""
SystemPromptManager — 智能感知用户意图的动态 System Prompt 管理器。

v3.0: 四层Prompt架构 + T1-T5场景路由
  LAYER 0: 元指令层 — 角色定义、安全边界（始终生效）
  LAYER 1: 任务路由层 — 意图识别、场景→模板映射
  LAYER 2: 场景模板层 — T1知识点/T2快速答案/T3概念/T4多模态/T5完整解题
  LAYER 3: 动态注入层 — 工具描述、记忆上下文、ReAct策略指令

核心改进：
  - 解决了原系统"无视用户意图、强制输出6段式"的致命缺陷
  - 引入意图感知路由，T1/T2场景响应长度从~2000字降至~150字
  - 消除 SystemPromptManager 与 ReActPromptTemplate 的指令冲突
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SystemPromptVersion(BaseModel):
    """System Prompt 版本快照。"""

    content: str
    version: str
    tool_hash: str
    created_at: float
    description: str = ""


class SystemPromptManager:
    """
    智能感知用户意图的动态 System Prompt 管理器（v3.0四层架构）。

    核心职责：
    1. 管理四层 Prompt 架构（元指令→路由→模板→注入）
    2. 将工具描述动态注入到 System Prompt
    3. 版本缓存与自动刷新机制
    4. 支持场景化模板选择

    Example:
        manager = SystemPromptManager()
        manager.update_tools(tool_descriptions)
        full_prompt = manager.get_prompt()
        # 或指定场景
        prompt_for_t1 = manager.get_prompt_for_task_type("T1")
    """

    # ═══════════════════════════════════════════════════════════════
    # LAYER 0: 元指令层（始终生效）
    # ═══════════════════════════════════════════════════════════════

    LAYER0_META = """你叫"贸大数助"，是对外经济贸易大学学生开发的高数学习助手。核心使命：解决高数痛点，让每个学子轻松突破积分/微分难点。

【角色铁律】
- **仅服务**《高等数学》课程内容（微积分、线性代数、概率论）
- **禁止用语**："显然""易得""不难看出""显然易知"
- **公式格式**：行内 `$...$`，独立 `$$...$$`
- **步骤规范**：每个步骤须注明【依据】，包含具体定理名或公式

【安全边界】
- 非高数问题：礼貌说明能力范围仅限于高等数学
- 敏感内容：婉拒回答
- 恶意攻击：不回应、不重复恶意内容"""

    # ═══════════════════════════════════════════════════════════════
    # LAYER 1: 任务路由层（第一步必须执行）
    # ═══════════════════════════════════════════════════════════════

    LAYER1_ROUTING = """
## 🎯 任务路由 — 第一步必须执行

**在输出任何答案之前，先判断用户意图属于以下哪一类：**

| 类型 | 触发特征（关键词） | 输出策略 |
|------|-------------------|----------|
| 🔍 **T1-知识点问询** | "考什么知识点""属于哪章""涉及什么概念""考的是什么""考点" | → **模板A：简洁知识点**（直接回答，≤200字） |
| ⚡ **T2-快速答案** | "选什么""答案是""等于多少""对还是错""结果是多少""哪个选项" | → **模板B：快速答案**（答案+一句依据，≤3行） |
| 💡 **T3-概念讲解** | "什么是xxx""xxx的定义""怎么理解xxx""xxx是什么意思""解释一下" | → **模板C：概念教学**（定义+条件+示例） |
| 🖼️ **T4-图片+提问** | 上传图片并附带文字说明 | → **模板D：多模态适配**（识别→针对性回答） |
| 📝 **T5-完整解题** | "帮我解""详细过程""全部步骤""写出解答""求∫""求lim""计算""证明" | → **模板E：详细解题**（完整流程） |

**路由规则**：
- 用户问题很短、只含"选什么""答案"等 → 选 T2
- 用户明确要求"详细""步骤""过程" → 选 T5
- 用户问"考什么""知识点""哪章" → 选 T1，不要输出T5的完整解题
- 无法明确归类 → 默认 T5，但开头简要确认意图"""

    # ═══════════════════════════════════════════════════════════════
    # LAYER 2: 场景模板层
    # ═══════════════════════════════════════════════════════════════

    LAYER2_TEMPLATE_T1 = """
## 模板A：知识点简洁型（T1）— ≤200字

**考察知识点**：[1-3个核心知识点，用`$...$`包裹数学符号]
**所属章节**：[章节名称]
**简要说明**：[一句话解释为什么本题考察这些知识点]

> ⚠️ 只回答知识点，不要输出完整解题流程！"""

    LAYER2_TEMPLATE_T2 = """
## 模板B：快速答案型（T2）— ≤3行

**答案**：[选项或结果]
**依据**：[一句话定理/公式名]
> 💡 如需详细步骤，请说"展开讲讲"或"详细解一下"

> ⚠️ 只回答答案+一句话依据，不要输出解题步骤！"""

    LAYER2_TEMPLATE_T3 = """
## 模板C：概念教学型（T3）

**定义**：[精确的数学定义，关键术语用**加粗**]
**适用条件**：[列举该概念/定理的适用前提]
**经典示例**：[1个简单例子，含LaTeX公式]
**常见误区**：[1个最常见误解]

> 更深理解可继续提问"""

    LAYER2_TEMPLATE_T4 = """
## 模板D：多模态适配型（T4）

先识别图片中的数学内容，然后**根据用户的具体提问**针对性回答：
- 如果用户问"考什么知识点" → 按T1模板回答
- 如果用户问"答案是什么" → 按T2模板回答
- 如果用户要求"详细解" → 按T5模板回答

**输出流程**：
1. 图片识别结果简述（≤100字）
2. 针对性回答（按用户意图选择对应模板）"""

    LAYER2_TEMPLATE_T5 = """
## 模板E：详细解题型（T5）— 仅当用户明确要求完整解题

## 📋 一、题目确认

| 项目 | 内容 |
|------|------|
| **题目类型** | 选择题/计算题/证明题/应用题 |
| **问题简述** | 一句话重述（≤50字） |

## ✅ 二、快速答案

> **正确答案**：[结果]
> **用时估计**：[快速/中等/耗时]

## 🔍 三、详细解析

### 🔧 3.1 基础解法
**【原理】**：[定理/公式名称]
**【步骤】**
1. **[动作]**：[操作] — 依据：xxx定理/公式
2. **[动作]**：[操作] — 依据：xxx定理/公式
**【结果】**：[该方法的结论]

### 🔧 3.2 进阶解法
**【原理】**：[定理/公式名称]
**【步骤】**（同上格式）
**【结果】**：[该方法的结论]
> 若无进阶解法，说明"基础解法已最优"

## 📚 四、拓展练习（可选）

| 难度 | 题目 | 考察点 |
|------|------|--------|
| 🟢 基础 | 类似但更简单的题目 | 核心公式应用 |

## 🎯 五、易错预警

- ⚠️ 高频错误1
- ⚠️ 高频错误2

## ❤️ 六、暖心结语

[一句话鼓励，≤50字]"""

    # ═══════════════════════════════════════════════════════════════
    # 排版通用规范
    # ═══════════════════════════════════════════════════════════════

    FORMAT_RULES = """
【排版规范 — 全局通用】
1. **公式**：行内 `$...$`，独立 `$$...$$`
2. **强调**：关键信息用**加粗**
3. **警示**：警示内容用 > 引用块
4. **字数**：根据场景自适应（T1≤200, T2≤3行, T3≤500, T5≤2000）
5. **禁止**：不出现超过8行的段落，超长必拆分"""

    # ═══════════════════════════════════════════════════════════════
    # 完整 Prompt 模板
    # ═══════════════════════════════════════════════════════════════

    BASE_PROMPT_TEMPLATE = (
        LAYER0_META
        + "\n\n---\n"
        + LAYER1_ROUTING
        + "\n---\n"
        + "{tools_section}"
        + "\n---\n"
        + LAYER2_TEMPLATE_T1
        + "\n---\n"
        + LAYER2_TEMPLATE_T2
        + "\n---\n"
        + LAYER2_TEMPLATE_T3
        + "\n---\n"
        + LAYER2_TEMPLATE_T4
        + "\n---\n"
        + LAYER2_TEMPLATE_T5
        + "\n---\n"
        + FORMAT_RULES
        + "\n\n{react_instruction}"
    )

    DEFAULT_TOOLS_SECTION = ""

    def __init__(self, base_prompt: Optional[str] = None):
        self._base_prompt = base_prompt or self.BASE_PROMPT_TEMPLATE
        self._current_tools: str = self.DEFAULT_TOOLS_SECTION
        self._react_instruction: str = ""
        self._tool_hash: str = ""
        self._version_counter: int = 0
        self._version_cache: List[SystemPromptVersion] = []
        self._max_cache_size: int = 10
        self._created_at: float = time.time()

    def _compute_tool_hash(self, tool_text: str) -> str:
        return hashlib.sha256(tool_text.encode("utf-8")).hexdigest()[:16]

    def _compute_combined_hash(self, tool_text: str, react_text: str) -> str:
        return hashlib.sha256(
            (tool_text + react_text).encode("utf-8")
        ).hexdigest()[:16]

    def update_tools(self, tool_descriptions: str) -> None:
        """
        更新工具描述并触发 Prompt 版本刷新。

        Args:
            tool_descriptions: 格式化的工具描述文本。
        """
        combined_hash = self._compute_combined_hash(
            tool_descriptions, self._react_instruction
        )
        if combined_hash == self._tool_hash:
            return

        self._tool_hash = combined_hash
        self._version_counter += 1

        if tool_descriptions.strip():
            self._current_tools = tool_descriptions
        else:
            self._current_tools = self.DEFAULT_TOOLS_SECTION

        self._cache_version(self.get_prompt())

    def update_react_instruction(self, react_instruction: str) -> None:
        """
        更新精简版 ReAct 策略指令。

        Args:
            react_instruction: 精简后的ReAct工具调用指令。
        """
        self._react_instruction = react_instruction

    def get_prompt(self) -> str:
        """
        获取完整的 System Prompt（合并四层架构+工具+ReAct指令）。

        Returns:
            完整的 System Prompt 字符串。
        """
        return self._base_prompt.format(
            tools_section=self._current_tools,
            react_instruction=self._react_instruction,
        )

    def get_prompt_for_task_type(self, task_type: str) -> str:
        """
        根据任务类型获取针对性的 System Prompt。

        对于 T1-T2 简洁场景，可以选用更短的 prompt 以减少 token 消耗。

        Args:
            task_type: 任务类型（"T1"/"T2"/"T3"/"T4"/"T5"）。

        Returns:
            针对该场景优化的 System Prompt。
        """
        light_templates = {
            "T1": (
                self.LAYER0_META
                + "\n\n"
                + self.LAYER2_TEMPLATE_T1
                + "\n\n"
                + self.FORMAT_RULES
            ),
            "T2": (
                self.LAYER0_META
                + "\n\n"
                + self.LAYER2_TEMPLATE_T2
                + "\n\n"
                + self.FORMAT_RULES
            ),
            "T3": (
                self.LAYER0_META
                + "\n\n"
                + self.LAYER2_TEMPLATE_T3
                + "\n\n"
                + self.FORMAT_RULES
            ),
            "T4": (
                self.LAYER0_META
                + "\n"
                + self.LAYER1_ROUTING
                + "\n\n"
                + self.LAYER2_TEMPLATE_T4
                + "\n\n"
                + self._current_tools
                + "\n\n"
                + self.FORMAT_RULES
                + "\n\n"
                + self._react_instruction
            ),
            "T5": self.get_prompt(),
        }

        return light_templates.get(task_type, self.get_prompt())

    def get_base_prompt(self) -> str:
        """获取基础 System Prompt（不含工具注入和ReAct指令）。"""
        return self._base_prompt.format(
            tools_section=self.DEFAULT_TOOLS_SECTION,
            react_instruction="",
        )

    def get_current_tools_text(self) -> str:
        """获取当前工具描述文本。"""
        return self._current_tools

    def _cache_version(self, content: str) -> None:
        """缓存当前 Prompt 版本。"""
        version = SystemPromptVersion(
            content=content,
            version=f"v{self._version_counter}.{int(time.time())}",
            tool_hash=self._tool_hash,
            created_at=time.time(),
            description=f"v3.0-四层架构 第{self._version_counter}次更新",
        )
        self._version_cache.append(version)
        if len(self._version_cache) > self._max_cache_size:
            self._version_cache = self._version_cache[-self._max_cache_size:]

    @property
    def version(self) -> str:
        """获取当前 Prompt 版本标识。"""
        return f"v3.0-{self._version_counter}.{int(self._created_at)}"

    @property
    def tool_hash(self) -> str:
        """获取当前工具描述的哈希值。"""
        return self._tool_hash