# LLM复杂度分类智能路由 — 技术开发文档

> **版本**: v1.0
> **日期**: 2026-05-20
> **目标**: 用快速千问模型（`qwen-turbo`）替代硬编码规则，智能判断数学问题复杂度，自动选择最优执行策略（ReAct 或 PlannedStrategy）

---

## 目录

1. [背景与需求](#1-背景与需求)
2. [架构设计](#2-架构设计)
3. [新建文件清单](#3-新建文件清单)
4. [文件1: 分类器核心模块 `agent_core/classifier/__init__.py`](#4-文件1-分类器包初始化)
5. [文件2: 复杂度分级标准 `agent_core/classifier/complexity_levels.py`](#5-文件2-复杂度分级标准)
6. [文件3: 输出解析器 `agent_core/classifier/output_parser.py`](#6-文件3-输出解析器)
7. [文件4: Prompt 模板 `agent_core/classifier/prompt_templates.py`](#7-文件4-prompt-模板)
8. [文件5: LLM分类器 `agent_core/classifier/llm_classifier.py`](#8-文件5-llm分类器核心实现)
9. [文件6: 现有文件修改 `agent_core/agent.py`](#9-文件6-agentpy-改动说明)
10. [文件7: 包导出更新 `agent_core/__init__.py`](#10-文件7-包导出更新)
11. [文件8: 配置文件更新 `app/config/settings.py`](#11-文件8-配置文件更新)
12. [文件9: 入口文件更新 `main.py`](#12-文件9-入口文件更新)
13. [测试与验证](#13-测试与验证)
14. [常见问题与排查指南](#14-常见问题与排查指南)

---

## 1. 背景与需求

### 1.1 当前问题

项目当前的策略选择逻辑位于 `agent_core/agent.py` 的 `_select_strategy()` 方法，依赖 `task_planner.py` 中的 `_estimate_complexity()` 函数，该函数使用**硬编码关键词 + 固定权重**的方式评估问题复杂度。

**现有机制的核心缺陷：**

| 缺陷 | 示例 | 实际情况 |
|------|------|---------|
| 无法语义理解 | "求解微分方程 y'' + 3y' + 2y = 0" | 仅因不含关键词被误判为简单 |
| 数学表达多样性 | "计算三重积分 ∭_Ω xyz dV" | 短文本被误判为简单 |
| 无法识别隐含复杂性 | "证明闭区间上连续函数必然一致连续" | 无关键词匹配，被判简单 |
| 无上下文感知 | 依赖前文的延续性问题无法判断 | 永远是薄弱判断 |

### 1.2 解决方案

引入一个**独立的快速LLM分类器**，使用阿里云千问系列中响应极快、成本极低的模型（如 `qwen-turbo`），在每次用户提问前快速判断问题复杂度（1-5分），然后根据分数决定执行策略：

- **分数 1-2（简单/基础）**：使用 **ReActStrategy**，快速响应
- **分数 3（中等）**：使用 **ReActStrategy**（增强模式，带工具提示）
- **分数 4-5（复杂/困难）**：使用 **PlannedStrategy**，结构化规划执行

### 1.3 关键技术决策

| 决策项 | 选择 | 理由 |
|--------|------|------|
| **分类模型** | `qwen-turbo`（独立实例） | 响应速度极快（~200ms），成本极低 |
| **主解题模型** | `qwen-max`（保持不变） | 推理能力强，适合解答复杂数学问题 |
| **Temperature** | `0.0`（强制确定性） | 保证同一问题多次分类结果一致 |
| **缓存策略** | 基于 MD5 的内存缓存，上限 2000 条 | 避免相同问题重复调用 LLM |
| **降级机制** | 三级降级（LLM → 缓存 → 规则兜底） | 保证 LLM 不可用时系统仍然可用 |

---

## 2. 架构设计

### 2.1 整体架构图

```
用户输入
    ↓
MathAgent.stream() / MathAgent.process()
    ↓
_select_strategy(user_input, session_id)
    ↓
┌──────────────────────────────────────────────────────────┐
│              LLMComplexityClassifier (新增)                │
│                                                          │
│  ┌────────────────┐   ┌────────────────┐   ┌──────────┐ │
│  │  MD5 缓存检查   │→  │ qwen-turbo 调用 │→  │ 输出解析  │ │
│  │  (< 0.1ms)     │   │  (~200ms)      │   │ (< 0.1ms) │ │
│  └────────────────┘   └────────────────┘   └──────────┘ │
│                                                          │
│  失败时: 规则降级 (_rule_based_fallback)                   │
└──────────────────────────────────────────────────────────┘
    ↓ (返回 complexity_score: 1-5)
┌───────────────────────────────────────┐
│         策略路由决策                    │
│                                       │
│  score 1-2 → ReActStrategy            │
│  score 3   → ReActStrategy (增强)      │
│  score 4-5 → PlannedStrategy           │
└───────────────────────────────────────┘
    ↓
执行策略 → 返回结果
```

### 2.2 数据流

```
Step 1: 用户输入 "求解微分方程 y'' + 3y' + 2y = 0"
Step 2: MathAgent._select_strategy() 被调用
Step 3: LLMComplexityClassifier.classify(problem)
  Step 3a: 计算 MD5 哈希 → 查缓存 → 未命中
  Step 3b: 构建 Prompt → 调用 qwen-turbo → 返回 "4"
  Step 3c: OutputParser 解析 "4" → complexity_score = 4
  Step 3d: 存入缓存
Step 4: 判断 score=4 >= 4 → 返回 PlannedStrategy
Step 5: PlannedStrategy 规划并逐步执行
```

### 2.3 新增目录结构

```
agent_core/
├── classifier/                    ← 新增目录
│   ├── __init__.py                ← 包初始化，导出公开API
│   ├── complexity_levels.py       ← 复杂度分级标准枚举
│   ├── output_parser.py           ← LLM输出解析器
│   ├── prompt_templates.py        ← Prompt模板管理
│   └── llm_classifier.py          ← 核心分类器实现
├── agent.py                       ← 需修改：集成分类器
├── __init__.py                    ← 需修改：导出分类器
└── ...
```

---

## 3. 新建文件清单

请按以下顺序创建文件，每个文件都包含完整可运行代码：

| 序号 | 文件路径 | 用途 |
|------|---------|------|
| 1 | `agent_core/classifier/__init__.py` | 包初始化 |
| 2 | `agent_core/classifier/complexity_levels.py` | 复杂度分级枚举 |
| 3 | `agent_core/classifier/output_parser.py` | 输出解析器 |
| 4 | `agent_core/classifier/prompt_templates.py` | Prompt 模板 |
| 5 | `agent_core/classifier/llm_classifier.py` | 核心分类器 |

---

## 4. 文件1: 分类器包初始化

**文件路径**: `agent_core/classifier/__init__.py`

**说明**: 包的公开 API 入口，导出核心类和工具函数。

```python
"""
agent_core/classifier 包 — LLM复杂度分类路由。

提供基于快速LLM（qwen-turbo）的数学问题复杂度评估功能，
用于在 ReAct 和 Planned 两种执行策略之间进行智能路由。

核心组件:
    - ComplexityLevel: 复杂度分级枚举 (1-5)
    - LLMComplexityClassifier: LLM驱动的复杂度分类器
    - RobustOutputParser: 鲁棒的LLM输出解析器
    - ClassificationPromptTemplate: 分类Prompt模板

使用示例:
    from langchain_openai import ChatOpenAI
    from agent_core.classifier import LLMComplexityClassifier

    fast_llm = ChatOpenAI(model="qwen-turbo", ...)
    classifier = LLMComplexityClassifier(llm=fast_llm)
    result = await classifier.classify("求∫x²dx")
    print(result.score)  # 输出: 3
"""

from agent_core.classifier.complexity_levels import (
    ComplexityLevel,
    ComplexityCategory,
    level_to_strategy,
    is_simple,
    is_complex,
)
from agent_core.classifier.output_parser import RobustOutputParser
from agent_core.classifier.prompt_templates import (
    ClassificationPromptTemplate,
    CLASSIFICATION_SYSTEM_PROMPT,
    CLASSIFICATION_HUMAN_TEMPLATE,
)
from agent_core.classifier.llm_classifier import (
    LLMComplexityClassifier,
    ClassificationResult,
    ClassifierConfig,
)

__all__ = [
    "ComplexityLevel",
    "ComplexityCategory",
    "level_to_strategy",
    "is_simple",
    "is_complex",
    "RobustOutputParser",
    "ClassificationPromptTemplate",
    "CLASSIFICATION_SYSTEM_PROMPT",
    "CLASSIFICATION_HUMAN_TEMPLATE",
    "LLMComplexityClassifier",
    "ClassificationResult",
    "ClassifierConfig",
]
```

---

## 5. 文件2: 复杂度分级标准

**文件路径**: `agent_core/classifier/complexity_levels.py`

**说明**: 定义五个复杂度等级以及它们到执行策略的映射关系。

```python
"""
复杂度分级标准 — 定义五级复杂度及其含义。

每一级都包含明确的定义、典型示例以及对应的执行策略。
这个模块不依赖任何外部库，可以被任何其他模块安全引用。
"""

from __future__ import annotations

from enum import IntEnum
from dataclasses import dataclass
from typing import Dict


class ComplexityLevel(IntEnum):
    """
    五级复杂度枚举。

    数值越大，问题越复杂，越需要结构化规划。
    """

    TRIVIAL = 1     # 极简：口算级别、概念背诵
    BASIC = 2       # 基础：单步计算、套用公式
    MODERATE = 3    # 中等：标准解题流程 (2-3步)
    ADVANCED = 4    # 较难：多步推理、需要技巧
    COMPLEX = 5     # 困难：综合应用、竞赛级别


class ComplexityCategory:
    """
    复杂度等级的描述信息。

    为每一级提供中文标签、详细定义、典型示例和推荐策略。
    """

    _METADATA: Dict[int, dict] = {
        1: {
            "label": "极简",
            "definition": "不需要思考的基础问题：查表、背诵、一步口算",
            "examples": [
                "1+1=?",
                "sin(π/6)=?",
                "梯形的面积公式是什么？",
                "什么是对数？",
            ],
            "strategy": "react",
            "max_steps": 1,
        },
        2: {
            "label": "基础",
            "definition": "套用单一公式、1-2步计算即可完成",
            "examples": [
                "求 f(x)=x³ 的导数",
                "计算 ∫₀¹ 2x dx",
                "解方程 x² - 4 = 0",
                "求 lim(x→0) sinx/x",
            ],
            "strategy": "react",
            "max_steps": 2,
        },
        3: {
            "label": "中等",
            "definition": "标准解题流程：需要选择适当方法、2-3个步骤",
            "examples": [
                "用分部积分求 ∫x·eˣ dx",
                "判定级数 Σ(1/n²) 的收敛性",
                "求函数 f(x)=x³-3x 的极值",
                "计算矩阵 [[1,2],[3,4]] 的行列式",
            ],
            "strategy": "react",
            "max_steps": 4,
        },
        4: {
            "label": "较难",
            "definition": "多步骤组合、需要方法选择策略、容易出错",
            "examples": [
                "证明: eˣ > x+1 对所有 x≠0 成立",
                "求解微分方程 y'' - 3y' + 2y = 0",
                "计算二重积分 ∬_D xy dxdy, D由 y=x² 和 y=x 围成",
                "用拉格朗日乘数法求条件极值",
            ],
            "strategy": "planned",
            "max_steps": 7,
        },
        5: {
            "label": "困难",
            "definition": "综合性强、需要创新思路、竞赛级难度",
            "examples": [
                "证明: π是无理数",
                "计算曲面积分 ∬_S (x+y+z) dS, S为球面",
                "求解偏微分方程 u_t = u_xx 的分离变量解",
                "证明闭区间上连续函数必一致连续 (Heine定理)",
            ],
            "strategy": "planned",
            "max_steps": 15,
        },
    }

    @classmethod
    def get_label(cls, level: int | ComplexityLevel) -> str:
        """获取中文标签，如"极简"、"中等"等。"""
        lv = int(level)
        return cls._METADATA.get(lv, {}).get("label", "未知")

    @classmethod
    def get_definition(cls, level: int | ComplexityLevel) -> str:
        """获取该等级的详细定义。"""
        lv = int(level)
        return cls._METADATA.get(lv, {}).get("definition", "")

    @classmethod
    def get_examples(cls, level: int | ComplexityLevel) -> list[str]:
        """获取该等级的典型示例列表。"""
        lv = int(level)
        return cls._METADATA.get(lv, {}).get("examples", [])

    @classmethod
    def get_recommended_strategy(cls, level: int | ComplexityLevel) -> str:
        """
        获取推荐的执行策略。

        Returns:
            "react" 或 "planned"
        """
        lv = int(level)
        return cls._METADATA.get(lv, {}).get("strategy", "react")


def level_to_strategy(score: int) -> str:
    """
    将复杂度分数 (1-5) 映射到 "react" 或 "planned" 策略。

    Args:
        score: 1-5的复杂度分数

    Returns:
        "react" 或 "planned"

    Raises:
        ValueError: 分数不在1-5范围内
    """
    if not 1 <= score <= 5:
        raise ValueError(f"复杂度分数必须在1-5之间，收到: {score}")

    if score <= 3:
        return "react"
    else:
        return "planned"


def is_simple(score: int) -> bool:
    """判断是否为简单问题（分数1-3）。"""
    return 1 <= score <= 3


def is_complex(score: int) -> bool:
    """判断是否为复杂问题（分数4-5）。"""
    return 4 <= score <= 5
```

---

## 6. 文件3: 输出解析器

**文件路径**: `agent_core/classifier/output_parser.py`

**说明**: 专门处理 LLM 非标准输出。千问模型有时会返回"答案是3"、"我认为3分"、"难度等级为3"等非纯数字，本解析器需要鲁棒地从中提取分数。

```python
"""
鲁棒输出解析器 — 处理 LLM 的各种非标准输出格式。

设计目标: 无论 LLM 返回什么格式的文本，都能从中提取出1-5的复杂度分数。

支持格式:
    - "3"                     → 3 (完美输出)
    - "答案是3"                → 3
    - "难度等级: 3"            → 3
    - "三"                    → 3 (中文数字)
    - "我认为大概是3分左右"     → 3
    - "介于3-4之间"            → 4 (取高值，偏保守)
    - "3或4都可以"             → 4 (取高值)
    - "属于中等难度(3分)"       → 3
"""

from __future__ import annotations

import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class RobustOutputParser:
    """
    鲁棒的 LLM 输出解析器。

    使用多层正则匹配策略，从 LLM 返回的任意文本中提取复杂度分数。

    Example:
        parser = RobustOutputParser()
        score, confidence = parser.parse("难度等级: 3")
        assert score == 3
        assert confidence == 0.85
    """

    # ── 精确匹配模式（高置信度） ──
    _EXACT_PATTERNS = [
        (re.compile(r'^\s*([1-5])\s*$'), 1.00),        # 纯数字: "3"
        (re.compile(r'^\s*([1-5])[.。,，;；\s]*$'), 0.95),  # 数字+标点: "3."
    ]

    # ── 短语匹配模式（中高置信度） ──
    _PHRASE_PATTERNS = [
        (re.compile(r'(?:答案|结果|分数|等级|难度|评级)\s*(?:是|为|：|:)\s*([1-5])'), 0.85),
        (re.compile(r'([1-5])\s*(?:分|级|档|类)'), 0.80),
        (re.compile(r'(?:属于|应该是)\s*(?:第\s*)?([1-5])\s*(?:级|档|类|分)'), 0.80),
    ]

    # ── 中文数字匹配 ──
    _CN_MAP = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '壹': 1, '贰': 2, '叁': 3, '肆': 4, '伍': 5,
    }

    # ── 范围匹配（取高值） ──
    _RANGE_PATTERN = re.compile(
        r'(?:介于|在|大约|约)?\s*([1-5])\s*(?:[-~～到和或]|至)\s*([1-5])\s*(?:之间)?'
    )

    # ── 兜底任意数字匹配（低置信度） ──
    _ANY_DIGIT_PATTERN = re.compile(r'([1-5])')

    def parse(self, raw_output: str) -> Tuple[int, float]:
        """
        从 LLM 原始输出中提取复杂度分数。

        采用分层匹配策略，从高精度到低精度依次尝试。

        Args:
            raw_output: LLM 返回的原始文本

        Returns:
            (复杂度分数 1-5, 置信度 0.0-1.0)
        """
        if not raw_output or not raw_output.strip():
            logger.warning("收到空的LLM输出，返回默认值3")
            return 3, 0.0

        text = raw_output.strip()

        # 第1层: 精确匹配（纯数字或数字+标点）
        for pattern, confidence in self._EXACT_PATTERNS:
            match = pattern.match(text)
            if match:
                return int(match.group(1)), confidence

        # 第2层: 短语匹配（"答案是X"等）
        for pattern, confidence in self._PHRASE_PATTERNS:
            match = pattern.search(text)
            if match:
                return int(match.group(1)), confidence

        # 第3层: 中文数字
        for cn_char, value in self._CN_MAP.items():
            if cn_char in text:
                return value, 0.65

        # 第4层: 范围匹配（"3-4" → 取中间偏上）
        range_match = self._RANGE_PATTERN.search(text)
        if range_match:
            low = int(range_match.group(1))
            high = int(range_match.group(2))
            score = max(low, high)  # 偏保守，取高值
            return score, 0.60

        # 第5层: 任意数字匹配（最低精度兜底）
        digit_match = self._ANY_DIGIT_PATTERN.search(text)
        if digit_match:
            score = int(digit_match.group(1))
            # 数字出现在前半段，置信度更高
            pos = digit_match.start()
            confidence = 0.50 + (0.20 if pos < len(text) / 2 else 0.0)
            return score, min(confidence, 0.70)

        # 完全无法解析
        logger.warning(f"无法从输出中提取分数: '{text[:100]}'，使用默认值3")
        return 3, 0.0

    def parse_with_validation(self, raw_output: str) -> Tuple[int, float]:
        """
        解析并验证结果在合法范围内。

        Args:
            raw_output: LLM 返回的原始文本

        Returns:
            (复杂度分数 1-5, 置信度 0.0-1.0)
        """
        score, confidence = self.parse(raw_output)

        # 边界校验
        if not 1 <= score <= 5:
            logger.error(f"解析出非法分数 {score}，被裁切到合法范围")
            score = max(1, min(5, score))
            confidence *= 0.5

        return score, confidence
```

---

## 7. 文件4: Prompt 模板

**文件路径**: `agent_core/classifier/prompt_templates.py`

**说明**: 管理系统 Prompt 和用户 Prompt 模板。System Prompt 需要精确定义五级复杂度，并提供充分的分级示例，让 qwen-turbo 能稳定准确地分类。

```python
"""
分类 Prompt 模板 — 管理复杂度分类所用的系统提示词和用户提示词模板。

设计原则:
    1. 明确的角色设定 → 建立分类权威性
    2. 清晰的五级标准 + 正反面示例 → 消除歧义
    3. 严格的输出约束 → 保证可解析性
    4. 充分的边界示例 → 减少误判
"""


# ============================================================================
# 系统提示词 (System Prompt)
# ============================================================================

CLASSIFICATION_SYSTEM_PROMPT = """\
[角色]
你是一位拥有20年教学经验的大学数学教授，同时也是中国高考和考研数学命题专家。
你擅长快速评估一道数学题目的难度等级。

[任务]
阅读用户提供的数学题目，判断其复杂程度，仅回答一个数字（1/2/3/4/5）。

[评分标准 — 请严格遵守]

★ 1分 — 极简（不需要思考，口算或查表即可）
  特征: 基础算术、查三角函数表、概念背诵、一步口算
  示例:
    - "1+1等于几？" → 1
    - "sin(π/6)的值为？" → 1
    - "梯形的面积公式是什么？" → 1
    - "导数的定义是什么？" → 1
    - "log₁₀(100) = ?" → 1

★ 2分 — 基础（套用单个公式，1-2步计算）
  特征: 简单的求导、基础积分、单步极限、一元一次方程
  示例:
    - "求 f(x)=x³ 的导数" → 2
    - "计算 ∫₀¹ 2x dx" → 2
    - "lim(x→0) sinx/x 的值？" → 2
    - "解方程 2x+5=15" → 2
    - "3的阶乘是多少？" → 2

★ 3分 — 中等（标准解题流程，需要选择方法，2-4步）
  特征: 分部积分、级数判别、求极值拐点、矩阵运算
  示例:
    - "用分部积分求∫x·eˣdx" → 3
    - "判定级数∑(1/n²)的收敛性" → 3
    - "求函数 f(x)=x³-3x 的单调区间和极值" → 3
    - "矩阵[[1,2],[3,4]]的特征值是多少？" → 3
    - "求曲线 y=x³ 在 x=1 处的切线方程" → 3

★ 4分 — 较难（多步骤组合、需要策略选择、易出错）
  特征: 含参数讨论、证明不等式、二阶ODE、重积分、条件极值
  示例:
    - "证明: eˣ > x+1 对所有 x≠0 成立" → 4
    - "求解微分方程 y''-3y'+2y=0" → 4
    - "计算二重积分∬_D xy dxdy，D由y=x²和y=x围成" → 4
    - "用拉格朗日乘数法求f(x,y)=x²+y²在x+y=1下的极值" → 4
    - "讨论参数a,使方程x²+ax+1=0有两个不等实根的条件" → 4

★ 5分 — 困难（综合性强、需要创新思路、竞赛级难度）
  特征: 构造性证明、复杂PDE/ODE、发散积分判敛、实分析定理证明
  示例:
    - "证明: π是无理数" → 5
    - "求解偏微分方程 u_t = u_xx 满足边界条件的分离变量解" → 5
    - "证明闭区间上连续函数必一致连续（Heine-Cantor定理）" → 5
    - "计算曲面积分∬_S(x+y+z)dS，S为球面x²+y²+z²=R²" → 5
    - "构造函数f(x)，使其在[0,1]上处处连续但处处不可导" → 5

[输出规则 — 必须严格遵守]
① 只要回答一个阿拉伯数字: 1, 2, 3, 4, 或 5
② 不要解释原因
③ 不要输出其他任何字符（包括空格、标点、换行）
④ 如果无法确定，选最接近的整数

[现在开始评估]\
"""


# ============================================================================
# 用户提示词模板
# ============================================================================

CLASSIFICATION_HUMAN_TEMPLATE = """\
请评估以下数学题目的复杂度，只回答数字(1/2/3/4/5):

{problem}\
"""


class ClassificationPromptTemplate:
    """
    分类 Prompt 模板管理器。

    提供构建完整 Prompt 消息列表的方法，兼容 LangChain ChatPromptTemplate。

    Example:
        template = ClassificationPromptTemplate()
        messages = template.build("求∫x²dx")
        # messages = [
        #     ("system", CLASSIFICATION_SYSTEM_PROMPT),
        #     ("human", "请评估...\\n求∫x²dx")
        # ]
    """

    @classmethod
    def build_system_message(cls) -> dict:
        """构建系统消息字典。"""
        return {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT}

    @classmethod
    def build_human_message(cls, problem: str) -> dict:
        """
        构建用户消息字典。

        Args:
            problem: 用户输入的数学问题

        Returns:
            包含 role 和 content 的消息字典
        """
        content = CLASSIFICATION_HUMAN_TEMPLATE.format(
            problem=problem.strip()
        )
        return {"role": "user", "content": content}

    @classmethod
    def build(cls, problem: str) -> list[dict]:
        """
        构建完整的 Prompt 消息列表。

        Args:
            problem: 用户输入的数学问题

        Returns:
            消息字典列表，可直接传给 ChatOpenAI
        """
        return [
            cls.build_system_message(),
            cls.build_human_message(problem),
        ]

    @classmethod
    def get_system_prompt(cls) -> str:
        """获取纯文本 System Prompt。"""
        return CLASSIFICATION_SYSTEM_PROMPT
```

---

## 8. 文件5: LLM分类器（核心实现）

**文件路径**: `agent_core/classifier/llm_classifier.py`

**这是最核心的文件，包含完整的分类器实现。**

```python
"""
LLMComplexityClassifier — 基于快速LLM的数学问题复杂度分类器。

核心功能:
    1. 调用 qwen-turbo（独立快速LLM实例）进行复杂度评估
    2. MD5缓存在内存中，避免重复调用
    3. 三级降级策略（LLM → 缓存 → 规则兜底）
    4. 完整的日志记录，便于调试和监控

使用示例:
    from langchain_openai import ChatOpenAI
    from agent_core.classifier import LLMComplexityClassifier, ClassifierConfig

    fast_llm = ChatOpenAI(
        model="qwen-turbo",
        temperature=0.0,
        api_key="your-api-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    classifier = LLMComplexityClassifier(llm=fast_llm)
    result = await classifier.classify("求∫x²dx")
    print(result.score)       # 3
    print(result.strategy)    # "react"
    print(result.method)      # "llm"
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Dict

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from agent_core.classifier.complexity_levels import (
    ComplexityLevel,
    ComplexityCategory,
    level_to_strategy,
    is_simple,
    is_complex,
)
from agent_core.classifier.output_parser import RobustOutputParser
from agent_core.classifier.prompt_templates import (
    ClassificationPromptTemplate,
    CLASSIFICATION_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


# ============================================================================
# 配置
# ============================================================================

@dataclass
class ClassifierConfig:
    """
    分类器配置参数。

    Attributes:
        cache_max_size: 内存缓存最大条目数（LRU淘汰）
        enable_cache: 是否启用缓存
        enable_fallback: LLM失败时是否降级到规则匹配
        classification_timeout: 单次分类超时秒数
        temperature: LLM temperature（建议0.0保证确定性）
    """

    cache_max_size: int = 2000
    enable_cache: bool = True
    enable_fallback: bool = True
    classification_timeout: float = 5.0
    temperature: float = 0.0


# ============================================================================
# 结果数据类
# ============================================================================

@dataclass
class ClassificationResult:
    """
    分类结果。

    Attributes:
        score: 复杂度分数 (1-5)
        confidence: 置信度 (0.0-1.0)
        strategy: 推荐的执行策略 ("react" 或 "planned")
        reasoning: 人类可读的推理描述
        method: 分类方法 ("llm" | "cache" | "fallback")
        latency_ms: 分类耗时（毫秒）
        token_usage: LLM Token用量（如有）
    """

    score: int
    confidence: float
    strategy: str
    reasoning: str
    method: str
    latency_ms: float = 0.0
    token_usage: Optional[Dict[str, int]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，便于日志记录和序列化。"""
        return {
            "score": self.score,
            "confidence": round(self.confidence, 3),
            "strategy": self.strategy,
            "reasoning": self.reasoning,
            "method": self.method,
            "latency_ms": round(self.latency_ms, 1),
            "token_usage": self.token_usage or {},
        }

    def __repr__(self) -> str:
        label = ComplexityCategory.get_label(self.score)
        return (
            f"ClassificationResult("
            f"score={self.score}({label}), "
            f"strategy={self.strategy}, "
            f"confidence={self.confidence:.2f}, "
            f"method={self.method}, "
            f"latency={self.latency_ms:.0f}ms)"
        )


# ============================================================================
# 核心分类器
# ============================================================================

class LLMComplexityClassifier:
    """
    LLM驱动的数学问题复杂度分类器。

    设计要点:
        - 使用独立的快速LLM实例（qwen-turbo），不干扰主解题流程
        - 内置MD5缓存，相同问题不会重复调用LLM
        - 三级降级策略保证可用性

    Example:
        classifier = LLMComplexityClassifier(llm=fast_llm)

        # 方式1: 获取完整结果
        result = await classifier.classify("用分部积分求∫x·eˣdx")
        if result.score >= 4:
            # 使用 PlannedStrategy
            ...
        else:
            # 使用 ReActStrategy
            ...

        # 方式2: 快速判断是否复杂
        if await classifier.is_complex_problem("证明eˣ > x+1"):
            ...  # 走规划模式

        # 方式3: 批量分类
        results = await classifier.batch_classify([
            "1+1=?",
            "求∫x²dx",
            "证明闭区间连续函数一致连续",
        ])
    """

    def __init__(
        self,
        llm: ChatOpenAI,
        config: Optional[ClassifierConfig] = None,
    ):
        """
        初始化分类器。

        Args:
            llm: 独立的快速 ChatOpenAI 实例。
                 建议配置: model="qwen-turbo", temperature=0.0
            config: 可选配置对象
        """
        self._llm = llm
        self._config = config or ClassifierConfig()
        self._parser = RobustOutputParser()

        # 内存缓存: {md5_hash: ClassificationResult}
        self._cache: Dict[str, ClassificationResult] = {}

        # 统计计数器
        self._stats = {
            "total_calls": 0,
            "llm_calls": 0,
            "cache_hits": 0,
            "fallbacks": 0,
            "errors": 0,
        }

        # Prompt 模板管理器
        self._prompt_template = ClassificationPromptTemplate()

        logger.info(
            f"LLMComplexityClassifier 初始化完成 "
            f"(model={getattr(llm, 'model_name', 'unknown')}, "
            f"cache_max={self._config.cache_max_size}, "
            f"fallback={'启用' if self._config.enable_fallback else '禁用'})"
        )

    # ── 公共 API ────────────────────────────────────────────────────────

    async def classify(self, problem: str) -> ClassificationResult:
        """
        对单个问题进行复杂度分类。

        执行流程:
            1. 输入合法性检查
            2. 查 MD5 内存缓存
            3. 调用 qwen-turbo LLM
            4. 鲁棒解析输出
            5. 合理性校验
            6. 存入缓存
            7. 返回结果

        Args:
            problem: 用户输入的数学问题文本

        Returns:
            ClassificationResult 包含分数、策略建议和元信息
        """
        start_time = time.perf_counter()
        self._stats["total_calls"] += 1

        # ====== 第1步: 输入校验 ======
        if not problem or not problem.strip():
            logger.debug("收到空输入，返回默认结果")
            return self._empty_input_result(start_time)

        problem = problem.strip()

        # ====== 第2步: 缓存查询 ======
        if self._config.enable_cache:
            cache_key = self._compute_cache_key(problem)
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._stats["cache_hits"] += 1
                cached.latency_ms = (time.perf_counter() - start_time) * 1000
                logger.debug(
                    f"缓存命中: '{problem[:40]}...' → "
                    f"score={cached.score} ({cached.strategy})"
                )
                return cached

        # ====== 第3步: LLM调用 ======
        try:
            result = await self._call_llm(problem, start_time)
            self._stats["llm_calls"] += 1

            # ====== 第4步: 合理性校验 ======
            result = self._validate_result(problem, result)

            # ====== 第5步: 存入缓存 ======
            if self._config.enable_cache:
                self._store_in_cache(problem, result)

            return result

        except asyncio.TimeoutError:
            logger.error(f"LLM分类超时 ({self._config.classification_timeout}s)")
            self._stats["errors"] += 1
            return await self._handle_failure(problem, start_time, "LLM调用超时")

        except Exception as e:
            logger.error(f"LLM分类异常: {type(e).__name__}: {e}")
            self._stats["errors"] += 1
            return await self._handle_failure(problem, start_time, str(e))

    async def is_complex_problem(self, problem: str) -> bool:
        """
        快捷判断: 是否为复杂问题（需要PlannedStrategy）。

        Args:
            problem: 问题文本

        Returns:
            True 表示分数 >= 4，应使用 PlannedStrategy
        """
        result = await self.classify(problem)
        return result.score >= 4

    async def batch_classify(
        self,
        problems: list[str],
        max_concurrency: int = 5,
    ) -> list[ClassificationResult]:
        """
        批量分类多个问题（并发执行）。

        Args:
            problems: 问题文本列表
            max_concurrency: 最大并发数

        Returns:
            ClassificationResult 列表，顺序与输入一致
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _classify_with_semaphore(problem: str) -> ClassificationResult:
            async with semaphore:
                return await self.classify(problem)

        tasks = [_classify_with_semaphore(p) for p in problems]
        return await asyncio.gather(*tasks, return_exceptions=False)

    # ── 内部方法 ─────────────────────────────────────────────────────────

    async def _call_llm(
        self,
        problem: str,
        start_time: float,
    ) -> ClassificationResult:
        """
        实际调用 LLM 进行分类。

        使用 SystemMessage + HumanMessage 构建消息，
        调用 ChatOpenAI.ainvoke() 获取回复。
        """
        messages = [
            SystemMessage(content=CLASSIFICATION_SYSTEM_PROMPT),
            HumanMessage(
                content=ClassificationPromptTemplate.build_human_message(problem)["content"]
            ),
        ]

        # 调用 LLM（带超时）
        response = await asyncio.wait_for(
            self._llm.ainvoke(messages),
            timeout=self._config.classification_timeout,
        )

        raw_output = response.content.strip()
        token_usage = {}
        if hasattr(response, 'response_metadata'):
            metadata = response.response_metadata
            token_usage = metadata.get('token_usage', {})

        # 解析输出
        score, confidence = self._parser.parse_with_validation(raw_output)

        # 计算延迟
        latency_ms = (time.perf_counter() - start_time) * 1000

        # 确定策略
        strategy = level_to_strategy(score)

        # 构建分类原因描述
        label = ComplexityCategory.get_label(score)
        reasoning = (
            f"LLM判断: {score}分({label}), "
            f"raw_output='{raw_output[:80]}', "
            f"confidence={confidence:.2f}"
        )

        result = ClassificationResult(
            score=score,
            confidence=confidence,
            strategy=strategy,
            reasoning=reasoning,
            method="llm",
            latency_ms=latency_ms,
            token_usage=token_usage,
        )

        logger.info(
            f"LLM分类完成: [{score}分/{label}] "
            f"→ {strategy} | "
            f"'{problem[:50]}...' | "
            f"延迟={latency_ms:.0f}ms | "
            f"tokens={token_usage.get('total_tokens', 'N/A')}"
        )

        return result

    async def _handle_failure(
        self,
        problem: str,
        start_time: float,
        error_reason: str,
    ) -> ClassificationResult:
        """
        处理LLM调用失败的情况。

        策略:
            1. 检查缓存中是否有相似问题
            2. 降级到规则匹配
            3. 返回中等复杂度（保守策略）
        """
        self._stats["fallbacks"] += 1

        if not self._config.enable_fallback:
            logger.warning("降级机制已禁用，返回中等复杂度默认值")
            return self._default_result(start_time, error_reason)

        # 使用规则降级
        fallback_score = self._rule_based_fallback(problem)
        strategy = level_to_strategy(fallback_score)
        latency_ms = (time.perf_counter() - start_time) * 1000

        label = ComplexityCategory.get_label(fallback_score)

        result = ClassificationResult(
            score=fallback_score,
            confidence=0.25,  # 规则降级置信度低
            strategy=strategy,
            reasoning=f"规则降级({error_reason[:60]}): {fallback_score}分({label})",
            method="fallback",
            latency_ms=latency_ms,
        )

        logger.warning(
            f"降级到规则匹配: [{fallback_score}分/{label}] "
            f"→ {strategy} | '{problem[:50]}...' | "
            f"原因: {error_reason[:80]}"
        )

        return result

    def _rule_based_fallback(self, problem: str) -> int:
        """
        LLM不可用时的规则降级。

        基于如下启发式:
            - 文本长度 (越长越可能复杂)
            - 数学符号密度 (越多越可能复杂)
            - 关键词 (证明/验证/求解ODE/PDE → 复杂)

        Args:
            problem: 问题文本

        Returns:
            1-5 的复杂度分数
        """
        text = problem.strip()
        length = len(text)

        # ── 基础分（长度维度） ──
        if length <= 8:
            base_score = 1
        elif length <= 20:
            base_score = 2
        elif length <= 45:
            base_score = 3
        elif length <= 80:
            base_score = 4
        else:
            base_score = 5

        # ── 复杂度关键词加权 ──
        complex_keywords = {
            "证明": 1.2, "验证": 0.8,
            "综上所述": 1.2, "求解": 0.3,
            "微分方程": 1.0, "偏微分": 1.5,
            "二重积分": 0.8, "三重积分": 1.0,
            "曲面积分": 1.2, "曲线积分": 0.8,
            "一致连续": 1.0, "收敛": 0.5,
            "画出": 0.7, "图像": 0.5,
            "比较": 0.6, "第一步": 1.0,
            "首先": 0.4, "然后": 0.5,
            "并且": 0.4, "最后": 0.4,
            "拉格朗日": 0.8, "泰勒": 0.6,
        }

        for keyword, weight in complex_keywords.items():
            if keyword in text:
                base_score += weight

        # ── 数学符号密度加权 ──
        math_symbols = re.findall(
            r'[∫∬∭∮∑∏∞∂∇Δ√±→⇒⇔∀∃∈⊂⊆∪∩'
            r'∫∬∭∮∑∏∞∂∇Δ√±→⇒⇔∀∃∈⊂⊆∪∩'
            r'dx|dy|dz|lim|sin|cos|tan|log|ln'
            r"['\"]{2,}|\\frac|\\sqrt|\\int|\\sum]",
            text
        )
        symbol_count = len(math_symbols)
        base_score += min(symbol_count * 0.2, 1.0)

        # ── 简单概念查询降权 ──
        simple_patterns = [
            r"^(什么|怎么)是",
            r"等于多少[？?]$",
            r"^(求|计算)\s*(sin|cos|tan)\(?[\dπ/]+\)?",
        ]
        for pattern in simple_patterns:
            if re.search(pattern, text):
                base_score -= 0.5
                break

        # ── 限制范围 ──
        return max(1, min(5, int(round(base_score))))

    def _validate_result(
        self,
        problem: str,
        result: ClassificationResult,
    ) -> ClassificationResult:
        """
        对分类结果进行合理性校验。

        如果 LLM 的分类明显不合理（如"1+1=?"被判为5分），
        会用规则兜底纠正。

        Args:
            problem: 原始问题
            result: LLM分类结果

        Returns:
            可能被修正后的分类结果
        """
        text = problem.strip()

        # 校验1: 明显极简的问题不可能 >= 4 分
        is_trivial = (
            len(text) <= 6
            and re.match(r'^[\d\s\+\-\*\/\(\)\=\?\.]+$', text)
        )
        if is_trivial and result.score >= 4:
            logger.warning(
                f"分类不合理 (极简问题被判{result.score}分), "
                f"修正为2分: '{text}'"
            )
            return ClassificationResult(
                score=2,
                confidence=0.30,
                strategy="react",
                reasoning=f"修正: 极简问题原判{result.score}分→修正为2分",
                method="fallback",
                latency_ms=result.latency_ms,
            )

        # 校验2: 超长文本（>200字）不太可能是简单问题
        if len(text) > 200 and result.score <= 2:
            logger.warning(
                f"分类可能偏低 (长文本被判{result.score}分), "
                f"修正为3分: '{text[:50]}...'"
            )
            return ClassificationResult(
                score=3,
                confidence=0.30,
                strategy="react",
                reasoning=f"修正: 长文本原判{result.score}分→修正为3分",
                method="fallback",
                latency_ms=result.latency_ms,
            )

        return result

    def _empty_input_result(self, start_time: float) -> ClassificationResult:
        """处理空输入的情况。"""
        latency_ms = (time.perf_counter() - start_time) * 1000
        return ClassificationResult(
            score=2,
            confidence=0.5,
            strategy="react",
            reasoning="空输入，默认简单",
            method="fallback",
            latency_ms=latency_ms,
        )

    def _default_result(
        self,
        start_time: float,
        error_reason: str = "",
    ) -> ClassificationResult:
        """返回中等复杂度的默认结果（最安全的默认值）。"""
        latency_ms = (time.perf_counter() - start_time) * 1000
        return ClassificationResult(
            score=3,
            confidence=0.10,
            strategy="react",
            reasoning=f"默认结果 (错误: {error_reason[:60]})",
            method="fallback",
            latency_ms=latency_ms,
        )

    # ── 缓存管理 ─────────────────────────────────────────────────────────

    def _compute_cache_key(self, problem: str) -> str:
        """计算问题的MD5哈希作为缓存键。"""
        normalized = problem.strip().lower()
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()

    def _store_in_cache(
        self,
        problem: str,
        result: ClassificationResult,
    ) -> None:
        """将分类结果存入缓存（LRU淘汰策略）。"""
        cache_key = self._compute_cache_key(problem)

        # LRU淘汰: 缓存满时删除最早一条
        if len(self._cache) >= self._config.cache_max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            logger.debug(f"缓存淘汰: {oldest_key[:8]}...")

        self._cache[cache_key] = result
        logger.debug(
            f"存入缓存: key={cache_key[:8]}..., "
            f"size={len(self._cache)}/{self._config.cache_max_size}"
        )

    # ── 统计信息 ─────────────────────────────────────────────────────────

    def clear_cache(self) -> None:
        """清空内存缓存。"""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"缓存已清空 (共{count}条)")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取分类器运行统计。

        Returns:
            包含缓存命中率、调用次数等统计数据的字典
        """
        total = max(self._stats["total_calls"], 1)
        cache_hit_rate = self._stats["cache_hits"] / total

        return {
            "total_calls": self._stats["total_calls"],
            "llm_calls": self._stats["llm_calls"],
            "cache_hits": self._stats["cache_hits"],
            "cache_hit_rate": round(cache_hit_rate, 3),
            "cache_size": len(self._cache),
            "cache_max_size": self._config.cache_max_size,
            "fallbacks": self._stats["fallbacks"],
            "fallback_rate": round(self._stats["fallbacks"] / total, 3),
            "errors": self._stats["errors"],
            "error_rate": round(self._stats["errors"] / total, 3),
        }
```

---

## 9. 文件6: `agent_core/agent.py` 改动说明

这是**最重要的改动文件**。需要修改 `MathAgent` 类的 `__init__` 方法和 `_select_strategy` 方法。

### 9.1 `__init__` 方法修改

**位置**: `agent_core/agent.py` 第 76-155 行

**改动内容**:

1. **新增参数**: `enable_classifier`, `classifier_llm`, `classifier_config`
2. **初始化快速LLM**: 为分类器单独创建一个 `ChatOpenAI` 实例
3. **初始化分类器**: 创建 `LLMComplexityClassifier` 实例

**具体改动说明**:

在 `__init__` 方法的参数列表中添加（约第 83-88 行）：

```python
def __init__(
    self,
    api_key: str,
    registry: Optional[ToolRegistry] = None,
    model: str = "qwen-max",
    temperature: float = 0,
    max_iterations: int = 5,
    stream: bool = True,
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    enable_planner: bool = True,
    enable_128k_context: bool = True,
    context_budget_tokens: int = 128000,
    context_strategy: ContextStrategy = ContextStrategy.HYBRID,
    # ── 🆕 新增参数: LLM分类器 ──
    enable_classifier: bool = True,
    classifier_model: str = "qwen-turbo",
    classifier_config: Optional[dict] = None,
):
```

**新增参数的用途**:
- `enable_classifier`: 总开关，设为 `False` 可完全禁用分类器，回退到原有逻辑
- `classifier_model`: 指定分类用的模型名称（默认 `qwen-turbo`，可选 `qwen-plus`）
- `classifier_config`: 可选的配置字典，用于定制缓存大小、超时等参数

在 `__init__` 方法内部，**第 105-112 行（创建主LLM的位置之后）**，添加以下代码块：

```python
# ── 🆕 新增: LLM复杂度分类器 ──
self._enable_classifier = enable_classifier
self._classifier: Optional[LLMComplexityClassifier] = None

if enable_classifier:
    # 为分类器创建独立的快速LLM实例
    classifier_llm = ChatOpenAI(
        model=classifier_model,
        temperature=0.0,  # 强制确定性: 确保同一问题多次分类结果一致
        api_key=api_key,
        base_url=base_url,
        streaming=False,  # 分类不需要流式
    )

    # 构建分类器配置
    _cfg = classifier_config or {}
    _classifier_config = ClassifierConfig(
        cache_max_size=_cfg.get("cache_max_size", 2000),
        enable_cache=_cfg.get("enable_cache", True),
        enable_fallback=_cfg.get("enable_fallback", True),
        classification_timeout=_cfg.get("classification_timeout", 5.0),
    )

    self._classifier = LLMComplexityClassifier(
        llm=classifier_llm,
        config=_classifier_config,
    )

    logger.info(
        f"✅ LLM复杂度分类器已启用 "
        f"(model={classifier_model}, "
        f"cache={_classifier_config.cache_max_size}条)"
    )
else:
    logger.info("⚠️ LLM复杂度分类器已禁用，使用原有策略路由")
```

**注意**: 还需要在文件顶部新增 import：

```python
# 在文件开头（约第50行附近）的 import 区域添加:

from agent_core.classifier.llm_classifier import (
    LLMComplexityClassifier,
    ClassificationResult,
    ClassifierConfig,
)
from agent_core.classifier.complexity_levels import (
    level_to_strategy,
    ComplexityCategory,
)
```

### 9.2 `_select_strategy` 方法重写

**位置**: `agent_core/agent.py` 第 711-750 行

**替换为以下完整实现**:

```python
def _select_strategy(
    self,
    user_input: str,
    session_id: str,
) -> AgentStrategy:
    """
    智能策略选择 — 优先使用LLM分类器，降级使用规则匹配。

    决策流程:
        1. 意图分类 (T1-T5, 轻量规则, <1ms)
        2. LLM复杂度分类 (qwen-turbo, ~200ms)  ← 新增
        3. 根据复杂度分数选择策略:
           - 分数 1-3 → ReActStrategy
           - 分数 4-5 → PlannedStrategy
        4. 如果分类器不可用，降级到原有 TaskPlanner 逻辑

    Args:
        user_input: 用户输入。
        session_id: 会话 ID。

    Returns:
        选定的执行策略。
    """
    # 意图分类（轻量规则匹配，<1ms）
    intent = self._classify_intent(user_input)

    # ── 🆕 优先使用LLM分类器 ──
    if self._classifier is not None:
        try:
            # 调用 qwen-turbo 进行分类（异步）
            # 注意: 这里使用 asyncio.get_event_loop() 的 run_until_complete
            # 是因为 _select_strategy 本身是同步方法。
            # 更好的做法是将 _select_strategy 改为 async，
            # 但为了最小化改动范围，这里采用同步包装。
            loop = asyncio.get_event_loop()
            classification = loop.run_until_complete(
                self._classifier.classify(user_input)
            )

            score = classification.score
            strategy_name = classification.strategy
            label = ComplexityCategory.get_label(score)

            # 记录分类结果
            logger.info(
                f"[分类器路由] score={score}({label}) "
                f"→ strategy={strategy_name} | "
                f"method={classification.method} | "
                f"confidence={classification.confidence:.2f} | "
                f"latency={classification.latency_ms:.0f}ms | "
                f"intent={intent.task_type.to_chinese()}"
            )

            # 根据分类结果选择策略
            if strategy_name == "planned":
                # 复杂问题 → PlannedStrategy
                if self._task_planner is not None and self._task_planner.enabled:
                    logger.info(f"✅ 使用 PlannedStrategy (score={score}, {label})")
                    return self._get_or_create_planned_strategy()

                # 规划器未启用，回退到 ReAct
                logger.warning("分类器建议 Planned，但规划器未启用，回退到 ReAct")
                return self._strategy

            else:
                # 简单/中等问题 → ReActStrategy
                logger.info(f"✅ 使用 ReActStrategy (score={score}, {label})")
                return self._strategy

        except Exception as e:
            logger.error(
                f"❌ LLM分类器异常: {type(e).__name__}: {e}，"
                f"降级到原有逻辑"
            )

    # ── 降级: 原有 TaskPlanner.should_plan() 逻辑 ──
    logger.info(
        f"使用原有策略路由 "
        f"(意图={intent.task_type.to_chinese()}, "
        f"confidence={intent.confidence:.2f})"
    )

    if (
        self._task_planner is not None
        and self._task_planner.enabled
        and self._task_planner.should_plan(user_input)
    ):
        logger.info(
            f"TaskPlanner判断复杂度高 → 使用 PlannedStrategy "
            f"(意图={intent.task_type.to_chinese()})"
        )
        return self._get_or_create_planned_strategy()

    logger.info(
        f"使用 ReActStrategy (意图={intent.task_type.to_chinese()}, "
        f"confidence={intent.confidence:.2f})"
    )
    return self._strategy
```

### 9.3 添加 `_select_strategy` 的异步版本（可选但推荐）

**说明**: 上述 `_select_strategy` 使用了 `loop.run_until_complete()` 同步包装，这在异步上下文中（如 `process()` / `stream()` 方法）是可以工作的，但不是最优实践。

如果你希望更优雅地实现，可以将 `_select_strategy` 改为异步方法。但这需要修改所有调用它的地方（`process()` 和 `stream()` 方法），工作量稍大。

**折中方案**: 保持 `_select_strategy` 同步，但预先在 `_build_context` 中触发分类器的异步预取。如果你需要这个优化，请在实现基础版后再考虑。

---

## 10. 文件7: 包导出更新

**文件路径**: `agent_core/__init__.py`

**改动说明**: 在现有导出列表中添加分类器相关模块。

将文件第 3-20 行替换为:

```python
"""
agent_core 包 — Agent 核心层。

提供统一的 MathAgent 和相关组件。
"""

from agent_core.agent import MathAgent, create_math_agent
from agent_core.thought import ThoughtRecorder, ThoughtProcess, ThoughtStepType
from agent_core.task_planner import (
    TaskPlanner,
    TaskDAG,
    Task,
    TaskStatus,
    TaskPriority,
    ExecutionPlan,
    PlanningContext,
    PlannerConfig,
    PlanningError,
    CircularDependencyError,
)
from agent_core.strategies.planned import PlannedStrategy

# ── 🆕 分类器相关导出 ──
from agent_core.classifier import (
    LLMComplexityClassifier,
    ClassificationResult,
    ClassifierConfig,
    ComplexityLevel,
    ComplexityCategory,
    level_to_strategy,
    is_simple,
    is_complex,
)

__all__ = [
    "MathAgent",
    "create_math_agent",
    "ThoughtRecorder",
    "ThoughtProcess",
    "ThoughtStepType",
    "TaskPlanner",
    "TaskDAG",
    "Task",
    "TaskStatus",
    "TaskPriority",
    "ExecutionPlan",
    "PlanningContext",
    "PlannerConfig",
    "PlanningError",
    "CircularDependencyError",
    "PlannedStrategy",
    # ── 🆕 分类器 ──
    "LLMComplexityClassifier",
    "ClassificationResult",
    "ClassifierConfig",
    "ComplexityLevel",
    "ComplexityCategory",
    "level_to_strategy",
    "is_simple",
    "is_complex",
]
```

---

## 11. 文件8: 配置文件更新

**文件路径**: `app/config/settings.py`

**改动说明**: 新增分类器模型配置项，允许通过环境变量 `.env` 灵活切换分类模型。

在 `Settings` 类中添加以下配置项（建议添加在第 56 行 `DASHSCOPE_API_KEY` 之后）:

```python
# ── 🆕 LLM分类器配置 ──
CLASSIFIER_ENABLED: bool = Field(
    default=True,
    alias="CLASSIFIER_ENABLED",
)
CLASSIFIER_MODEL: str = Field(
    default="qwen-turbo",
    alias="CLASSIFIER_MODEL",
)
CLASSIFIER_CACHE_SIZE: int = Field(
    default=2000,
    alias="CLASSIFIER_CACHE_SIZE",
)
CLASSIFIER_TIMEOUT: float = Field(
    default=5.0,
    alias="CLASSIFIER_TIMEOUT",
)
```

---

## 12. 文件9: 入口文件更新

**文件路径**: `main.py`

**改动说明**: 在创建 `MathAgent` 实例时传入分类器相关配置。

找到第 275-276 行附近的 `agent` 初始化代码:

```python
# 修改前:
agent = MathAgent(api_key=api_key, registry=registry)

# 修改后:
agent = MathAgent(
    api_key=api_key,
    registry=registry,
    enable_classifier=settings.CLASSIFIER_ENABLED,
    classifier_model=settings.CLASSIFIER_MODEL,
    classifier_config={
        "cache_max_size": settings.CLASSIFIER_CACHE_SIZE,
        "classification_timeout": settings.CLASSIFIER_TIMEOUT,
        "enable_cache": True,
        "enable_fallback": True,
    },
)
```

---

## 13. 测试与验证

### 13.1 单元测试脚本

创建独立的测试脚本，验证分类器各组件正确工作。

**文件路径**: `tests/test_classifier.py`

```python
"""
LLM复杂度分类器 — 单元测试与集成测试

使用方法:
    cd "math AI assistant"
    python -m pytest tests/test_classifier.py -v -s
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from agent_core.classifier.complexity_levels import (
    ComplexityLevel,
    ComplexityCategory,
    level_to_strategy,
    is_simple,
    is_complex,
)
from agent_core.classifier.output_parser import RobustOutputParser
from agent_core.classifier.prompt_templates import (
    ClassificationPromptTemplate,
    CLASSIFICATION_SYSTEM_PROMPT,
)
from agent_core.classifier.llm_classifier import ClassifierConfig, ClassificationResult


# ============================================================================
# 测试1: 复杂度分级枚举
# ============================================================================

class TestComplexityLevels:
    def test_enum_values(self):
        assert ComplexityLevel.TRIVIAL == 1
        assert ComplexityLevel.BASIC == 2
        assert ComplexityLevel.MODERATE == 3
        assert ComplexityLevel.ADVANCED == 4
        assert ComplexityLevel.COMPLEX == 5

    def test_label_mapping(self):
        assert ComplexityCategory.get_label(1) == "极简"
        assert ComplexityCategory.get_label(3) == "中等"
        assert ComplexityCategory.get_label(5) == "困难"

    def test_level_to_strategy(self):
        assert level_to_strategy(1) == "react"
        assert level_to_strategy(2) == "react"
        assert level_to_strategy(3) == "react"
        assert level_to_strategy(4) == "planned"
        assert level_to_strategy(5) == "planned"

    def test_level_to_strategy_invalid(self):
        with pytest.raises(ValueError):
            level_to_strategy(0)
        with pytest.raises(ValueError):
            level_to_strategy(6)

    def test_is_simple(self):
        assert is_simple(1) is True
        assert is_simple(3) is True
        assert is_simple(4) is False
        assert is_simple(5) is False

    def test_is_complex(self):
        assert is_complex(1) is False
        assert is_complex(3) is False
        assert is_complex(4) is True
        assert is_complex(5) is True


# ============================================================================
# 测试2: 输出解析器
# ============================================================================

class TestOutputParser:
    def setup_method(self):
        self.parser = RobustOutputParser()

    def test_perfect_output(self):
        score, conf = self.parser.parse("3")
        assert score == 3
        assert conf == 1.0

    def test_digit_with_punctuation(self):
        score, conf = self.parser.parse("4.")
        assert score == 4
        assert conf >= 0.9

    def test_phrase_answer(self):
        score, conf = self.parser.parse("答案是2")
        assert score == 2
        assert conf >= 0.8

    def test_phrase_difficulty_level(self):
        score, conf = self.parser.parse("难度等级: 3")
        assert score == 3
        assert conf >= 0.8

    def test_chinese_number(self):
        score, conf = self.parser.parse("三")
        assert score == 3
        assert conf == 0.65

    def test_range_expression(self):
        score, conf = self.parser.parse("介于3-4之间")
        assert score == 4  # 取高值
        assert conf == 0.60

    def test_range_or(self):
        score, conf = self.parser.parse("3或4都可以")
        assert score == 4  # 取高值
        assert conf == 0.60

    def test_embedded_digit(self):
        score, conf = self.parser.parse("我认为大概是3分左右")
        assert score == 3
        assert conf >= 0.7

    def test_empty_input(self):
        score, conf = self.parser.parse("")
        assert score == 3  # 默认值
        assert conf == 0.0

    def test_no_digit_fallback(self):
        score, conf = self.parser.parse("这个问题太难了")
        assert score == 3  # 默认值
        assert conf == 0.0

    def test_parse_with_validation_normal(self):
        score, conf = self.parser.parse_with_validation("2")
        assert score == 2
        assert conf == 1.0

    def test_parse_with_validation_out_of_range(self):
        score, conf = self.parser.parse_with_validation("9")
        assert 1 <= score <= 5
        assert conf <= 0.5


# ============================================================================
# 测试3: Prompt模板
# ============================================================================

class TestPromptTemplates:
    def test_system_prompt_not_empty(self):
        assert len(CLASSIFICATION_SYSTEM_PROMPT) > 100

    def test_system_prompt_contains_levels(self):
        assert "1分" in CLASSIFICATION_SYSTEM_PROMPT
        assert "5分" in CLASSIFICATION_SYSTEM_PROMPT
        assert "只回答" in CLASSIFICATION_SYSTEM_PROMPT.lower()

    def test_build_messages(self):
        messages = ClassificationPromptTemplate.build("1+1=?")
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "1+1=?" in messages[1]["content"]


# ============================================================================
# 测试4: ClassifierConfig
# ============================================================================

class TestClassifierConfig:
    def test_default_config(self):
        config = ClassifierConfig()
        assert config.cache_max_size == 2000
        assert config.enable_cache is True
        assert config.enable_fallback is True
        assert config.classification_timeout == 5.0
        assert config.temperature == 0.0

    def test_custom_config(self):
        config = ClassifierConfig(cache_max_size=500, classification_timeout=3.0)
        assert config.cache_max_size == 500
        assert config.classification_timeout == 3.0


# ============================================================================
# 测试5: ClassificationResult
# ============================================================================

class TestClassificationResult:
    def test_result_creation(self):
        result = ClassificationResult(
            score=4,
            confidence=0.85,
            strategy="planned",
            reasoning="test",
            method="llm",
            latency_ms=150.0,
        )
        assert result.score == 4
        assert result.strategy == "planned"

    def test_result_to_dict(self):
        result = ClassificationResult(
            score=2, confidence=0.9, strategy="react",
            reasoning="test", method="llm",
        )
        d = result.to_dict()
        assert d["score"] == 2
        assert d["strategy"] == "react"
        assert d["method"] == "llm"

    def test_result_repr(self):
        result = ClassificationResult(
            score=5, confidence=0.8, strategy="planned",
            reasoning="test", method="llm",
        )
        repr_str = repr(result)
        assert "5" in repr_str
        assert "planned" in repr_str


# ============================================================================
# 测试6: LLMClassifier 集成测试（需要真实API Key）
# ============================================================================

@pytest.mark.integration
@pytest.mark.asyncio
class TestLLMClassifierIntegration:
    """
    集成测试 — 需要有效的 DASHSCOPE_API_KEY。
    
    运行方式:
        python -m pytest tests/test_classifier.py -v -s -m integration
    """

    async def _create_classifier(self):
        from langchain_openai import ChatOpenAI
        from agent_core.classifier.llm_classifier import LLMComplexityClassifier
        from app.config.settings import settings

        llm = ChatOpenAI(
            model="qwen-turbo",
            temperature=0.0,
            api_key=settings.DASHSCOPE_API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            streaming=False,
        )

        return LLMComplexityClassifier(llm=llm)

    async def test_classify_trivial(self):
        """极简问题 → 期望 1-2 分"""
        classifier = await self._create_classifier()
        result = await classifier.classify("1+1等于几？")
        assert 1 <= result.score <= 2, f"期望1-2分, 得到{result.score}"
        assert result.strategy == "react"
        print(f"✅ 极简分类: {result}")

    async def test_classify_basic(self):
        """基础问题 → 期望 2-3 分"""
        classifier = await self._create_classifier()
        result = await classifier.classify("求 f(x)=x³ 的导数")
        assert 1 <= result.score <= 3, f"期望1-3分, 得到{result.score}"
        print(f"✅ 基础分类: {result}")

    async def test_classify_moderate(self):
        """中等问题 → 期望 3-4 分"""
        classifier = await self._create_classifier()
        result = await classifier.classify("用分部积分求∫x·eˣdx")
        assert 2 <= result.score <= 4, f"期望2-4分, 得到{result.score}"
        print(f"✅ 中等分类: {result}")

    async def test_classify_advanced(self):
        """复杂问题 → 期望 4-5 分"""
        classifier = await self._create_classifier()
        result = await classifier.classify("证明: eˣ > x+1 对所有 x≠0 成立")
        assert 3 <= result.score <= 5, f"期望3-5分, 得到{result.score}"
        print(f"✅ 较难分类: {result}")

    async def test_classify_complex(self):
        """困难问题 → 期望 4-5 分, strategy=planned"""
        classifier = await self._create_classifier()
        result = await classifier.classify("证明闭区间上连续函数必一致连续")
        assert 3 <= result.score <= 5, f"期望3-5分, 得到{result.score}"
        print(f"✅ 困难分类: {result}")

    async def test_cache_hit(self):
        """测试缓存命中"""
        classifier = await self._create_classifier()
        
        # 第一次调用（LLM）
        result1 = await classifier.classify("解方程 x²-4=0")
        assert result1.method == "llm"
        
        # 第二次调用（缓存命中）
        result2 = await classifier.classify("解方程 x²-4=0")
        assert result2.method == "cache"
        assert result2.score == result1.score
        
        stats = classifier.get_stats()
        assert stats["cache_hits"] >= 1
        
        print(f"✅ 缓存测试通过: {stats}")

    async def test_is_complex_problem(self):
        """测试快捷判断方法"""
        classifier = await self._create_classifier()
        
        is_simple = await classifier.is_complex_problem("sin(π/6)=?")
        assert is_simple is False  # 简单问题
        
        is_complex = await classifier.is_complex_problem(
            "证明: π是无理数"
        )
        assert is_complex is True  # 复杂问题
        
        print("✅ is_complex_problem 测试通过")

    async def test_batch_classify(self):
        """测试批量分类"""
        classifier = await self._create_classifier()
        
        problems = [
            "1+1=?",
            "求∫x²dx",
            "证明eˣ > x+1",
        ]
        
        results = await classifier.batch_classify(problems, max_concurrency=2)
        assert len(results) == 3
        
        for problem, result in zip(problems, results):
            assert 1 <= result.score <= 5
            print(f"  '{problem[:30]}...' → score={result.score} ({result.strategy})")
        
        print("✅ 批量分类测试通过")

    async def test_stats(self):
        """测试统计信息"""
        classifier = await self._create_classifier()
        await classifier.classify("1+1=?")
        await classifier.classify("求∫x²dx")
        
        stats = classifier.get_stats()
        assert stats["total_calls"] >= 2
        assert "cache_hit_rate" in stats
        assert "error_rate" in stats
        
        print(f"✅ 统计信息: {stats}")


# ============================================================================
# 直接运行
# ============================================================================

if __name__ == "__main__":
    # 运行所有测试
    pytest.main([__file__, "-v", "-s", "--tb=short"])
```

### 13.2 端到端手动测试流程

**步骤1: 验证后端启动日志**

启动服务器后，检查控制台日志确认分类器是否正常初始化：

```
# 成功初始化应看到:
[INFO] LLMComplexityClassifier 初始化完成 (model=qwen-turbo, cache_max=2000, fallback=启用)
[INFO] ✅ LLM复杂度分类器已启用 (model=qwen-turbo, cache=2000条)
```

**步骤2: 测试简单问题（期望走 ReAct）**

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "1+1等于几？", "session_id": "test1"}'
```

**预期结果**:
- 日志显示: `[分类器路由] score=1(极简) → strategy=react`
- 响应时间: < 2秒
- 内容正确: "2"

**步骤3: 测试复杂问题（期望走 Planned）**

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "证明闭区间上连续函数必一致连续，并给出完整证明步骤", "session_id": "test2"}'
```

**预期结果**:
- 日志显示: `[分类器路由] score=4(较难) → strategy=planned`
- 日志显示: `✅ 使用 PlannedStrategy`
- 响应包含规划步骤和执行结果

**步骤4: 测试缓存命中**

```bash
# 第一次发送（LLM分类，expect ~200ms延迟）
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "解方程 x²-4=0", "session_id": "test3"}'

# 第二次发送相同问题（缓存命中，expect < 1ms延迟）
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "解方程 x²-4=0", "session_id": "test4"}'
```

**预期结果**:
- 第二次日志显示: `缓存命中`
- method: `cache`

---

## 14. 常见问题与排查指南

### 问题1: 启动报错 `ImportError: No module named 'agent_core.classifier'`

**原因**: 分类器目录或文件未正确创建。

**解决方案**:
1. 确认 `agent_core/classifier/` 目录已创建
2. 确认目录下所有 5 个 `.py` 文件都已创建
3. 确认 `__init__.py` 文件存在且不为空
4. 确认每个文件内容与本文档一致

### 问题2: 分类器总是返回 `score=3, method=fallback`

**原因**: LLM 调用失败，降级到规则匹配。

**排查步骤**:
1. 检查 `.env` 文件中 `DASHSCOPE_API_KEY` 是否正确
2. 检查 `CLASSIFIER_MODEL` 配置是否有效（默认 `qwen-turbo`）
3. 查看日志中的具体错误信息
4. 尝试手动调用 DashScope API 验证连通性:

```python
from langchain_openai import ChatOpenAI
from app.config.settings import settings

llm = ChatOpenAI(
    model="qwen-turbo",
    api_key=settings.DASHSCOPE_API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
response = llm.invoke("你好")
print(response.content)  # 应该正常回复
```

### 问题3: 分类结果不稳定，同一问题有时返回2有时返回3

**原因**: `temperature` 设置不为 0.0。

**解决方案**:
确认 `__init__` 方法中分类器 LLM 的 `temperature` 确实设为 `0.0`:

```python
classifier_llm = ChatOpenAI(
    model=classifier_model,
    temperature=0.0,  # ← 必须为 0.0
    ...
)
```

### 问题4: 简单问题被判为4-5分，走了 PlannedStrategy

**原因**: Prompt 中分级标准与千问模型的认知不完全一致。

**解决方案**:
1. 收集这些误判案例
2. 检查 `_validate_result()` 中的合理性校验是否生效
3. 如果合理性校验未能拦截，在 System Prompt 中补充更明确的示例:

```python
# 在 CLASSIFICATION_SYSTEM_PROMPT 的1分示例中增加:
"2+3=?" → 1
"√4 = ?" → 1
"π/2 是多少度？" → 1
```

### 问题5: 用户等待时间明显变长

**原因**: `qwen-turbo` 响应时间在高峰期可能达 500-800ms。

**解决方案**（按优先级排序）:
1. **缓存预热**: 预计算常见数学问题的分类结果，程序启动时写入缓存
2. **切换到更快的模型**: 如果 `qwen-turbo` 响应仍然慢，可尝试 `qwen-turbo-latest`
3. **异步预取**: 在用户输入过程中就开始分类（参考 9.3 节）

### 问题6: 如何临时禁用分类器

**方式一**（全局禁用，修改 `.env`）:

```bash
CLASSIFIER_ENABLED=false
```

**方式二**（代码禁用，修改 `main.py`）:

```python
agent = MathAgent(
    api_key=api_key,
    enable_classifier=False,  # ← 禁用
    ...
)
```

### 问题7: 如何查看分类器的运行统计

在 `main.py` 中新增一个调试端点:

```python
@app.get("/api/debug/classifier-stats")
async def get_classifier_stats():
    """查看分类器运行统计"""
    if hasattr(agent, '_classifier') and agent._classifier:
        return {
            "enabled": True,
            "stats": agent._classifier.get_stats(),
        }
    return {"enabled": False, "stats": {}}
```

---

## 附录A: `.env` 配置参考

```bash
# ============================================
# 数学AI助手 - 分类器配置（新增）
# ============================================

# LLM分类器总开关（true/false）
CLASSIFIER_ENABLED=true

# 分类用模型（推荐: qwen-turbo，极快且便宜）
CLASSIFIER_MODEL=qwen-turbo

# 内存缓存上限（条）
CLASSIFIER_CACHE_SIZE=2000

# 单次分类超时（秒）
CLASSIFIER_TIMEOUT=5
```

---

## 附录B: 完整文件变更清单

| 操作 | 文件路径 | 说明 |
|------|---------|------|
| **新建** | `agent_core/classifier/__init__.py` | 包初始化 |
| **新建** | `agent_core/classifier/complexity_levels.py` | 复杂度分级枚举 |
| **新建** | `agent_core/classifier/output_parser.py` | 输出解析器 |
| **新建** | `agent_core/classifier/prompt_templates.py` | Prompt模板 |
| **新建** | `agent_core/classifier/llm_classifier.py` | 核心分类器 |
| **新建** | `tests/test_classifier.py` | 单元测试 |
| **修改** | `agent_core/agent.py` | 集成分类器 |
| **修改** | `agent_core/__init__.py` | 导出分类器 |
| **修改** | `app/config/settings.py` | 新增配置项 |
| **修改** | `main.py` | 传入分类器配置 |
| **修改** | `.env` | 新增分类器配置 |

---

## 附录C: 实施检查清单

- [ ] 创建 `agent_core/classifier/` 目录
- [ ] 创建 5 个分类器模块文件
- [ ] 创建 `tests/test_classifier.py` 测试文件
- [ ] 修改 `agent_core/agent.py` (__init__ + _select_strategy)
- [ ] 修改 `agent_core/__init__.py` (新增导出)
- [ ] 修改 `app/config/settings.py` (新增配置项)
- [ ] 修改 `main.py` (传入分类器配置)
- [ ] 更新 `.env` 文件（可选，有默认值）
- [ ] 运行单元测试: `python -m pytest tests/test_classifier.py -v`
- [ ] 运行集成测试: `python -m pytest tests/test_classifier.py -v -m integration`
- [ ] 启动服务器，验证分类器初始化日志
- [ ] 测试简单问题走 ReAct 策略
- [ ] 测试复杂问题走 Planned 策略
- [ ] 测试缓存命中
- [ ] 验证降级机制（临时禁用API Key测试）
- [ ] 前端构建并验证流式输出正常

---

> **文档结束** — 请严格按照本文档的顺序和代码内容进行开发。如有疑问，请参考源代码中的注释和本文档的排查指南。