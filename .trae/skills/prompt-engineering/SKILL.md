---
name: "prompt-engineering"
description: "AI数学助手的全面Prompt工程优化方案。当用户需要优化、重构或设计LLM Agent的系统提示词时调用此技能。支持多场景路由、动态参数调整、评估框架。涵盖任务分类(T1-T5)、四层Prompt架构、上下文管理策略和A/B测试。"
---

# Prompt 工程优化方案 — AI数学助手专用

## 实施状态

| 阶段 | 状态 | 文件 |
|------|:----:|------|
| Phase 1: 核心Prompt重构 | ✅ 已完成 | `prompts/system_prompt.py` (v3.0四层架构)、`prompts/dynamic_params.py` (新增)、`prompts/react_prompt.py` (v2.0精简版) |
| Phase 2: Agent集成 | ✅ 已完成 | `agent_core/agent.py` (意图分类 + ReAct指令合并) |
| 验证测试 | ✅ 全部通过 (5/5) | `tests/test_v3_prompt_system.py` |

---

## 概述

本技能为"贸大数助"（MathAI）Agent系统提供一套完整的 **Prompt工程优化框架**。该系统基于 FastAPI + LangChain + ReAct策略模式构建，用于解决高等数学问题。

### 解决的核心问题

原系统存在**严重的僵化问题**：无论用户问什么（比如"这道题考什么知识点？"），Agent都机械地输出完整的6段式模板（约2000字），完全忽略用户的真实需求。

**根本原因：**
1. 输出模板与所有场景**硬绑定**
2. 工具调用指令**劫持**了用户意图优先级
3. 两个System Prompt（`SystemPromptManager` + `ReActPromptTemplate`）**冲突重叠**

---

## 架构：四层Prompt框架

```
┌──────────────────────────────────────────────┐
│  LAYER 0: 元指令层                           │
│  角色定义 | 安全边界 | 全局约束(始终生效)      │
├──────────────────────────────────────────────┤
│  LAYER 1: 任务路由层                         │
│  意图识别 | 场景→模板映射 | 输出策略选择规则   │
├──────────────────────────────────────────────┤
│  LAYER 2: 场景模板层                         │
│  T1知识点查询 | T2快速答案 | T3概念讲解       │
│  T4多模态适配 | T5完整解题                    │
├──────────────────────────────────────────────┤
│  LAYER 3: 动态注入层                         │
│  工具描述(按需注入) | 记忆上下文 | 用户画像    │
│  ReAct/Plan 策略指令                          │
└──────────────────────────────────────────────┘
```

---

## 任务类型分类体系（T1-T5）

| 编码 | 名称 | 触发关键词 | 响应策略 | 字数上限 |
|------|------|-----------|----------|---------|
| **T1** | 知识点查询 | "考什么知识点"、"哪章"、"涉及什么概念" | 直接回答，不展开完整解题 | ≤200字 |
| **T2** | 快速答案 | "选什么"、"答案是"、"等于多少"、"对错" | 答案+一句话依据 | ≤3行 |
| **T3** | 概念讲解 | "什么是xxx"、"xxx的定义"、"怎么理解" | 定义+条件+1个示例 | ≤500字 |
| **T4** | 多模态适配 | 上传图片+文字提问 | 识别→针对性回答 | 自适应 |
| **T5** | 完整解题 | "帮我解"、"详细步骤"、"写出过程" | 完整6段式模板 | ≤2000字 |

---

## 优化后的 System Prompt 模板

```python
OPTIMIZED_BASE_PROMPT = '''你叫"贸大数助"，是对外经济贸易大学学生开发的高数学习助手。核心使命：解决高数痛点，让每个学子轻松突破积分/微分难点。

## LAYER 0: 元指令（始终生效）

【角色铁律】
- **仅服务**《高等数学》课程内容
- **禁止用语**："显然""易得""不难看出""显然易知"
- **公式格式**：行内 `$...$`，独立 `$$...$$`

【安全边界】
- 非高数问题：礼貌说明你的能力范围仅限于高等数学
- 敏感内容：婉拒回答

---

## LAYER 1: 任务路由（第一步必须执行）

**在输出任何答案之前，先判断用户意图属于以下哪一类：**

| 类型 | 特征 | 输出策略 |
|------|------|----------|
| 🔍 **知识点问询** | 问"考什么知识点""哪章""涉及什么概念" | → **模板A：概念简洁型**（直接回答，≤200字） |
| ⚡ **快速答案** | 问"选什么""答案是""等于多少""对错" | → **模板B：快速答案型**（答案+1句依据，≤3行） |
| 💡 **概念讲解** | 问"什么是xxx""xxx的定义""怎么理解" | → **模板C：概念教学型**（定义+条件+1个示例） |
| 📝 **完整解题** | 问"帮我解""详细步骤""写出过程""求xxx" | → **模板D：详细解题型**（6段式完整流程） |
| 🖼️ **图片+提问** | 上传图片同时附带问题 | → **模板E：多模态适配型**（识别→针对性回答） |
| ❓ **其他/模糊** | 无法明确归类 | → **默认：详细解题型**，但开头确认用户意图 |

{tools_section}

{task_routing_instruction}

---

## LAYER 2: 场景模板

### 模板A：知识点简洁型（T1）
> 直接回答用户问的知识点，不展开完整解题。

**输出格式**：
**考察知识点**：[1-3个核心知识点]
**所属章节**：[章节名称]
**简要说明**：[一句话解释为什么考这个]
（总字数 ≤ 200字，不要输出完整解题流程）

---

### 模板B：快速答案型（T2）
> 给答案+一句话依据，简洁至上。

**输出格式**：
**答案**：[选项/结果]
**依据**：[一句话定理/公式名]
> 💡 如需详细步骤，请说"展开讲讲"

---

### 模板C：概念教学型（T3）
**输出格式**：
**定义**：[精确的数学定义]
**适用条件**：[什么时候能用]
**示例**：[1个简单例子，含LaTeX公式]
> 更深理解可继续提问

---

### 模板D：详细解题型（T5）【保留现有6段式】
（此处保留原有的完整解题模板，但标记为仅在T5场景使用）

{t5_full_solution_template}

---

【排版规范 - 全局通用】
1. 公式格式：行内 `$...$`，独立 `$$...$$`
2. 重点强调：关键信息用**加粗**
3. 警示标记：警示内容用 > 引用块
4. 字数控制：根据场景自适应（T1≤200, T2≤100, T3≤500, T5≤2000）
5. 每个数学步骤必须注明依据定理
'''
```

---

## 动态参数调整机制

```python
from dataclasses import dataclass
from enum import Enum
from typing import Dict


class TaskType(str, Enum):
    KNOWLEDGE_QUERY = "knowledge"      # T1 - 知识点查询
    QUICK_ANSWER = "quick"             # T2 - 快速答案
    CONCEPT_TEACHING = "concept"       # T3 - 概念讲解
    MULTIMODAL = "multimodal"          # T4 - 多模态适配
    FULL_SOLUTION = "solution"         # T5 - 完整解题
    PLANNED_SOLUTION = "planned"       # 复杂规划模式
    DEFAULT = "solution"               # 默认=完整解题


@dataclass
class LLMParams:
    temperature: float = 0.0           # 温度参数（越低越确定）
    top_p: float = 1.0                 # 核采样阈值
    max_tokens: int = 4096             # 最大输出Token数
    presence_penalty: float = 0.0      # 存在惩罚
    frequency_penalty: float = 0.0     # 频率惩罚


# 任务类型 → LLM参数映射表
TASK_PARAMS_MAP: Dict[TaskType, LLMParams] = {
    TaskType.KNOWLEDGE_QUERY: LLMParams(
        temperature=0.0,     # 极低：知识点必须精确
        top_p=1.0,
        max_tokens=800,      # 短回答
    ),
    TaskType.QUICK_ANSWER: LLMParams(
        temperature=0.0,     # 极低：答案不能错
        top_p=1.0,
        max_tokens=300,      # 极短
    ),
    TaskType.CONCEPT_TEACHING: LLMParams(
        temperature=0.1,     # 低：定义精确，举例可略灵活
        top_p=0.95,
        max_tokens=2000,
    ),
    TaskType.FULL_SOLUTION: LLMParams(
        temperature=0.0,     # 极低：数学解题必须准确一致
        top_p=1.0,
        max_tokens=4096,
    ),
    TaskType.MULTIMODAL: LLMParams(
        temperature=0.0,     # 识别+回答都要准确
        top_p=1.0,
        max_tokens=4096,
    ),
    TaskType.PLANNED_SOLUTION: LLMParams(
        temperature=0.0,
        top_p=1.0,
        max_tokens=8192,
    ),
}
```

---

## 各场景上下文注入规则

```python
CONTEXT_INJECTION_RULES = {
    "T1_knowledge": {
        "history_turns": 1,       # 仅保留最近1轮对话
        "inject_tools": False,     # 不需要工具描述
        "inject_profile": False,   # 不需要用户画像
    },
    "T2_quick": {
        "history_turns": 1,
        "inject_tools": False,
        "inject_profile": False,
    },
    "T3_concept": {
        "history_turns": 2,
        "inject_tools": False,
        "inject_profile": True,    # 根据用户薄弱点举例
    },
    "T4_multimodal": {
        "history_turns": 1,
        "inject_tools": True,      # 需要识别工具
        "inject_profile": False,
    },
    "T5_solution": {
        "history_turns": 5,        # 解题需要更多上下文
        "inject_tools": True,      # 可能需要计算工具
        "inject_profile": True,    # 根据用户水平调整讲解
    },
}
```

### 各场景Token预算分配表

| 场景 | System Prompt | 对话历史 | 工具描述 | 用户画像 | 输出预留 | 总计 |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| T1-知识点 | 2K | 1K | 0 | 0 | 0.5K | ~3.5K |
| T2-快速答案 | 2K | 1K | 0 | 0 | 0.3K | ~3.3K |
| T3-概念讲解 | 2K | 2K | 0 | 0.5K | 1K | ~5.5K |
| T4-多模态 | 2K | 1K | 1K | 0 | 2K | ~6K |
| T5-完整解题 | 2K | 5K | 1K | 1K | 4K | ~13K |
| T5-规划模式 | 2K | 10K | 2K | 1K | 8K | ~23K |

---

## 指令优先级体系

```
优先级1 (最高): 安全边界指令
  ├─ 非高数问题 → 礼貌婉拒
  └─ 敏感内容 → 不回答

优先级2: 任务路由指令  
  ├─ 用户意图判断
  └─ 模板选择

优先级3: 内容输出模板
  ├─ 模板A/B/C/D/E的具体格式
  └─ LaTeX规范、字数控制

优先级4: 工具调用规范（条件触发）
  ├─ 仅T5场景 + 需要计算/画图时
  └─ ReAct格式

优先级5: 排版美化
  ├─ 加粗、引用块
  └─ emoji标记
```

---

## 精简版ReAct策略指令

在与现有的 `agent_core/strategies/react.py` 集成时，使用这套**精简版**指令避免与主系统提示词冲突：

```python
def _build_react_instruction(self, tools):
    tool_names = [t.name for t in tools] if tools else []

    return f"""【解题工具使用规范 — 仅当需要时才使用】

可用的工具：{', '.join(tool_names) if tool_names else '无专用工具'}

工具调用格式（严格遵循）：
Action: 工具名称
Action Input: {{"query": "具体问题", "parameters": {{}}}}

**重要规则**：
1. 简单概念问题 → 直接回答，不使用工具
2. 只有计算/画图/识别才使用工具
3. 工具调用失败时说明原因并手动推导
4. 最多进行 3 次工具调用
5. 不要在Thought/Action之前加任何前缀文字
"""
```

---

## 评估测试框架

### 基准测试用例集

```python
BENCHMARK_CASES = [
    # T1 - 知识点查询
    {
        "input": "这道题考的是什么知识点？",
        "expected_type": "knowledge",
        "expected_max_length": 300,
        "should_not_contain": [
            "## 📋 一、题目确认",
            "## ✅ 二、快速答案",
            "## 📚 四、拓展练习",
        ],
    },
    # T2 - 快速答案
    {
        "input": "这道题选什么？",
        "expected_type": "quick",
        "expected_max_length": 200,
        "should_not_contain": ["详细解析", "拓展练习", "学习锦囊"],
    },
    # T3 - 概念讲解
    {
        "input": "什么是洛必达法则？",
        "expected_type": "concept",
        "expected_min_length": 100,
        "should_contain": ["定义", "条件"],
    },
    # T5 - 完整解题
    {
        "input": "帮我详细解一下这道题：求f(x)=x³-3x在[0,2]上的最值",
        "expected_type": "solution",
        "expected_min_length": 500,
        "should_contain": ["依据"],
    },
]
```

### 关键监控指标

| 指标 | 当前值 | 目标值 | 测量方式 |
|------|:---:|:---:|---------|
| 模板过度使用率 | ~95%（几乎都走T5） | <10% | 回答中是否出现"拓展练习""暖心结语"模式 |
| 快速答案平均响应长度 | ~2000字 | <200字 | 字符数统计 |
| 首次回答相关性 | ~40% | >90% | 人工标注 + LLM评分 |
| 平均Token消耗（非T5场景） | ~4000 | <800 | tiktoken计数 |
| 不必要的工具调用率 | ~30% | <5% | 日志分析 |

---

## A/B测试框架

```python
class PromptABTester:
    """
    Prompt版本A/B对比测试框架。
    
    功能：
    - 并行运行A/B两个Prompt版本
    - 自动收集对比指标
    - 统计显著性检验
    """

    async def run_test(self, test_cases, sample_size=100):
        """执行A/B测试"""
        ...

    def report(self) -> Dict:
        """生成对比报告并判定胜出版本"""
        ...
```

---

## 实施计划清单

### 第一阶段：核心Prompt重构（1-2天）

| 任务 | 文件 | 验收标准 |
|------|------|----------|
| 重写 `system_prompt.py` 为四层架构 | `prompts/system_prompt.py` | 全部5个模板通过单元测试 |
| 新增 `prompts/dynamic_params.py` | 新建文件 | 参数映射表完整可用 |
| 修改 `_create_react_strategy` 方法 | `agent_core/agent.py` | 新旧prompt合并逻辑正确 |
| 精简 `react_prompt.py` 去除重复指令 | `prompts/react_prompt.py` | ReAct指令精简到≤30行 |

### 第二阶段：动态路由实现（1-2天）

| 任务 | 文件 | 验收标准 |
|------|------|----------|
| 新增 `prompts/task_router.py` 意图识别器 | 新建文件 | 5种场景分类准确率>90% |
| 集成场景自适应上下文注入 | `agent_core/context_manager.py` | Token预算符合设计要求 |
| API响应支持 `task_type` 字段 | `main.py` | 前端可获取任务分类信息 |

### 第三阶段：测试发布（1天）

| 任务 | 文件 | 验收标准 |
|------|------|----------|
| 新增 `prompts/evaluation.py` 基准测试套件 | 新建文件 | 10+用例覆盖全部5种场景 |
| 新增 `prompts/ab_testing.py` 测试框架 | 新建文件 | A/B对比报告可正常生成 |
| CI集成自动回归测试 | GitHub Actions | PR自动触发prompt回归测试 |
| 灰度发布功能开关 | 配置文件 | 支持10%→50%→100%逐步放量 |

---

## 文件修改总览

| 序号 | 文件 | 操作 | 优先级 |
|:----:|------|------|:-----:|
| 1 | `prompts/system_prompt.py` | **重写** — 四层架构 + 5个场景模板 | ★★★★★ |
| 2 | `prompts/react_prompt.py` | **精简** — 删除重复的角色定义 | ★★★★ |
| 3 | `agent_core/agent.py` | **修改** `_create_react_strategy`, `_build_context` | ★★★★ |
| 4 | `prompts/dynamic_params.py` | **新建** — 动态参数调整模块 | ★★★ |
| 5 | `prompts/task_router.py` | **新建** — 意图识别路由器 | ★★★ |
| 6 | `prompts/evaluation.py` | **新建** — 基准测试用例 | ★★★ |
| 7 | `agent_core/context_manager.py` | **微调** — 场景自适应注入逻辑 | ★★ |

---

## 预期效果

| 指标 | 优化前 | 优化后 | 提升幅度 |
|------|:-----:|:-----:|:-------:|
| T1/T2响应长度 | ~2000字 | ~150字 | **减少93%** |
| Token消耗（非T5场景） | ~4000 | ~800 | **节省80%** |
| 模板过度使用率 | ~95% | <10% | **改善85%** |
| 用户抱怨"太啰嗦" | 频繁 | 几乎没有 | **体验大幅提升** |
| 不必要工具调用 | ~30% | <5% | **减少83%** |

---

## 使用指南

### 适用场景

1. **从零设计新的系统提示词**（AI Agent项目）
2. **重构已有的僵化Prompt**（无法响应用户意图的问题）
3. **排查Prompt相关Bug**（Agent忽略用户提问）
4. **构建多场景回复系统**（问答机器人、辅导助手等）
5. **在保证质量的前提下降低Token成本**
6. **搭建Prompt A/B测试基础设施**

### 如何应用

1. 阅读**任务类型分类**章节，根据你的领域定义自己的T1-Tn类别
2. 将**四层架构**适配到你的业务场景
3. 为每个任务类型定制**场景模板**
4. 根据你使用的模型实现**动态参数调整**
5. 用自己的测试用例搭建**评估框架**
6. 按照**实施计划清单**分阶段落地

### 反面模式（不要这样做）

- ❌ 用一个巨型模板覆盖所有场景
- ❌ 把工具调用指令放在意图路由之前
- ❐ 两个System Prompt重叠但不做去重
- ❌ 硬编码输出格式不做条件分支
- ❌ 忽略简单任务和复杂任务的Token预算差异
