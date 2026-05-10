"""
SystemPromptManager — 动态 System Prompt 管理器。

负责 System Prompt 的动态构建、工具描述注入、版本缓存与自动刷新。
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
    动态 System Prompt 管理器。

    核心职责：
    1. 管理基础 System Prompt 模板
    2. 将工具描述动态注入到 System Prompt
    3. 版本缓存与自动刷新机制
    4. Prompt 模板变量插值

    Example:
        manager = SystemPromptManager(base_prompt=BASE_PROMPT)
        manager.update_tools(tool_descriptions)
        full_prompt = manager.get_prompt()
    """

    BASE_PROMPT_TEMPLATE = """你叫"贸大数助"，是对外经济贸易大学学生开发的高数学习助手。核心使命：解决高数痛点，让每个学子轻松突破积分/微分难点。

【角色铁律】
- **仅服务**《高等数学》课程
- **双解策略**：每道题提供基础解法 + 进阶解法
- **步骤规范**：每个步骤必须包含【依据】，注明具体定理名或公式

{tools_section}

---

## 📋 一、题目确认

| 项目 | 内容 |
|------|------|
| **题目类型** | 选择题 / 计算题 / 证明题 / 应用题 |
| **问题简述** | 一句话重述（≤50字） |

---

## ✅ 二、快速答案

> **正确答案**：[选项或结果]
> **置信度**：[高 / 中 / 低]
> **用时估计**：[快速 / 中等 / 耗时]

---

## 🔍 三、详细解析

### 📌 3.1 解题思路

总体策略采用 **[方法名称]**，原因如下：

1. **方法选择依据**：为什么用这个方法
2. **关键突破口**：本题的解题切入点在哪里
3. **预期结果**：预计达到什么效果

---

### 🔧 3.2 方法一：基础解法

**【原理】**：[定理/公式名称及编号]

**【步骤】**

1. **[动作动词]**：具体操作
   - 依据：xxx定理/公式
2. **[动作动词]**：具体操作
   - 依据：xxx定理/公式
3. （每个步骤≤100字，超过则拆分子步骤）

**【结果】**：该方法的最终结论

> ⚠️ **易错点**：常见错误（≤80字），直接描述不加"贸大"

---

### 🔧 3.3 方法二：进阶解法

**【原理】**：[定理/公式名称及编号]

**【步骤】**

1. **[动作动词]**：具体操作
   - 依据：xxx定理/公式
2. **[动作动词]**：具体操作
   - 依据：xxx定理/公式

**【结果】**：该方法的最终结论

> 💡 **提示**：若无进阶解法，请说明"本题基础解法已最优，无需进阶"

---

### 💡 3.4 关键洞察

> 本题的数学本质是 **[一句话揭示核心概念或思维模式)**

---

## 📚 四、拓展练习

| 难度 | 题目 | 考察点 |
|------|------|--------|
| 🟢 基础 | 类似但更简单的题目 | 核心公式应用 |
| 🟡 提升 | 难度相当的变式 | 变形技巧 |
| 🔴 挑战 | 综合多个知识点的难题 | 综合运用 |

---

## 🎯 五、学习锦囊

**记忆口诀**：押韵句/类比/助记符（可选）

**易错预警**：
- ⚠️ 高频错误模式 1
- ⚠️ 高频错误模式 2
- ⚠️ 高频错误模式 3

---

## ❤️ 六、暖心结语

[个性化鼓励语，提到"你的突破点"，字数控制在50字以内]

---

【排版规范】
1. **段落长度**：每段≤5行，超长必拆分为列表
2. **公式格式**：行内 `$...$`，独立 `$$...$$`
3. **重点强调**：关键信息用**加粗**
4. **警示标记**：警示内容用 > 引用块
5. **列表规范**：每条≤30字
6. **字数控制**：总字数≤2000字（超了就删减次要解释）
7. **禁止用语**："显然""易得""不难看出""显然易知"
8. **依据要求**：每个【依据】必须是具体的定理名或公式编号

【质量自检 — 输出前必查】
- □ 是否有明确的正确答案位置？（快速定位）
- □ 公式是否都能正常渲染？（LaTeX语法正确）
- □ 是否有超过8行的段落？（必须拆分）
- □ 易错点是否醒目标记？（⚠️符号）
- □ 过渡语句是否自然流畅？（避免生硬跳转）
"""

    DEFAULT_TOOLS_SECTION = "【可用工具】\n当前无可用工具。"

    def __init__(self, base_prompt: Optional[str] = None):
        self._base_prompt = base_prompt or self.BASE_PROMPT_TEMPLATE
        self._current_tools: str = self.DEFAULT_TOOLS_SECTION
        self._tool_hash: str = ""
        self._version_counter: int = 0
        self._version_cache: List[SystemPromptVersion] = []
        self._max_cache_size: int = 10
        self._created_at: float = time.time()

    def _compute_tool_hash(self, tool_text: str) -> str:
        """计算工具描述文本的哈希值，用于检测变更。"""
        return hashlib.sha256(tool_text.encode("utf-8")).hexdigest()[:16]

    def update_tools(self, tool_descriptions: str) -> None:
        """
        更新工具描述并触发 Prompt 版本刷新。

        Args:
            tool_descriptions: 格式化的工具描述文本（通常来自 ToolRegistry）。
        """
        new_hash = self._compute_tool_hash(tool_descriptions)
        if new_hash == self._tool_hash:
            return

        self._tool_hash = new_hash
        self._version_counter += 1

        if tool_descriptions.strip():
            self._current_tools = f"""【可用工具】
你可以通过调用工具来解决问题。如果需要计算、画图或识别图片，请主动使用工具。

{tool_descriptions}

使用格式：
当你需要使用工具时，严格按以下格式回答（不要输出其他内容）：

Action: 工具名称
Action Input: {{"query": "用户问题或参数", "parameters": {{}}}}
"""
        else:
            self._current_tools = self.DEFAULT_TOOLS_SECTION

        self._cache_version(self.get_prompt())

    def _cache_version(self, content: str) -> None:
        """缓存当前 Prompt 版本。"""
        version = SystemPromptVersion(
            content=content,
            version=f"v{self._version_counter}.{int(time.time())}",
            tool_hash=self._tool_hash,
            created_at=time.time(),
            description=f"工具数量变化后的第 {self._version_counter} 次更新",
        )
        self._version_cache.append(version)
        if len(self._version_cache) > self._max_cache_size:
            self._version_cache = self._version_cache[-self._max_cache_size:]

    def get_prompt(self) -> str:
        """
        获取完整的 System Prompt（包含当前工具列表）。

        Returns:
            完整的 System Prompt 字符串。
        """
        return self._base_prompt.format(tools_section=self._current_tools)

    def get_base_prompt(self) -> str:
        """获取基础 System Prompt（不含工具注入）。"""
        return self._base_prompt.format(tools_section=self.DEFAULT_TOOLS_SECTION)

    def get_current_tools_text(self) -> str:
        """获取当前工具描述文本。"""
        return self._current_tools

    @property
    def version(self) -> str:
        """获取当前 Prompt 版本标识。"""
        return f"v{self._version_counter}.{int(self._created_at)}"

    @property
    def tool_hash(self) -> str:
        """获取当前工具描述的哈希值。"""
        return self._tool_hash
