# RAG + LLM 智能推荐系统 — 完整开发文档 (PRD)

> 版本: 3.0 | 状态: 待开发 | 编写日期: 2026-06-06
>
> 当前阶段: 使用通义千问 DashScope API（后续部署本地大模型）
>
> 内容范围: RAG推荐引擎 + 工具层 + API层 + 测试 + 部署

***

## 0. 文档控制

| 属性         | 值                          |
| ---------- | -------------------------- |
| **PRD 标题** | RAG + LLM 智能推荐系统           |
| **文档所有者**  | 数学 AI 助手项目组                |
| **目标仓库**   | `math AI assistant`        |
| **数据分类**   | 内部使用（学校教学环境）               |
| **合规标签**   | 无特殊合规要求                    |
| **审批状态**   | 待开发                        |
| **目标读者**   | Trae coding agent（AI 代码生成） |

### 0.1 构建 / 运行 / 验证合约

> 以下命令是 Agent 开发完成后的验证标准，必须全部通过。

| 阶段       | 命令                                                                                                                                                                                               | 预期结果                       |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------- |
| **安装依赖** | `venv\Scripts\activate && pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple && pip install chromadb pandas openpyxl numpy -i https://pypi.tuna.tsinghua.edu.cn/simple` | 无错误                        |
| **启动服务** | `python main.py`                                                                                                                                                                                 | 服务启动，无报错                   |
| **健康检查** | `curl http://localhost:8000/api/recommend/health`                                                                                                                                                | 返回 `{"status": "healthy"}` |
| **运行测试** | `pytest tests/test_rag_recommender.py -v`                                                                                                                                                        | 全部通过                       |
| **覆盖率**  | `pytest tests/test_rag_recommender.py -v --cov=app.services --cov=tools --cov-report=term-missing`                                                                                               | ≥ 80%                      |
| **导入题目** | `curl -X POST /api/recommend/questions/import -d '{"questions":[...]}'`                                                                                                                          | 返回导入成功                     |
| **推荐接口** | `curl -X POST /api/recommend/questions -d '{"target_category":"导数","count":3}'`                                                                                                                  | 返回题目 + AI 分析               |

### 0.2 技术栈（已批准，不可替换）

| 组件        | 技术选型                                     | 替代方案（已否决）                  |
| --------- | ---------------------------------------- | -------------------------- |
| Web 框架    | FastAPI + uvicorn                        | 不可替换                       |
| 数据库       | SQLite (SQLAlchemy ORM)                  | PostgreSQL（后续迁移）           |
| 向量数据库     | ChromaDB 0.4+                            | FAISS（接口不兼容）               |
| LLM 客户端   | openai SDK (兼容 OpenAI API)               | 不可替换（后续本地模型也走 OpenAI 兼容接口） |
| 嵌入模型      | all-MiniLM-L6-v2 (sentence-transformers) | 可替换为 BGE 系列                |
| 测试框架      | pytest + pytest-asyncio + pytest-cov     | 不可替换                       |
| Python 版本 | 3.10+                                    | 不可低于 3.10                  |

### 0.3 禁止替换

Agent 开发时**不得**替换以下组件：

* 数据库 ORM（SQLAlchemy）

* LLM 调用方式（openai SDK）

* 工具基类（BaseTool / ToolInput / ToolOutput）

* 配置管理方式（pydantic-settings）

***

## 目录

* [1. 摘要](#1-摘要)

* [2. 问题陈述](#2-问题陈述)

* [3. 目标与非目标](#3-目标与非目标)

* [4. 用户故事](#4-用户故事)

* [5. 功能需求](#5-功能需求)

* [6. 非功能需求](#6-非功能需求)

* [7. 架构设计](#7-架构设计)

* [8. 实现规范](#8-实现规范)

  * [8.1 前置依赖与配置](#81-前置依赖与配置)

  * [8.2 LLM服务模块](#82-llm服务模块)

  * [8.3 向量数据库模块](#83-向量数据库模块)

  * [8.4 题库导入模块](#84-题库导入模块)

  * [8.5 RAG推荐引擎](#85-rag推荐引擎)

  * [8.6 工具层（Agent Tools）](#86-工具层agent-tools)

  * [8.7 API接口层](#87-api接口层)

  * [8.8 主应用集成](#88-主应用集成)

* [9. 测试策略](#9-测试策略)

* [10. 部署指南](#10-部署指南)

* [11. 超出范围](#11-超出范围)

* [12. 风险与待解决问题](#12-风险与待解决问题)

* [13. 成功指标](#13-成功指标)

* [附录A: 文件创建清单](#附录a-文件创建清单)

* [附录B: 依赖安装命令](#附录b-依赖安装命令)

* [附录C: 关键配置项汇总](#附录c-关键配置项汇总)

***

## 1. 摘要

为数学 AI 助手项目构建 **RAG + LLM + 知识图谱 + 难度估算** 四合一智能推荐系统。当前使用通义千问 API，后续可无缝切换到本地部署的 Qwen2.5-Math 模型。

目标用户是**大学本科生**，核心学科覆盖**高等数学、线性代数、概率论与数理统计**。核心产出是：学生提问后，系统能自动推荐适合其难度水平的练习题，并给出 AI 讲解。

同时补齐项目最大短板——**工具层**。当前项目只有 1 个 vision\_tool 注册在册，导致 Agent 的策略模式（ReAct / TaskPlanner）虽然有工具调用能力，但实际无工具可用。本次新增 5 个 P0 工具，使 Agent 在**两种策略模式**下都具备智能决策能力：

* **LangChain ReAct 策略**：通过 function calling 自动调用工具

* **TaskPlanner 策略**：生成 ExecutionPlan 后通过 ToolInvoker 执行工具调用

***

## 2. 问题陈述

### 当前痛点

1. **无个性化推荐**: 大学生做完高数/线代/概率论题目后没有"接着练"的机制，学习链断裂
2. **工具层严重不足**: 只有 vision\_tool 一个工具，Agent 的 ReAct 和 TaskPlanner 两种策略都退化为纯对话模式
3. **题库未向量化**: 学校题库导入后无法按语义相似度检索
4. **LLM 调用分散**: 各处直接调用 openai SDK，没有缓存、没有流式统一接口
5. **无降级策略**: 任何组件故障都会导致功能不可用

### 目标用户

**大学本科生**（使用数学 AI 助手进行高等数学、线性代数、概率论与数理统计的自主学习和练习）

***

## 3. 目标与非目标

### 目标

1. 学生提问后自动推荐 3-5 道适合其水平的练习题
2. Agent 能主动调用工具（查技能画像、推荐题目、搜索题库、讲解题目）
3. 支持 SQL 精确查询 + 向量语义搜索 + 知识图谱三路检索
4. LLM 调用统一管理（缓存、流式、TIR 模式）
5. 任何组件故障时自动降级，不影响基础功能
6. 后续部署本地模型时只需改一行配置

### 非目标

* 不实现复杂的知识追踪模型（DKT/SAKT）

* 不实现前端 UI 改动

* 不实现公式编辑器或思维导图

* 不实现独立的组卷大模型

* 不实现实验模拟器

***

## 4. 用户故事

1. 作为一个**大学本科生**，我做完一道高数导数题后，希望系统能自动推荐类似难度的题目，以便趁热打铁巩固知识
2. 作为一个**大学本科生**，我输入"推荐几道线性代数矩阵的题"，希望 Agent 能理解我的意图并调用推荐工具
3. 作为一个**大学本科生**，我想知道我的薄弱知识点是什么（比如概率论条件期望掌握不好），希望 Agent 能告诉我并推荐相应的练习
4. 作为一个**大学本科生**，我遇到一道不会的高数题（如多元函数积分），希望能得到详细的讲解，包括解题步骤和知识点回顾
5. 作为一个老师/助教，我导入学校的高数/线代题库后，希望系统能自动处理并支持智能搜索
6. 作为一个管理员，当向量库或 LLM 服务出问题时，希望系统仍能通过降级策略提供基础推荐
7. 作为一个运维人员，后续部署本地模型时，希望只需修改配置文件而不需要改动任何代码

***

## 5. 功能需求

### FR-1: 自适应难度推荐

* 输入: 用户ID、目标知识点、场景上下文

* 处理: DifficultyEstimator 五因子加权评分 → 确定推荐难度

* 输出: 3-5 道题目 + AI 推荐理由

* 降级: 向量库/LLM 不可用时降级为纯 SQL 查询

### FR-2: 多路检索

* SQL 精确检索: category + difficulty 组合查询

* 向量语义检索: ChromaDB 相似度搜索

* 知识图谱: MathSkillDAG 前置/后继知识点分析

### FR-3: 工具层（Agent 可调用）

* `recommend_tool`: 智能推荐题目

* `skill_profile_tool`: 查询技能画像

* `explain_tool`: 题目详细讲解

* `search_tool`: 题库语义搜索

* `error_book_tool`: 错题本分析

### FR-4: LLM 服务统一管理

* 单例模式，全局复用

* 内存缓存（5分钟TTL，LRU淘汰）

* 流式响应支持

* TIR 数学推理模式

* AI 难度分析辅助

### FR-5: 题库导入

* CSV/Excel 批量导入

* 自动写入数据库 + 向量库

* 数据完整性验证

* 增量导入（跳过已存在ID）

### FR-6: 降级策略

* 完整模式: SQL + 向量 + 知识图谱 + LLM分析

* 半降级: SQL + 知识图谱（向量库不可用）

* 最小降级: 纯 SQL 查询（所有高级组件不可用）

***

## 6. 非功能需求

| 需求        | 指标             |
| --------- | -------------- |
| 推荐响应时间    | < 3s（含 LLM 生成） |
| 向量搜索延迟    | < 100ms        |
| LLM 缓存命中率 | > 60%（高频请求）    |
| 降级响应时间    | < 500ms（纯 SQL） |
| 系统可用性     | 99.5%（降级策略保障）  |
| 并发支持      | 10+ 并发推荐请求     |
| 向量库容量     | 10 万+ 题目       |
| 后续切换成本    | 修改 1 个配置项      |

***

## 7. 架构设计

### 7.1 整体架构

```
┌────────────────────────────────────────────────────────────┐
│                     用户交互层                              │
│  POST /api/recommend/questions                             │
│  Agent: "推荐几道导数题" → 调用工具 → 返回结果              │
└───────────────┬────────────────────────────────────────────┘
                │
    ┌───────────┴──────────────┐
    │                          │
    ▼                          ▼
┌───────────┐          ┌──────────────┐
│  API 层   │          │  Agent 工具层  │
│recommend- │          │ recommend_tool│
│ ation_api │          │ skill_profile │
│  .py      │          │ explain_tool  │
└─────┬─────┘          │ search_tool   │
      │                │ error_book    │
      │                └──────┬────────┘
      │                       │
      ▼                       ▼
┌──────────────────────────────────────┐
│           RAG推荐引擎 (services)      │
│  RAGRecommender                      │
│  ├─ LLMService (llm_service.py)      │
│  ├─ VectorStoreManager (vector_store)│
│  ├─ DifficultyEstimator (已有)        │
│  ├─ SkillAggregator (已有)           │
│  ├─ MathSkillDAG (已有)              │
│  └─ QuestionImporter (question_imp)  │
└───┬──────────┬──────────┬────────────┘
    │          │          │
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌─────────┐
│ 数据库  │ │ChromaDB│ │知识图谱  │
│ SQLite  │ │向量检索  │ │SkillDAG  │
└────────┘ └────────┘ └─────────┘
```

### 7.2 分层职责

| 层               | 职责                 | 厚度           |
| --------------- | ------------------ | ------------ |
| `tools/`        | Agent 可调用的工具（薄适配器） | 每个 30-50 行   |
| `app/services/` | 核心业务逻辑（厚实现）        | 每个 200-500 行 |
| `app/api/`      | RESTful API 端点     | 每个 200-300 行 |
| `app/data/`     | 数据模型和数据库           | 已有，不修改       |

### 7.3 工具层设计（核心新增）

**设计原则**: 工具层是 Agent 的"瑞士军刀"——薄、聚焦、单一职责。每个工具只是 `app/services/` 的适配器，不包含业务逻辑。

**双策略兼容**: 所有工具注册到 `HybridToolRegistry` 后，自动对两种策略模式可用：

| 策略模式                              | 工具调用方式                                                 | 适用场景                        |
| --------------------------------- | ------------------------------------------------------ | --------------------------- |
| **LangChain ReAct**               | function calling 自动调用（`create_agent(tools=...)`）       | 单轮简单问题，如"推荐几道导数题"           |
| **TaskPlanner (PlannedStrategy)** | 生成 `ExecutionPlan(DAG)` → `ToolInvoker.invoke()` 逐节点执行 | 复杂多步问题，如"帮我分析薄弱点→推荐题目→讲解错题" |

> **关键机制**: `HybridToolRegistry.register()` 注册时自动双向同步：
>
> * 存入 `_custom_tools` → 供 PlannedStrategy / 自定义 ReAct 通过 `ToolInvoker` 调用
>
> * 转换为 `_langchain_tools`（StructuredTool）→ 供 LangChain ReAct 通过 function calling 调用
>
> 因此新工具**无需额外配置**即可被两种策略使用。

```
tools/
├── __init__.py          (修改: 注册所有工具)
├── base_tool.py         (已有, 不修改)
├── hybrid_registry.py   (已有, 不修改)
├── tool_description.py  (已有, 不修改)
├── tool_invoker.py      (已有, 不修改)
├── vision_tool.py       (已有)
├── recommend_tool.py    (新增 P0)
├── skill_profile_tool.py(新增 P0)
├── explain_tool.py      (新增 P0)
├── search_tool.py       (新增 P1)
└── error_book_tool.py   (新增 P1)
```

***

## 8. 实现规范

> **重要**: 以下所有代码块均为**完整可运行代码**，直接复制到对应文件即可。

***

### 8.0 前置修复：修改现有文件

> **必须最先执行**：以下修改确保新增代码与现有代码库兼容，不修复会导致运行时错误。

#### 8.0.1 修改 `tools/base_tool.py` 的 ToolOutput 类

**问题**：ToolOutput 缺少 `data` 字段，所有工具使用 `data={...}` 会触发 Pydantic v2 的额外字段校验错误。

**修改**：在 `ToolOutput` 类（约第42行）中新增 `data` 字段：

```python
class ToolOutput(BaseModel):
    """工具输出标准模型 — 所有工具的出参结构。"""
    success: bool = Field(..., description="执行是否成功")
    result: Any = Field(None, description="执行结果数据")
    data: Dict[str, Any] = Field(default_factory=dict, description="结构化数据（供前端/Agent使用）")  # 【新增】
    error: Optional[str] = Field(None, description="错误信息")
    tool_name: str = Field("", description="执行工具名称")
    execution_time_ms: float = Field(0.0, description="执行耗时（毫秒）")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="附加元数据"
    )
```

***

### 8.1 前置依赖与配置

#### 8.1.1 新增依赖 (`requirements.txt` 追加)

```txt
# RAG + Vector Store + LLM
chromadb>=0.4.22
pandas>=2.0.0
openpyxl>=3.1.0
numpy>=1.24.0
```

#### 8.1.2 环境变量 (`.env` 追加)

```env
# LLM 配置（当前使用通义千问 DashScope）
LLM_API_KEY=sk-你的key
LLM_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-max
LLM_MATH_MODEL=qwen-turbo
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=4096
LLM_STREAMING=true

# 向量数据库
VECTOR_DB_PATH=./data/chroma_db
```

#### 8.1.3 Settings 配置 (`app/config/settings.py` 追加)

在 `Settings` 类中追加以下字段（追加到 `CLASSIFIER_TIMEOUT` 字段之后）：

```python
# ── LLM 配置 ──
LLM_API_KEY: str = Field(default="", alias="LLM_API_KEY")
LLM_API_BASE: str = Field(
    default="https://dashscope.aliyuncs.com/compatible-mode/v1",
    alias="LLM_API_BASE",
)
LLM_MODEL: str = Field(default="qwen-max", alias="LLM_MODEL")
LLM_MATH_MODEL: str = Field(default="qwen-turbo", alias="LLM_MATH_MODEL")
LLM_TEMPERATURE: float = Field(default=0.3, alias="LLM_TEMPERATURE")
LLM_MAX_TOKENS: int = Field(default=4096, alias="LLM_MAX_TOKENS")
LLM_STREAMING: bool = Field(default=True, alias="LLM_STREAMING")

# ── 向量数据库配置 ──
VECTOR_DB_PATH: str = Field(default="./data/chroma_db", alias="VECTOR_DB_PATH")
VECTOR_EMBEDDING_MODEL: str = Field(default="all-MiniLM-L6-v2", alias="VECTOR_EMBEDDING_MODEL")

# ── 推荐引擎配置 ──
RAG_ENABLED: bool = Field(default=True, alias="RAG_ENABLED")
RAG_ENABLE_AI_EXPLANATION: bool = Field(default=True, alias="RAG_ENABLE_AI_EXPLANATION")
RAG_ENABLE_VECTOR_SEARCH: bool = Field(default=True, alias="RAG_ENABLE_VECTOR_SEARCH")
RAG_DEFAULT_RECOMMEND_COUNT: int = Field(default=5, alias="RAG_DEFAULT_RECOMMEND_COUNT")
RAG_HYBRID_SEARCH_TOP_K: int = Field(default=20, alias="RAG_HYBRID_SEARCH_TOP_K")
```

***

### 8.2 LLM服务模块

#### 文件: `app/services/llm_service.py` 【新建】

````python
"""
LLM 服务模块 — 统一管理大语言模型调用。

当前阶段：通义千问 DashScope API（兼容 OpenAI SDK）
后续阶段：切换至本地部署模型（接口不变，只改配置）

设计要点：
- 单例模式，全局复用
- 内存缓存（5分钟TTL，LRU淘汰，最多100条）
- 流式响应支持（AsyncGenerator）
- TIR 数学推理模式
- 降级处理（JSON解析失败返回默认值）
"""

from __future__ import annotations

import json
import logging
import time
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from openai import AsyncOpenAI

from app.config.settings import settings

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    DASHSCOPE = "dashscope"
    LOCAL = "local"


class LLMResponse:
    def __init__(
        self,
        content: str,
        model: str,
        provider: str,
        usage: Optional[Dict[str, int]] = None,
        latency_ms: float = 0.0,
        cached: bool = False,
    ):
        self.content = content
        self.model = model
        self.provider = provider
        self.usage = usage or {}
        self.latency_ms = latency_ms
        self.cached = cached

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "model": self.model,
            "provider": self.provider,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
            "cached": self.cached,
        }


class LLMService:
    """
    LLM 服务管理器（单例模式）

    设计要点：
    - 全项目共享一个 LLMService 实例（单例模式）
    - 通用对话和数学推理共用同一个模型
    - 数学推理使用 generate_with_math_model() 方法（自动添加 TIR prompt）
    - 后续切换本地模型只需修改 .env 中的 LLM_API_BASE 和 LLM_MODEL

    核心方法：
    - generate(): 非流式生成
    - generate_stream(): 流式生成
    - generate_with_math_model(): 数学专用（自动添加 TIR prompt）
    - analyze_question_difficulty(): AI难度分析
    """

    _instance: Optional[LLMService] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model: Optional[str] = None,
        math_model: Optional[str] = None,
    ):
        if hasattr(self, "_initialized") and self._initialized:
            return

        self.api_key = api_key or settings.LLM_API_KEY or settings.DASHSCOPE_API_KEY
        self.api_base = api_base or settings.LLM_API_BASE
        self.model = model or settings.LLM_MODEL
        self.math_model = math_model or settings.LLM_MATH_MODEL
        self.temperature = settings.LLM_TEMPERATURE
        self.max_tokens = settings.LLM_MAX_TOKENS

        self.provider = LLMProvider.DASHSCOPE
        if "localhost" in self.api_base or "127.0.0.1" in self.api_base:
            self.provider = LLMProvider.LOCAL

        self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.api_base)
        self._cache: Dict[str, Tuple[LLMResponse, float]] = {}
        self._cache_ttl: int = 300
        self._cache_max_size: int = 100
        self._initialized = True

        logger.info(
            f"LLMService 初始化: provider={self.provider.value}, "
            f"model={self.model}, math_model={self.math_model}"
        )

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_cache: bool = True,
    ) -> LLMResponse:
        start = time.time()

        if use_cache:
            cache_key = self._make_cache_key(prompt, system_prompt, model or self.model)
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

        messages = self._build_messages(prompt, system_prompt)

        try:
            response = await self._client.chat.completions.create(
                model=model or self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=False,
            )
            content = response.choices[0].message.content or ""
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            } if response.usage else {}

            result = LLMResponse(
                content=content,
                model=response.model,
                provider=self.provider.value,
                usage=usage,
                latency_ms=(time.time() - start) * 1000,
            )

            if use_cache:
                self._add_to_cache(cache_key, result)

            return result
        except Exception as e:
            logger.error(f"LLM生成失败: {e}", exc_info=True)
            raise

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        messages = self._build_messages(prompt, system_prompt)
        try:
            stream = await self._client.chat.completions.create(
                model=model or self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"LLM流式生成失败: {e}", exc_info=True)
            yield f"\n\n[生成错误: {str(e)}]"

    async def generate_with_math_model(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        use_tir: bool = True,
    ) -> LLMResponse:
        if use_tir:
            prompt = prompt + (
                "\n\n【TIR模式要求】"
                "\n1. 先用自然语言分析问题思路"
                "\n2. 编写 Python 代码进行计算或验证（用 ```python 包裹）"
                "\n3. 根据代码执行结果给出最终答案"
                "\n4. 格式：最后用 **最终答案：** 标记结果"
            )
        return await self.generate(
            prompt=prompt, system_prompt=system_prompt, model=self.math_model,
        )

    async def analyze_question_difficulty(
        self, question_content: str, category: str
    ) -> Dict[str, Any]:
        system_prompt = (
            "你是一位数学教育专家。请分析以下数学题目的难度等级。\n"
            "请严格按照 JSON 格式返回：\n"
            '{"estimated_difficulty": 数字1-5, "reason": "理由", '
            '"knowledge_points": ["知识点1", "知识点2"]}\n'
            "难度定义：1=入门 2=基础 3=标准 4=进阶 5=挑战"
        )
        prompt = f"题目分类: {category}\n\n题目内容:\n{question_content}"
        response = await self.generate(prompt=prompt, system_prompt=system_prompt, temperature=0.1)
        content = response.content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        try:
            return json.loads(content)
        except (json.JSONDecodeError, IndexError):
            return {"estimated_difficulty": 3, "reason": "AI分析失败", "knowledge_points": [category]}

    def _build_messages(self, prompt: str, system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _make_cache_key(self, prompt: str, system_prompt: Optional[str], model: str) -> str:
        import hashlib
        return hashlib.md5(f"{model}:{system_prompt or ''}:{prompt}".encode()).hexdigest()

    def _get_from_cache(self, key: str) -> Optional[LLMResponse]:
        if key not in self._cache:
            return None
        entry, timestamp = self._cache[key]
        if time.time() - timestamp > self._cache_ttl:
            del self._cache[key]
            return None
        entry.cached = True
        return entry

    def _add_to_cache(self, key: str, response: LLMResponse) -> None:
        if not response.content or len(response.content) < 10:
            return
        if len(self._cache) >= self._cache_max_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        self._cache[key] = (response, time.time())

    def clear_cache(self) -> int:
        count = len(self._cache)
        self._cache.clear()
        return count

    def get_cache_stats(self) -> Dict[str, Any]:
        return {"cache_size": len(self._cache), "ttl_seconds": self._cache_ttl}


def get_llm_service() -> LLMService:
    """获取 LLM 服务单例。数学推理使用 generate_with_math_model() 方法。"""
    return LLMService()
````

***

### 8.3 向量数据库模块

#### 文件: `app/services/vector_store.py` 【新建】

```python
"""
向量数据库模块 — 基于 ChromaDB 的题目向量存储与语义检索。

设计要点：
- ChromaDB 持久化存储（自动创建目录）
- 默认使用内置 embedding 函数（all-MiniLM-L6-v2）
- 支持语义搜索、混合搜索（向量 + 关键词 + 筛选）
- metadata 自动清理（只保留 str/int/float/bool 类型）
- 增量更新（先删后加）
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class VectorSearchResult:
    id: str
    content: str
    metadata: Dict[str, Any]
    score: float
    distance: float


class VectorStoreManager:
    def __init__(
        self,
        persist_directory: Optional[str] = None,
        collection_name: str = "math_questions",
    ):
        self.persist_directory = persist_directory or settings.VECTOR_DB_PATH
        self.collection_name = collection_name
        self._client: Optional[chromadb.PersistentClient] = None
        self._collection: Optional[chromadb.Collection] = None
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return
        os.makedirs(self.persist_directory, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._initialized = True
        logger.info(f"ChromaDB 初始化完成: collection={self.collection_name}, 文档数={self._collection.count()}")

    async def add_question(self, question_id: str, content: str, metadata: Dict[str, Any]) -> bool:
        await self.initialize()
        try:
            self._collection.add(
                ids=[question_id],
                documents=[content],
                metadatas=[self._clean_metadata(metadata)],
            )
            return True
        except Exception as e:
            logger.error(f"添加题目失败: id={question_id}, error={e}")
            return False

    async def add_questions_batch(
        self, questions: List[Tuple[str, str, Dict[str, Any]]], batch_size: int = 100
    ) -> int:
        await self.initialize()
        success = 0
        for i in range(0, len(questions), batch_size):
            batch = questions[i:i + batch_size]
            try:
                self._collection.add(
                    ids=[q[0] for q in batch],
                    documents=[q[1] for q in batch],
                    metadatas=[self._clean_metadata(q[2]) for q in batch],
                )
                success += len(batch)
            except Exception as e:
                logger.error(f"批量添加失败: batch={i}, error={e}")
        return success

    async def semantic_search(
        self, query: str, n_results: int = 10, where: Optional[Dict[str, Any]] = None
    ) -> List[VectorSearchResult]:
        await self.initialize()
        try:
            results = self._collection.query(query_texts=[query], n_results=n_results, where=where)
            return self._format_results(results)
        except Exception as e:
            logger.error(f"语义搜索失败: {e}")
            return []

    async def hybrid_search(
        self,
        query: str,
        category_filter: Optional[str] = None,
        difficulty_range: Optional[Tuple[int, int]] = None,
        n_results: int = 10,
        vector_weight: float = 0.7,
    ) -> List[VectorSearchResult]:
        await self.initialize()
        where_filter = {}
        if category_filter:
            where_filter["category"] = category_filter
        if difficulty_range:
            where_filter["difficulty"] = {"$gte": difficulty_range[0], "$lte": difficulty_range[1]}

        vector_results = await self.semantic_search(
            query=query, n_results=n_results * 3,
            where=where_filter if where_filter else None,
        )
        if not vector_results:
            return []

        keyword_scores = self._calculate_keyword_scores(query, vector_results)
        for vr in vector_results:
            kw_score = keyword_scores.get(vr.id, 0.0)
            vr.score = vector_weight * vr.score + (1 - vector_weight) * kw_score
        vector_results.sort(key=lambda x: x.score, reverse=True)
        return vector_results[:n_results]

    async def remove_question(self, question_id: str) -> bool:
        await self.initialize()
        try:
            self._collection.delete(ids=[question_id])
            return True
        except Exception as e:
            logger.error(f"移除题目失败: {e}")
            return False

    async def update_question(
        self, question_id: str, content: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        await self.initialize()
        try:
            existing = self._collection.get(ids=[question_id])
            if existing["ids"]:
                current_content = existing["documents"][0] if existing["documents"] else ""
                current_metadata = existing["metadatas"][0] if existing["metadatas"] else {}
                self._collection.delete(ids=[question_id])
                self._collection.add(
                    ids=[question_id],
                    documents=[content if content is not None else current_content],
                    metadatas=[self._clean_metadata(metadata if metadata is not None else current_metadata)],
                )
                return True
            return False
        except Exception as e:
            logger.error(f"更新题目失败: {e}")
            return False

    async def get_collection_stats(self) -> Dict[str, Any]:
        await self.initialize()
        try:
            count = self._collection.count()
            all_metadatas = self._collection.get(limit=min(count, 1000))["metadatas"]
            categories = {m["category"] for m in all_metadatas if m and "category" in m}
            difficulties = {m["difficulty"] for m in all_metadatas if m and "difficulty" in m}
            return {
                "total_documents": count,
                "categories": sorted(categories),
                "difficulty_range": (min(difficulties) if difficulties else None, max(difficulties) if difficulties else None),
            }
        except Exception as e:
            return {"error": str(e)}

    async def get_all_ids(self) -> List[str]:
        await self.initialize()
        count = self._collection.count()
        if count == 0:
            return []
        return self._collection.get(limit=count)["ids"]

    def _format_results(self, raw_results) -> List[VectorSearchResult]:
        results = []
        if not raw_results or not raw_results["ids"]:
            return results
        for i in range(len(raw_results["ids"][0])):
            results.append(VectorSearchResult(
                id=raw_results["ids"][0][i],
                content=raw_results["documents"][0][i] if raw_results["documents"] else "",
                metadata=raw_results["metadatas"][0][i] if raw_results["metadatas"] else {},
                score=1.0 - raw_results["distances"][0][i] if raw_results["distances"] else 0.0,
                distance=raw_results["distances"][0][i] if raw_results["distances"] else 0.0,
            ))
        return results

    def _calculate_keyword_scores(self, query: str, results: List[VectorSearchResult]) -> Dict[str, float]:
        import re
        query_lower = query.lower()
        chinese_chars = set(re.findall(r'[\u4e00-\u9fff]+', query_lower))
        english_words = set(re.findall(r'[a-z]+', query_lower))
        keywords = chinese_chars | english_words
        if not keywords:
            return {}
        scores = {}
        for r in results:
            content_lower = r.content.lower()
            meta_str = json.dumps(r.metadata, ensure_ascii=False).lower()
            match_count = sum(1 for kw in keywords if kw in content_lower or kw in meta_str)
            scores[r.id] = match_count / len(keywords)
        return scores

    @staticmethod
    def _clean_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = {}
        for k, v in metadata.items():
            if v is None:
                continue
            if isinstance(v, (str, int, float, bool)):
                cleaned[k] = v
            elif isinstance(v, (list, dict)):
                cleaned[k] = json.dumps(v, ensure_ascii=False)
            else:
                cleaned[k] = str(v)
        return cleaned


_vector_store_instance: Optional[VectorStoreManager] = None


async def get_vector_store() -> VectorStoreManager:
    global _vector_store_instance
    if _vector_store_instance is None:
        _vector_store_instance = VectorStoreManager()
        await _vector_store_instance.initialize()
    return _vector_store_instance
```

***

### 8.4 题库导入模块

#### 文件: `app/services/question_importer.py` 【新建】

```python
"""
题库导入模块 — 从 CSV/Excel 批量导入题目到数据库和向量库。

CSV/Excel 列格式：
| id | content | question_type | options | answer | analysis |
| category | sub_categories | knowledge_points | difficulty | estimated_time | source |

必需列: id, content, category, answer
可选列: question_type, options, analysis, sub_categories, knowledge_points, difficulty, estimated_time, source
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from app.data.database import get_db_session
from app.data.models import Question
from app.services.vector_store import VectorStoreManager

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    total: int = 0
    success: int = 0
    failed: int = 0
    errors: List[str] = field(default_factory=list)
    imported_ids: List[str] = field(default_factory=list)


class QuestionImporter:
    REQUIRED_COLUMNS = {"id", "content", "category", "answer"}
    OPTIONAL_COLUMNS = {
        "question_type": "text", "options": "[]", "analysis": "",
        "sub_categories": "", "knowledge_points": "[]",
        "difficulty": 3, "estimated_time": 3, "source": "",
    }

    def __init__(self, vector_store: Optional[VectorStoreManager] = None):
        self._vector_store = vector_store

    async def import_from_csv(self, file_path: str, encoding: str = "utf-8-sig") -> ImportResult:
        if not os.path.exists(file_path):
            return ImportResult(errors=[f"文件不存在: {file_path}"])
        try:
            df = pd.read_csv(file_path, encoding=encoding)
            return await self._import_dataframe(df)
        except Exception as e:
            return ImportResult(errors=[f"CSV读取失败: {str(e)}"])

    async def import_from_excel(self, file_path: str, sheet_name: str = "Sheet1") -> ImportResult:
        if not os.path.exists(file_path):
            return ImportResult(errors=[f"文件不存在: {file_path}"])
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
            return await self._import_dataframe(df)
        except Exception as e:
            return ImportResult(errors=[f"Excel读取失败: {str(e)}"])

    async def import_from_dict_list(self, questions: List[Dict[str, Any]]) -> ImportResult:
        return await self._import_dataframe(pd.DataFrame(questions))

    async def _import_dataframe(self, df: pd.DataFrame) -> ImportResult:
        result = ImportResult()
        missing_cols = self.REQUIRED_COLUMNS - set(df.columns)
        if missing_cols:
            result.errors.append(f"缺少必需列: {missing_cols}")
            return result
        result.total = len(df)
        for col, default in self.OPTIONAL_COLUMNS.items():
            if col not in df.columns:
                df[col] = default

        for idx, row in df.iterrows():
            try:
                qid = str(row["id"]).strip()
                if not qid:
                    result.failed += 1
                    continue

                question_data = self._build_question_data(row)

                async with get_db_session() as db:
                    existing = await db.get(Question, qid)
                    if existing:
                        result.imported_ids.append(qid)
                        result.success += 1
                        continue
                    db.add(question_data)
                    await db.flush()

                if self._vector_store:
                    content_for_embedding = self._build_embedding_content(row)
                    metadata = {
                        "id": qid, "category": str(row.get("category", "")),
                        "difficulty": int(row.get("difficulty", 3)),
                        "question_type": str(row.get("question_type", "text")),
                        "sub_categories": str(row.get("sub_categories", "")),
                        "knowledge_points": str(row.get("knowledge_points", "")),
                        "source": str(row.get("source", "")),
                    }
                    await self._vector_store.add_question(qid, content_for_embedding, metadata)

                result.success += 1
                result.imported_ids.append(qid)
            except Exception as e:
                result.failed += 1
                result.errors.append(f"第{idx+2}行导入失败: {str(e)}")

        logger.info(f"题库导入完成: total={result.total}, success={result.success}, failed={result.failed}")
        return result

    def _build_question_data(self, row: pd.Series) -> Question:
        options_raw = row.get("options", "[]")
        if isinstance(options_raw, str):
            try:
                options = json.loads(options_raw)
            except (json.JSONDecodeError, TypeError):
                options = []
        else:
            options = options_raw

        kp_raw = row.get("knowledge_points", "[]")
        if isinstance(kp_raw, str):
            try:
                knowledge_points = json.dumps(json.loads(kp_raw), ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                knowledge_points = kp_raw
        else:
            knowledge_points = json.dumps(kp_raw, ensure_ascii=False)

        return Question(
            id=str(row["id"]).strip(),
            content=str(row["content"]).strip(),
            question_type=str(row.get("question_type", "text")).strip(),
            options=options,
            answer=str(row["answer"]).strip(),
            analysis=str(row.get("analysis", "")).strip(),
            category=str(row.get("category", "")).strip(),
            sub_categories=str(row.get("sub_categories", "")).strip(),
            knowledge_points=knowledge_points,
            difficulty=int(row.get("difficulty", 3)),
            source=str(row.get("source", "")).strip(),
            estimated_time=int(row.get("estimated_time", 3)),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _build_embedding_content(row: pd.Series) -> str:
        return "\n".join([
            f"题目: {row.get('content', '')}",
            f"分类: {row.get('category', '')}",
            f"知识点: {row.get('knowledge_points', '')}",
            f"解析: {row.get('analysis', '')[:200]}",
        ])
```

***

### 8.5 RAG推荐引擎

#### 文件: `app/services/rag_recommender.py` 【新建】

```python
"""
RAG 智能推荐引擎 — 整合所有组件，实现自适应题目推荐。

6步工作流：
1. 获取用户画像 + 技能数据 + 近期练习历史
2. 确定目标知识点（指定 or 自动推断薄弱点）
3. DifficultyEstimator 估算推荐难度
4. 三路并行检索（SQL + 向量 + 知识图谱）
5. 结果融合、去重、排序
6. LLM 生成个性化推荐理由
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, and_

from app.config.settings import settings
from app.data.database import get_db_session
from app.data.models import Question, LearningRecord
from app.services.difficulty_estimator import DifficultyEstimator
from app.services.llm_service import LLMService, get_llm_service
from app.services.vector_store import VectorStoreManager, get_vector_store
from app.services.skill_aggregator import SkillAggregator

logger = logging.getLogger(__name__)


@dataclass
class RecommendationRequest:
    user_id: str
    target_category: str = ""
    count: int = 5
    context: str = "practice"
    exclude_ids: List[str] = field(default_factory=list)
    request_id: str = ""


@dataclass
class RecommendationResult:
    questions: List[Dict[str, Any]]
    ai_analysis: Dict[str, Any]
    meta: Dict[str, Any]
    request_id: str = ""
    generated_at: str = ""
    processing_time_ms: float = 0.0


class RAGRecommender:
    def __init__(
        self,
        db_session_factory=None,
        vector_store: Optional[VectorStoreManager] = None,
        llm_service: Optional[LLMService] = None,
        difficulty_estimator: Optional[DifficultyEstimator] = None,
        skill_aggregator: Optional[SkillAggregator] = None,
    ):
        self._session_factory = db_session_factory or get_db_session
        self._vector_store = vector_store
        self._llm = llm_service
        self._difficulty_estimator = difficulty_estimator or DifficultyEstimator()
        self._skill_aggregator = skill_aggregator or SkillAggregator()
        self.enable_rag = settings.RAG_ENABLED
        self.enable_ai_explanation = settings.RAG_ENABLE_AI_EXPLANATION
        self.enable_vector_search = settings.RAG_ENABLE_VECTOR_SEARCH
        self.hybrid_top_k = settings.RAG_HYBRID_SEARCH_TOP_K

    async def recommend(self, request: RecommendationRequest) -> RecommendationResult:
        start_time = time.time()
        logger.info(f"[推荐] user={request.user_id} category={request.target_category or 'auto'} context={request.context}")

        try:
            user_profile = await self._get_user_profile(request.user_id)
            user_skills = await self._get_user_skills_dict(request.user_id)
            recently_done = await self._get_recently_done_ids(request.user_id)

            target_category, weak_points = await self._determine_target(
                request.target_category, user_skills, user_profile
            )

            recommended_difficulty = await self._difficulty_estimator.estimate(
                user_id=request.user_id, category=target_category,
                context=request.context, profile=user_profile,
            )

            all_exclude = list(set(request.exclude_ids + recently_done))
            sql_results = await self._sql_retrieval(target_category, recommended_difficulty, all_exclude, request.count)

            vector_results = []
            if self.enable_rag and self.enable_vector_search and self._vector_store:
                vector_results = await self._vector_retrieval(target_category, recommended_difficulty, request.count * 2)

            kg_suggestions = await self._kg_analysis(target_category, user_skills)

            final_questions = await self._fuse_and_rank(
                sql_results=sql_results, vector_results=vector_results,
                kg_suggestions=kg_suggestions, target_count=request.count,
                difficulty=recommended_difficulty,
            )

            ai_analysis = {}
            if self.enable_ai_explanation and self._llm and final_questions:
                ai_analysis = await self._generate_ai_analysis(
                    user_profile=user_profile, questions=final_questions,
                    difficulty=recommended_difficulty, weak_points=weak_points,
                    target_category=target_category,
                )

            total_time = (time.time() - start_time) * 1000
            result = RecommendationResult(
                questions=[self._question_to_dict(q) for q in final_questions],
                ai_analysis=ai_analysis,
                meta={
                    "target_category": target_category,
                    "recommended_difficulty": recommended_difficulty,
                    "weak_points": weak_points,
                    "context": request.context,
                    "retrieval_method": "hybrid" if self.enable_rag else "sql_only",
                    "sql_result_count": len(sql_results),
                    "vector_result_count": len(vector_results),
                    "final_count": len(final_questions),
                    "total_ms": total_time,
                },
                request_id=request.request_id or f"rec_{int(time.time()*1000)}",
                generated_at=datetime.now(timezone.utc).isoformat(),
                processing_time_ms=total_time,
            )
            logger.info(f"[推荐完成] user={request.user_id} count={len(result.questions)} time={total_time:.0f}ms")
            return result
        except Exception as e:
            logger.error(f"[推荐失败] {e}", exc_info=True)
            fallback = await self._get_fallback_recommendation(request)
            fallback.processing_time_ms = (time.time() - start_time) * 1000
            fallback.meta["error"] = str(e)
            return fallback

    async def _get_user_profile(self, user_id: str) -> Dict[str, Any]:
        from agent_core.memory_persistence import MemoryPersistenceFacade
        try:
            facade = MemoryPersistenceFacade(self._session_factory)
            profile = await facade.get_profile(user_id)
            return profile.to_dict()
        except Exception:
            return {"correct_rate": 0.5, "total_questions": 0}

    async def _get_user_skills_dict(self, user_id: str) -> Dict[str, Any]:
        try:
            skills = await self._skill_aggregator.get_all_skills(user_id)
            return {s["skill_code"]: s for s in skills}
        except Exception:
            return {}

    async def _get_recently_done_ids(self, user_id: str) -> List[str]:
        try:
            async with self._session_factory() as db:
                thirty_days_ago = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                result = await db.execute(
                    select(LearningRecord.question_id).where(
                        and_(LearningRecord.user_id == user_id, LearningRecord.question_id.isnot(None),
                             LearningRecord.created_at >= thirty_days_ago)
                    ).limit(200)
                )
                return [r[0] for r in result.fetchall() if r[0]]
        except Exception:
            return []

    async def _determine_target(
        self, target_category: str, user_skills: Dict[str, Any], user_profile: Dict[str, Any]
    ) -> Tuple[str, List[str]]:
        if target_category:
            return target_category, []
        weak_points = user_profile.get("weak_points", [])
        if weak_points:
            return weak_points[0].get("category", "导数"), [w.get("category", "") for w in weak_points]
        return "导数", []

    async def _sql_retrieval(
        self, category: str, difficulty: int, exclude_ids: List[str], count: int
    ) -> List[Question]:
        async with self._session_factory() as db:
            query = select(Question).where(
                and_(Question.category == category, Question.difficulty == difficulty, Question.is_active == True)
            )
            if exclude_ids:
                query = query.where(Question.id.notin_(exclude_ids))
            query = query.order_by(Question.usage_count.asc()).limit(count * 2)
            result = await db.execute(query)
            questions = list(result.scalars().all())

            if len(questions) < count:
                relaxed = select(Question).where(
                    and_(Question.category == category,
                         Question.difficulty.between(max(1, difficulty - 1), min(5, difficulty + 1)),
                         Question.is_active == True)
                )
                if exclude_ids:
                    relaxed = relaxed.where(Question.id.notin_(exclude_ids))
                relaxed = relaxed.order_by(Question.usage_count.asc()).limit(count * 3)
                result = await db.execute(relaxed)
                questions = list(result.scalars().all())
            return questions

    async def _vector_retrieval(self, category: str, difficulty: int, count: int) -> List[Dict]:
        try:
            query_text = f"{category} 数学题目 难度{difficulty}"
            results = await self._vector_store.hybrid_search(
                query=query_text, category_filter=category,
                difficulty_range=(max(1, difficulty - 1), min(5, difficulty + 1)),
                n_results=count,
            )
            return [{
                "id": r.id, "content": r.content,
                "category": r.metadata.get("category", category),
                "difficulty": r.metadata.get("difficulty", difficulty),
                "score": r.score, "source": "vector",
            } for r in results]
        except Exception as e:
            logger.warning(f"向量检索失败: {e}")
            return []

    async def _kg_analysis(self, category: str, user_skills: Dict[str, Any]) -> List[Dict]:
        try:
            from app.services.math_skill_dag import MathSkillDAG
            dag = MathSkillDAG()
            target_skills = [code for code, node in dag._graph.items() if node.get("category") == category]
            if not target_skills:
                return []
            mastered = {code for code, s in user_skills.items() if s.get("status") == "mastered"}
            suggestions = []
            for skill_code in target_skills:
                prereqs = dag.get_prerequisites(skill_code)
                missing = [p for p in prereqs if p not in mastered]
                if missing:
                    suggestions.append({"skill_code": skill_code, "missing_prerequisites": missing, "suggestion": "建议先巩固前置知识点"})
            return suggestions
        except Exception as e:
            logger.warning(f"知识图谱分析失败: {e}")
            return []

    async def _fuse_and_rank(
        self, sql_results: List[Question], vector_results: List[Dict],
        kg_suggestions: List[Dict], target_count: int, difficulty: int,
    ) -> List[Question]:
        seen_ids = set()
        final = []
        for q in sql_results:
            if q.id not in seen_ids:
                final.append(q)
                seen_ids.add(q.id)
        if len(final) < target_count and vector_results:
            vector_ids = [v["id"] for v in vector_results if v["id"] not in seen_ids]
            if vector_ids:
                await self._fetch_vector_questions(vector_ids, final, seen_ids)
        final.sort(key=lambda q: q.usage_count if q.usage_count else 0)
        return final[:target_count]

    async def _fetch_vector_questions(self, vector_ids: List[str], final: List[Question], seen_ids: set):
        async with self._session_factory() as db:
            result = await db.execute(select(Question).where(Question.id.in_(vector_ids)))
            for q in result.scalars().all():
                if q.id not in seen_ids:
                    final.append(q)
                    seen_ids.add(q.id)

    async def _generate_ai_analysis(
        self, user_profile: Dict, questions: List[Question],
        difficulty: int, weak_points: List[str], target_category: str,
    ) -> Dict[str, Any]:
        correct_rate = user_profile.get("correct_rate", 0.5)
        question_summaries = [f"- {q.content[:80]}... (难度:{q.difficulty})" for q in questions]
        system_prompt = (
            "你是一位数学教育专家。请根据学生信息，用简洁专业的语言给出推荐理由。\n"
            "严格按JSON格式返回（不要用markdown代码块）：\n"
            '{"assessment": "水平评估", "recommendation_reason": "推荐原因", "learning_advice": "学习建议", "estimated_time_minutes": 数字}'
        )
        prompt = (
            f"### 学生概况\n- 正确率: {correct_rate:.0%}\n- 薄弱点: {weak_points or target_category}\n- 推荐难度: {difficulty}/5\n\n"
            f"### 推荐题目\n共{len(questions)}道{target_category}题目：\n" + "\n".join(question_summaries)
        )
        try:
            response = await self._llm.generate(prompt=prompt, system_prompt=system_prompt, temperature=0.3)
            content = response.content.strip()
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                import re
                m = re.search(r'\{.*\}', content, re.DOTALL)
                return json.loads(m.group()) if m else self._default_analysis(correct_rate, target_category, len(questions), difficulty)
        except Exception:
            return self._default_analysis(correct_rate, target_category, len(questions), difficulty)

    def _default_analysis(self, correct_rate: float, category: str, count: int, difficulty: int) -> Dict:
        return {
            "assessment": f"当前正确率 {correct_rate:.0%}",
            "recommendation_reason": f"推荐{count}道难度{difficulty}/5的{category}题目",
            "learning_advice": "建议先复习概念，再逐一完成",
            "estimated_time_minutes": count * 3,
        }

    async def _get_fallback_recommendation(self, request: RecommendationRequest) -> RecommendationResult:
        logger.info(f"[降级推荐] user={request.user_id}")
        try:
            async with self._session_factory() as db:
                query = select(Question).where(and_(Question.is_active == True, Question.difficulty == 3))
                if request.exclude_ids:
                    query = query.where(Question.id.notin_(request.exclude_ids))
                query = query.limit(request.count)
                result = await db.execute(query)
                questions = list(result.scalars().all())
        except Exception:
            questions = []
        return RecommendationResult(
            questions=[self._question_to_dict(q) for q in questions],
            ai_analysis={},
            meta={"target_category": request.target_category or "auto", "recommended_difficulty": 3, "retrieval_method": "fallback"},
            request_id=request.request_id or f"rec_{int(time.time()*1000)}",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _question_to_dict(q: Question) -> Dict[str, Any]:
        return {
            "id": q.id, "content": q.content, "question_type": q.question_type,
            "options": q.options, "answer": q.answer, "analysis": q.analysis,
            "category": q.category, "sub_categories": q.sub_categories,
            "knowledge_points": q.knowledge_points, "difficulty": q.difficulty,
            "estimated_time": q.estimated_time, "source": q.source,
        } if q else {}


_rag_recommender_instance: Optional[RAGRecommender] = None


async def get_rag_recommender() -> RAGRecommender:
    global _rag_recommender_instance
    if _rag_recommender_instance is None:
        vector_store = await get_vector_store() if settings.RAG_ENABLE_VECTOR_SEARCH else None
        llm_service = get_llm_service() if settings.RAG_ENABLE_AI_EXPLANATION else None
        _rag_recommender_instance = RAGRecommender(
            vector_store=vector_store, llm_service=llm_service,
            difficulty_estimator=DifficultyEstimator(), skill_aggregator=SkillAggregator(),
        )
    return _rag_recommender_instance
```

***

### 8.6 工具层（Agent Tools）

> **设计原则**: 工具层是 Agent 的"瑞士军刀"——每个工具只做一件事，30-50行代码，薄适配器，实际业务逻辑在 `app/services/` 中。
>
> **双策略兼容**: 注册到 `HybridToolRegistry` 后，所有工具自动对 LangChain ReAct 和 TaskPlanner (PlannedStrategy) 两种策略可用，无需额外配置。

#### 8.6.1 文件: `tools/recommend_tool.py` 【新建 P0】

```python
"""
智能推荐工具 — Agent 调用此工具获取个性化题目推荐。

触发场景: 用户说"推荐几道导数题"、"给我来几道极限题练练"
"""

from __future__ import annotations

from typing import Any

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability


class RecommendTool(BaseTool):
    name = "recommend_questions"
    description = "根据用户的学习情况推荐个性化数学题目，支持指定知识点、数量和场景"
    version = "1.0.0"
    capabilities = [ToolCapability.PRACTICE_GENERATION, ToolCapability.KNOWLEDGE_RETRIEVAL]

    def get_info(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [c.value for c in self.capabilities],
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "目标知识点分类，如'导数'、'极限'、'积分'"},
                    "count": {"type": "integer", "description": "推荐数量，默认5"},
                    "context": {"type": "string", "description": "practice/exam/review/error_correction/challenge"},
                },
                "required": ["category"],
            },
        }

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        try:
            from app.services.rag_recommender import get_rag_recommender, RecommendationRequest

            params = input_data.parameters or {}
            category = params.get("category", input_data.query or "")
            count = int(params.get("count", 5))
            context = params.get("context", "practice")

            recommender = await get_rag_recommender()
            result = await recommender.recommend(RecommendationRequest(
                user_id=input_data.context.get("user_id", "anonymous"),
                target_category=category,
                count=count,
                context=context,
            ))

            questions_text = "\n".join(
                f"{i+1}. {q['content'][:100]}... (难度:{q['difficulty']})"
                for i, q in enumerate(result.questions)
            )
            return ToolOutput(
                success=True,
                result=f"已为你推荐{len(result.questions)}道{category}题目：\n\n{questions_text}",
                data={"questions": result.questions, "ai_analysis": result.ai_analysis},
            )
        except Exception as e:
            return ToolOutput(success=False, error=f"推荐失败: {str(e)}")
```

#### 8.6.2 文件: `tools/skill_profile_tool.py` 【新建 P0】

```python
"""
技能画像工具 — Agent 调用此工具查询用户的学习状态。

触发场景: 用户说"我的薄弱点是什么"、"导数掌握得怎么样"
"""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability


class SkillProfileTool(BaseTool):
    name = "skill_profile"
    description = "查询用户技能画像，包括各知识点掌握度、薄弱点、推荐难度、已掌握技能和下一步学习建议"
    version = "1.0.0"
    capabilities = [ToolCapability.KNOWLEDGE_RETRIEVAL]

    def get_info(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [c.value for c in self.capabilities],
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "可选，查询特定知识点的掌握情况"},
                },
                "required": [],
            },
        }

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        try:
            from agent_core.memory_persistence import MemoryPersistenceFacade
            from app.services.skill_aggregator import SkillAggregator
            from app.services.difficulty_estimator import DifficultyEstimator

            user_id = input_data.context.get("user_id", "anonymous")
            facade = MemoryPersistenceFacade()
            profile = await facade.get_profile(user_id)

            skills = await SkillAggregator().get_all_skills(user_id)
            mastered = [s for s in skills if s["status"] == "mastered"]
            weak = [s for s in skills if s["status"] in ("novice", "learning")]

            result_lines = [
                f"## 学习画像\n",
                f"- 正确率: {profile.correct_rate:.0%}",
                f"- 推荐难度: T{profile.recommended_difficulty}",
                f"- 已掌握: {len(mastered)}个知识点",
                f"- 薄弱点: {len(weak)}个知识点",
            ]

            if profile.weak_points:
                result_lines.append(f"\n### 薄弱知识点")
                for wp in profile.weak_points[:5]:
                    result_lines.append(f"- {wp.get('category', '')} (掌握度: {wp.get('mastery', 0):.0%})")

            if mastered:
                result_lines.append(f"\n### 已掌握")
                result_lines.append(", ".join(s["skill_code"] for s in mastered[:5]))

            return ToolOutput(
                success=True,
                result="\n".join(result_lines),
                data={"skills": skills, "profile": profile.to_dict()},
            )
        except Exception as e:
            return ToolOutput(success=False, error=f"获取技能画像失败: {str(e)}")
```

#### 8.6.3 文件: `tools/explain_tool.py` 【新建 P0】

```python
"""
题目讲解工具 — Agent 调用此工具对某道数学题目进行详细讲解。

触发场景: 用户说"讲一下这道题"、"这道题为什么选C"
"""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability


class ExplainTool(BaseTool):
    name = "explain_question"
    description = "对某道数学题目进行详细讲解，包括知识点回顾、解题步骤、常见错误提示"
    version = "1.0.0"
    capabilities = [ToolCapability.KNOWLEDGE_RETRIEVAL, ToolCapability.VERIFICATION]

    def get_info(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [c.value for c in self.capabilities],
            "input_schema": {
                "type": "object",
                "properties": {
                    "question_id": {"type": "string", "description": "题目ID（可选）"},
                    "question_content": {"type": "string", "description": "题目内容（如果没有ID）"},
                    "user_answer": {"type": "string", "description": "用户的答案（可选）"},
                },
                "required": [],
            },
        }

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        try:
            from app.data.database import get_db_session
            from app.data.models import Question
            from app.services.llm_service import get_llm_service

            params = input_data.parameters or {}
            question_id = params.get("question_id")
            question_content = params.get("question_content", input_data.query)
            user_answer = params.get("user_answer")

            # 如果有ID，从数据库获取完整题目
            if question_id:
                async with get_db_session() as db:
                    q = await db.get(Question, question_id)
                    if q:
                        question_content = q.content
                        correct_answer = q.answer
                        analysis = q.analysis or ""
                        category = q.category
                    else:
                        return ToolOutput(success=False, error=f"未找到题目: {question_id}")
            else:
                correct_answer = "未知"
                analysis = ""
                category = "数学"

            llm = get_llm_service()
            system_prompt = (
                "你是一位数学老师。请对以下题目进行详细讲解，包括：\n"
                "1. 考察的知识点\n2. 解题思路和步骤\n3. 常见错误提醒\n"
                "如果用户给出了答案，请判断对错并分析错误原因。"
            )
            prompt = (
                f"题目: {question_content}\n"
                f"知识点: {category}\n"
                f"正确答案: {correct_answer}\n"
                f"题库解析: {analysis}\n"
            )
            if user_answer:
                prompt += f"用户答案: {user_answer}\n请判断对错并分析。"

            response = await llm.generate_with_math_model(prompt=prompt, system_prompt=system_prompt)
            return ToolOutput(success=True, result=response.content)
        except Exception as e:
            return ToolOutput(success=False, error=f"讲解失败: {str(e)}")
```

#### 8.6.4 文件: `tools/search_tool.py` 【新建 P1】

```python
"""
题库搜索工具 — Agent 调用此工具在题库中搜索符合条件的题目。

触发场景: 用户说"找一些关于微积分基本定理的题目"、"有没有不定积分的计算题"
"""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability


class SearchTool(BaseTool):
    name = "search_questions"
    description = "在题库中搜索符合条件的数学题目，支持按知识点、难度、关键词搜索"
    version = "1.0.0"
    capabilities = [ToolCapability.KNOWLEDGE_RETRIEVAL]

    def get_info(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [c.value for c in self.capabilities],
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词或描述"},
                    "category": {"type": "string", "description": "知识点分类"},
                    "difficulty": {"type": "integer", "description": "难度等级 1-5"},
                    "limit": {"type": "integer", "description": "返回数量，默认5"},
                },
                "required": ["query"],
            },
        }

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        try:
            from app.services.vector_store import get_vector_store

            params = input_data.parameters or {}
            query = params.get("query", input_data.query)
            category = params.get("category")
            difficulty = params.get("difficulty")
            limit = int(params.get("limit", 5))

            vs = await get_vector_store()
            difficulty_range = None
            if difficulty:
                difficulty_range = (difficulty, difficulty)

            results = await vs.hybrid_search(
                query=query, category_filter=category,
                difficulty_range=difficulty_range, n_results=limit,
            )

            if not results:
                return ToolOutput(success=True, result="未找到匹配的题目。")

            output = "\n".join(
                f"{i+1}. [{r.id}] {r.content[:100]}... (难度:{r.metadata.get('difficulty', '?')}, 相似度:{r.score:.2f})"
                for i, r in enumerate(results)
            )
            return ToolOutput(
                success=True,
                result=f"找到 {len(results)} 道相关题目：\n\n{output}",
                data={"results": [{"id": r.id, "content": r.content, "score": r.score} for r in results]},
            )
        except Exception as e:
            return ToolOutput(success=False, error=f"搜索失败: {str(e)}")
```

#### 8.6.5 文件: `tools/error_book_tool.py` 【新建 P1】

```python
"""
错题本分析工具 — Agent 调用此工具分析用户的错题记录。

触发场景: 用户说"看看我的错题"、"分析一下我经常错的知识点"
"""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability


class ErrorBookTool(BaseTool):
    name = "error_book_analysis"
    description = "分析用户的错题记录，找出薄弱知识点和错误模式，提供针对性建议"
    version = "1.0.0"
    capabilities = [ToolCapability.ERROR_BOOK_MANAGEMENT, ToolCapability.KNOWLEDGE_RETRIEVAL]

    def get_info(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [c.value for c in self.capabilities],
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "分析最近N道错题，默认10"},
                },
                "required": [],
            },
        }

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        try:
            from app.services.error_book_sync import ErrorBookSkillSyncService

            user_id = input_data.context.get("user_id", "anonymous")
            service = ErrorBookSkillSyncService()
            summary = await service.get_skill_impact_summary(user_id)

            if summary["total_error_records"] == 0:
                return ToolOutput(success=True, result="暂无错题记录，继续保持！")

            lines = [
                f"## 错题分析\n",
                f"- 总错题数: {summary['total_error_records']}",
                f"- 已掌握: {summary['mastered_errors']}",
                f"- 待攻克: {summary['unmastered_errors']}",
            ]

            if summary.get("weak_categories"):
                lines.append(f"\n### 薄弱知识点 Top5")
                for wc in summary["weak_categories"]:
                    lines.append(f"- {wc['category']}: {wc['count']}道错题")

            lines.append(f"\n建议：优先攻克数量最多的薄弱知识点，每道错题至少重新做2遍。")

            return ToolOutput(success=True, result="\n".join(lines), data=summary)
        except Exception as e:
            return ToolOutput(success=False, error=f"错题分析失败: {str(e)}")
```

#### 8.6.6 文件: `tools/__init__.py` 【修改】

**修改为**:

```python
"""
工具层初始化 — 注册所有工具到 HybridToolRegistry。
"""

from __future__ import annotations

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability
from tools.hybrid_registry import HybridToolRegistry, ToolNotFoundError, ToolExecutionError
from tools.vision_tool import VisionTool, VisionToolAdapter
from tools.recommend_tool import RecommendTool
from tools.skill_profile_tool import SkillProfileTool
from tools.explain_tool import ExplainTool
from tools.search_tool import SearchTool
from tools.error_book_tool import ErrorBookTool

_registry: HybridToolRegistry = None


def get_registry() -> HybridToolRegistry:
    global _registry
    if _registry is None:
        _registry = HybridToolRegistry()
        _registry.register(VisionToolAdapter(VisionTool()))
        _registry.register(RecommendTool())
        _registry.register(SkillProfileTool())
        _registry.register(ExplainTool())
        _registry.register(SearchTool())
        _registry.register(ErrorBookTool())
    return _registry


ToolRegistry = HybridToolRegistry
```

***

### 8.7 API接口层

#### 文件: `app/api/recommendation_api.py` 【新建】

```python
"""
推荐系统 API 接口 — 提供 RESTful API 端点。

端点列表：
- POST /api/recommend/questions    获取个性化推荐题目
- POST /api/recommend/explain      获取推荐解释
- GET  /api/recommend/skill-profile 获取技能画像摘要
- POST /api/recommend/ai-analyze   AI分析题目难度
- POST /api/recommend/questions/import 批量导入题目
- POST /api/recommend/vector-search    向量搜索
- GET  /api/recommend/health       健康检查
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field

from app.services.rag_recommender import (
    RecommendationRequest, get_rag_recommender,
)
from app.services.vector_store import get_vector_store
from app.services.llm_service import get_llm_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recommend", tags=["智能推荐"])


class RecommendQuestionsRequest(BaseModel):
    target_category: Optional[str] = Field(None)
    count: int = Field(default=5, ge=1, le=20)
    context: str = Field(default="practice")
    exclude_ids: List[str] = Field(default_factory=list)


class ImportQuestionsRequest(BaseModel):
    questions: List[Dict[str, Any]]


class VectorSearchRequest(BaseModel):
    query: str
    category: Optional[str] = None
    difficulty_min: Optional[int] = Field(None, ge=1, le=5)
    difficulty_max: Optional[int] = Field(None, ge=1, le=5)
    n_results: int = Field(default=10, ge=1, le=50)


@router.post("/questions")
async def recommend_questions(request: RecommendQuestionsRequest, http_request: Request, background_tasks: BackgroundTasks):
    try:
        user_id = getattr(http_request.state, "user_id", None)
        if not user_id:
            raise HTTPException(status_code=401, detail="未认证")
        recommender = await get_rag_recommender()
        result = await recommender.recommend(RecommendationRequest(
            user_id=user_id, target_category=request.target_category or "",
            count=request.count, context=request.context,
            exclude_ids=request.exclude_ids or [],
        ))
        return {
            "success": True,
            "data": {"questions": result.questions, "ai_analysis": result.ai_analysis, "meta": result.meta},
            "request_id": result.request_id,
            "generated_at": result.generated_at,
            "processing_time_ms": result.processing_time_ms,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"推荐失败: {str(e)}")


@router.post("/explain")
async def explain_recommendation(request: RecommendQuestionsRequest, http_request: Request):
    try:
        user_id = getattr(http_request.state, "user_id", None)
        if not user_id:
            raise HTTPException(status_code=401, detail="未认证")
        recommender = await get_rag_recommender()
        result = await recommender.recommend(RecommendationRequest(
            user_id=user_id, target_category=request.target_category or "",
            count=min(request.count, 3), context=request.context,
            exclude_ids=request.exclude_ids or [],
        ))
        return {"success": True, "data": {"ai_analysis": result.ai_analysis, "meta": result.meta}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/skill-profile")
async def get_skill_profile(http_request: Request):
    try:
        user_id = getattr(http_request.state, "user_id", None)
        if not user_id:
            raise HTTPException(status_code=401, detail="未认证")
        from agent_core.memory_persistence import MemoryPersistenceFacade
        facade = MemoryPersistenceFacade()
        profile = await facade.get_profile(user_id)
        return {
            "success": True,
            "data": {
                "user_id": user_id, "correct_rate": profile.correct_rate,
                "recommended_difficulty": profile.recommended_difficulty,
                "weak_points": profile.weak_points[:5], "strong_points": profile.strong_points[:5],
                "total_skills": len(profile.skills),
                "mastered_count": sum(1 for s in profile.skills if s["status"] == "mastered"),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai-analyze")
async def ai_analyze_question(http_request: Request):
    try:
        body = await http_request.json()
        question_content = body.get("content", "")
        category = body.get("category", "数学")
        if not question_content:
            raise HTTPException(status_code=400, detail="题目内容不能为空")
        result = await get_llm_service().analyze_question_difficulty(question_content, category)
        return {"success": True, "data": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/questions/import")
async def import_questions(request: ImportQuestionsRequest, http_request: Request):
    try:
        user_id = getattr(http_request.state, "user_id", None)
        if not user_id:
            raise HTTPException(status_code=401, detail="未认证")
        from app.services.question_importer import QuestionImporter
        vs = await get_vector_store()
        importer = QuestionImporter(vector_store=vs)
        result = await importer.import_from_dict_list(request.questions)
        return {"success": True, "data": {"total": result.total, "success": result.success, "failed": result.failed, "imported_ids": result.imported_ids}, "errors": result.errors[:10] if result.errors else None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vector-search")
async def vector_search(request: VectorSearchRequest, http_request: Request):
    try:
        user_id = getattr(http_request.state, "user_id", None)
        if not user_id:
            raise HTTPException(status_code=401, detail="未认证")
        vs = await get_vector_store()
        difficulty_range = None
        if request.difficulty_min and request.difficulty_max:
            difficulty_range = (request.difficulty_min, request.difficulty_max)
        results = await vs.hybrid_search(query=request.query, category_filter=request.category, difficulty_range=difficulty_range, n_results=request.n_results)
        return {"success": True, "data": {"results": [{"id": r.id, "content": r.content[:100], "category": r.metadata.get("category", ""), "difficulty": r.metadata.get("difficulty", ""), "score": round(r.score, 3)} for r in results], "total": len(results)}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def recommend_health():
    checks = {}
    try:
        llm = get_llm_service()
        checks["llm_service"] = {"status": "ready", "cache": llm.get_cache_stats()}
    except Exception as e:
        checks["llm_service"] = {"status": "error", "detail": str(e)}
    try:
        vs = await get_vector_store()
        stats = await vs.get_collection_stats()
        checks["vector_store"] = {"status": "ready", "stats": stats}
    except Exception as e:
        checks["vector_store"] = {"status": "error", "detail": str(e)}
    return {"status": "healthy" if all(c.get("status") == "ready" for c in checks.values()) else "degraded", "service": "rag-recommendation-engine", "checks": checks}
```

***

### 8.8 主应用集成

#### 文件: `main.py` 【修改，追加以下内容】

**1. 在文件顶部导入区域追加**（约第41行后）:

```python
from app.api.recommendation_api import router as recommendation_router
```

**2. 在** **`lifespan`** **函数中，`init_db()`** **之后追加**:

```python
# ── RAG 推荐系统初始化 ──
if settings.RAG_ENABLED:
    try:
        if settings.RAG_ENABLE_VECTOR_SEARCH:
            from app.services.vector_store import get_vector_store
            await get_vector_store()
            logger.info("向量数据库初始化完成")
    except Exception as e:
        logger.warning(f"向量数据库初始化失败: {e}")
    try:
        if settings.RAG_ENABLE_AI_EXPLANATION:
            from app.services.llm_service import get_llm_service
            get_llm_service()
            logger.info("LLM服务初始化完成")
    except Exception as e:
        logger.warning(f"LLM服务初始化失败: {e}")
# ── END RAG ──
```

**3. 在** **`include_router`** **区域追加**:

```python
app.include_router(recommendation_router)
```

***

## 9. 测试策略

### 9.1 文件: `tests/test_rag_recommender.py` 【新建】

```python
"""
RAG 推荐引擎 + 工具层测试

覆盖：
1. LLMService 基础功能
2. VectorStoreManager 基础功能
3. RAGRecommender 降级策略
4. 工具层基础功能
5. DifficultyEstimator 集成
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.llm_service import LLMService, LLMResponse
from app.services.vector_store import VectorStoreManager, VectorSearchResult
from app.services.rag_recommender import RAGRecommender, RecommendationRequest, RecommendationResult


@pytest.fixture
def mock_llm_service():
    service = MagicMock(spec=LLMService)
    service.generate = AsyncMock(return_value=LLMResponse(
        content='{"assessment":"测试","recommendation_reason":"测试","learning_advice":"测试","estimated_time_minutes":10}',
        model="qwen-max", provider="dashscope",
    ))
    return service


@pytest.fixture
def mock_vector_store():
    store = MagicMock(spec=VectorStoreManager)
    store.initialize = AsyncMock()
    store.hybrid_search = AsyncMock(return_value=[
        VectorSearchResult(id="v001", content="测试题", metadata={"category": "导数", "difficulty": 3}, score=0.85, distance=0.15),
    ])
    return store


# ── LLM Service ──

@pytest.mark.asyncio
async def test_llm_service_singleton():
    s1 = LLMService()
    s2 = LLMService()
    assert s1 is s2


@pytest.mark.asyncio
async def test_llm_service_cache_key():
    key = LLMService()._make_cache_key("hello", None, "qwen-max")
    assert len(key) == 32


def test_llm_response_serialization():
    r = LLMResponse("hello", "qwen-max", "dashscope", {"total_tokens": 10}, 100.0)
    d = r.to_dict()
    assert d["content"] == "hello"
    assert d["latency_ms"] == 100.0


# ── Vector Store ──

def test_clean_metadata():
    meta = {"name": "test", "count": 5, "rate": 0.85, "is_active": True, "tags": ["a", "b"], "nested": {"k": "v"}, "none_val": None}
    cleaned = VectorStoreManager._clean_metadata(meta)
    assert cleaned["name"] == "test"
    assert cleaned["count"] == 5
    assert isinstance(cleaned["tags"], str)
    assert "none_val" not in cleaned


def test_keyword_scores():
    store = VectorStoreManager(persist_directory="./test_chroma")
    query = "导数 计算 f(x)"
    results = [
        VectorSearchResult("1", "求函数 f(x)=x² 的导数", {"category": "导数"}, 0.0, 0.0),
        VectorSearchResult("2", "三角函数 sin²x+cos²x", {"category": "三角函数"}, 0.0, 0.0),
    ]
    scores = store._calculate_keyword_scores(query, results)
    assert scores["1"] > scores["2"]


# ── RAG Recommender ──

@pytest.mark.asyncio
async def test_recommender_fallback():
    recommender = RAGRecommender()
    result = await recommender._get_fallback_recommendation(RecommendationRequest(user_id="test", target_category="导数", count=3))
    assert isinstance(result, RecommendationResult)
    assert result.meta.get("retrieval_method") == "fallback"


@pytest.mark.asyncio
async def test_question_to_dict():
    from app.data.models import Question
    q = Question(id="Q001", content="测试题", question_type="选择题", options=["A", "B"], answer="A", category="导数", difficulty=3)
    d = RAGRecommender._question_to_dict(q)
    assert d["id"] == "Q001"
    assert d["category"] == "导数"


# ── DifficultyEstimator ──

@pytest.mark.asyncio
async def test_score_to_difficulty():
    from app.services.difficulty_estimator import DifficultyEstimator
    assert DifficultyEstimator._score_to_difficulty(0.95) == 5
    assert DifficultyEstimator._score_to_difficulty(0.60) == 3
    assert DifficultyEstimator._score_to_difficulty(0.10) == 1


# ── Tool Layer ──

@pytest.mark.asyncio
async def test_recommend_tool_registration():
    from tools.recommend_tool import RecommendTool
    from tools.hybrid_registry import HybridToolRegistry
    registry = HybridToolRegistry()
    registry.register(RecommendTool())
    assert registry.has_tool("recommend_questions")


@pytest.mark.asyncio
async def test_skill_profile_tool_registration():
    from tools.skill_profile_tool import SkillProfileTool
    from tools.hybrid_registry import HybridToolRegistry
    registry = HybridToolRegistry()
    registry.register(SkillProfileTool())
    assert registry.has_tool("skill_profile")


@pytest.mark.asyncio
async def test_all_tools_registered():
    from tools import get_registry
    registry = get_registry()
    expected = ["vision_tool", "recommend_questions", "skill_profile", "explain_question", "search_questions", "error_book_analysis"]
    for name in expected:
        assert registry.has_tool(name), f"工具 {name} 未注册"
```

### 9.2 运行测试

```bash
venv\Scripts\activate && pip install pytest pytest-asyncio pytest-cov -i https://pypi.tuna.tsinghua.edu.cn/simple
# 运行所有推荐系统测试
pytest tests/test_rag_recommender.py -v

# 带覆盖率报告
pytest tests/test_rag_recommender.py -v --cov=app.services --cov=tools --cov-report=term-missing
```

### 9.3 手动验证流程

```bash
# 1. 启动服务
python main.py

# 2. 健康检查
curl http://localhost:8000/api/recommend/health

# 3. 导入测试题目
curl -X POST http://localhost:8000/api/recommend/questions/import \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"questions":[{"id":"demo001","content":"求 f(x)=x² 的导数","category":"导数","answer":"2x","difficulty":3}]}'

# 4. 获取推荐
curl -X POST http://localhost:8000/api/recommend/questions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"target_category":"导数","count":3,"context":"practice"}'
```

***

## 10. 部署指南

### 当前阶段（通义千问 API，零 GPU）

```bash
# 1. 创建虚拟环境（如果还没有）
python -m venv venv

# 2. 激活虚拟环境（Windows PowerShell）
venv\Scripts\activate

# 3. 安装基础依赖（使用清华源）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 4. 安装 RAG 额外依赖（使用清华源）
pip install chromadb pandas openpyxl numpy -i https://pypi.tuna.tsinghua.edu.cn/simple

# 5. 配置 .env
# DASHSCOPE_API_KEY=sk-xxx
# LLM_API_KEY=sk-xxx

# 6. 启动服务
python main.py
```

### 后续切换本地模型（只改 .env）

```env
# Ollama 方式
LLM_API_BASE=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen2.5-math:7b
LLM_MATH_MODEL=qwen2.5-math:7b

# 或 vLLM 方式
# LLM_API_BASE=http://localhost:8000/v1
# LLM_API_KEY=EMPTY
```

***

## 11. 超出范围

* 深度知识追踪模型（DKT/SAKT/BKT）

* 独立组卷大模型

* 公式编辑器、思维导图、实验模拟器

* 前端 UI 改动

* 用户认证系统改造

***

## 12. 已知风险与注意事项

> **Agent 开发时必读**：以下风险已在文档中修复，但 Agent 在实现时仍需注意。

### 12.1 已修复的兼容性问题

| # | 风险                                             | 修复方案                                                                                   | 验证方法                              |
| - | ---------------------------------------------- | -------------------------------------------------------------------------------------- | --------------------------------- |
| 1 | ToolOutput 缺少 `data` 字段                        | 在 `base_tool.py` 新增 `data: Dict[str, Any]` 字段                                          | 工具调用不报 Pydantic 校验错误              |
| 2 | LLMService 单例导致数学模型无法独立创建                      | 删除 `get_llm_service_for_math()`，统一用 `get_llm_service()` + `generate_with_math_model()` | explain\_tool 和 ai-analyze 接口正常工作 |
| 3 | `_fuse_and_rank` 中 `asyncio.ensure_future` 非阻塞 | 改为 `async def` + `await self._fetch_vector_questions()`                                | 向量检索结果能正确合并到最终推荐                  |

### 12.2 运行时风险

| 风险                        | 影响           | 缓解措施                         |
| ------------------------- | ------------ | ---------------------------- |
| 通义千问 API 限流               | 推荐接口超时       | 5分钟缓存 + 降级策略（纯 SQL）          |
| ChromaDB 向量库初始化失败         | 语义搜索不可用      | 自动降级为纯 SQL 查询                |
| 题库数据格式不统一                 | 导入失败         | QuestionImporter 自动补默认值      |
| 工具注册遗漏                    | Agent 无法调用工具 | 测试用例验证所有工具已注册                |
| 后续本地模型切换                  | 接口不兼容        | 接口兼容 OpenAI SDK，只改配置         |
| sentence-transformers 下载慢 | 向量库初始化卡住     | 初次启动需要网络，可预下载模型              |
| SQLite 并发写入               | 高并发时锁冲突      | 当前仅支持 10 并发，后续可迁移 PostgreSQL |

### 12.3 代码实现注意事项

1. **虚拟环境 + 清华源**：Agent 在终端执行 `pip install` 或 `python` 命令前，必须先执行 `venv\Scripts\activate` 激活虚拟环境，所有 pip 安装必须使用 `-i https://pypi.tuna.tsinghua.edu.cn/simple` 清华源
2. **异步调用链**：所有涉及数据库和 LLM 的操作必须是 `async`，不能在 async 函数中调用同步阻塞代码
3. **导入路径**：所有新增文件使用绝对导入（`from app.services.xxx import ...`），不要使用相对导入
4. **数据库 session**：必须使用 `async with get_db_session() as db:` 模式，不要手动管理 session 生命周期
5. **Pydantic v2**：`model_validate` 替代 `parse_obj`，`model_dump` 替代 `dict()`
6. **ChromaDB 初始化**：`chromadb.PersistentClient` 需要 `settings=ChromaSettings(anonymized_telemetry=False)` 避免遥测警告
7. **ToolOutput 构造**：始终使用 `success=True/False` 和 `error` 字段，不要抛出未捕获异常

***

## 13. 成功指标

* 推荐接口 `/api/recommend/questions` 响应时间 < 3s

* 健康检查 `/api/recommend/health` 返回 "healthy"

* 所有工具注册成功（6个工具）

* 测试覆盖率 > 80%

* 题库导入: 1000 道题导入无错误

* 降级策略: 关掉 ChromaDB 后推荐仍可用

***

## 14. 阶段计划（Phase Plan）

> 按以下顺序实施，每个阶段完成后运行验证命令。

### Phase 0 — 基础设施（先决条件）

* [ ] **E0-1: 修改现有文件** — 修改 `tools/base_tool.py`（ToolOutput 加 data 字段）、`requirements.txt`（追加依赖）、`app/config/settings.py`（追加 15 个配置项）、`.env`（追加环境变量）

  * 验证: `python -c "from app.config.settings import settings; print(settings.LLM_API_BASE)"`

  * 类型: AFK

### Phase 1 — 核心 Services 层（按依赖顺序）

* [ ] **E1-1: LLM 服务模块** — 新建 `app/services/llm_service.py`，单例模式，支持缓存、流式、TIR

  * 验证: `python -c "from app.services.llm_service import get_llm_service; print(get_llm_service().model)"`

  * 类型: AFK

  * 依赖: E0-1

* [ ] **E1-2: 向量数据库模块** — 新建 `app/services/vector_store.py`，ChromaDB 持久化存储，支持语义搜索 + 混合搜索

  * 验证: `python -c "import asyncio; asyncio.run(__import__('app.services.vector_store', fromlist=['get_vector_store']).get_vector_store())"`

  * 类型: AFK

  * 依赖: E0-1

* [ ] **E1-3: 题库导入模块** — 新建 `app/services/question_importer.py`，CSV/Excel 批量导入 → 数据库 + 向量库

  * 验证: 用测试 CSV 导入并确认数据库有数据

  * 类型: AFK

  * 依赖: E1-2

* [ ] **E1-4: RAG 推荐引擎** — 新建 `app/services/rag_recommender.py`，6步工作流，三路检索 + 融合排序 + AI 分析

  * 验证: `python -c "from app.services.rag_recommender import RAGRecommender; print('import ok')"`

  * 类型: AFK

  * 依赖: E1-1, E1-2, E1-3

### Phase 2 — 工具层 + API 层

* [ ] **E2-1: 5个工具** — 新建 5 个工具文件 + 修改 `tools/__init__.py`

  * 验证: `python -c "from tools import get_registry; r = get_registry(); print([t for t in ['recommend_questions','skill_profile','explain_question','search_questions','error_book_analysis'] if r.has_tool(t)])"`

  * 类型: AFK

  * 依赖: E1-4

* [ ] **E2-2: 推荐 API 接口** — 新建 `app/api/recommendation_api.py`，7 个端点

  * 验证: 启动服务后 `curl /api/recommend/health`

  * 类型: HITL（需要人工验证 API 返回格式）

  * 依赖: E2-1

* [ ] **E2-3: 主应用集成** — 修改 `main.py`，追加路由注册 + lifespan 初始化

  * 验证: `python main.py` 启动不报错

  * 类型: AFK

  * 依赖: E2-2

### Phase 3 — 测试与验证

* [ ] **E3-1: 单元测试** — 新建 `tests/test_rag_recommender.py`，覆盖 LLM、向量库、推荐引擎、工具层

  * 验证: `pytest tests/test_rag_recommender.py -v` 全部通过

  * 类型: AFK

  * 依赖: E2-3

* [ ] **E3-2: 覆盖率验证** — 运行覆盖率报告，确保 ≥ 80%

  * 验证: `pytest tests/test_rag_recommender.py -v --cov=app.services --cov=tools --cov-report=term-missing`

  * 类型: HITL（需要人工确认覆盖率达标）

  * 依赖: E3-1

* [ ] **E3-3: 端到端验证** — 导入测试题目 → 调用推荐接口 → 确认返回正确数据

  * 验证: 按 9.3 节手动验证流程执行

  * 类型: HITL（需要人工验证推荐结果质量）

  * 依赖: E3-1

***

## 15. 未解决歧义日志

| # | 主题     | 缺失信息                                                    | 影响               | 建议                             |
| - | ------ | ------------------------------------------------------- | ---------------- | ------------------------------ |
| 1 | 题库数据   | 学校题库的具体格式和内容尚未确认                                        | 影响 E1-3 题库导入的列映射 | 开发前先获取一份样例题库 CSV               |
| 2 | 用户认证   | 当前 API 依赖 `http_request.state.user_id`，但认证中间件的具体实现未确认   | 影响 API 测试        | 测试时可在中间件中 hardcode 测试 user\_id |
| 3 | 嵌入模型   | `all-MiniLM-L6-v2` 对中文支持一般，后续可能需换为 BGE 系列               | 影响向量检索精度         | 先用默认模型，后续根据实际效果调整              |
| 4 | 本地模型部署 | 后续部署的具体模型（Qwen2.5-Math-7B vs 其他）和部署方式（Ollama vs vLLM）未定 | 影响长期规划           | 接口已兼容，切换时只需改 .env              |

***

## 16. 完成定义（Definition of Done）

以下条件**全部满足**才算开发完成：

* [ ] 所有 11 个新建文件 + 4 个修改文件存在且内容正确

* [ ] `python main.py` 启动无报错

* [ ] `curl /api/recommend/health` 返回 `{"status": "healthy"}`

* [ ] `pytest tests/test_rag_recommender.py -v` 全部通过

* [ ] 测试覆盖率 ≥ 80%

* [ ] 推荐接口返回题目数据 + AI 分析

* [ ] Agent 对话中能调用工具（如"推荐几道导数题"）

* [ ] 所有工具注册成功（6 个工具）

* [ ] 关闭 ChromaDB 后推荐仍可用（降级策略生效）

* [ ] 文档中无 TODO 或 FIXME 标记

***

## 附录A: 文件创建清单

### 新建文件（11个）

| #  | 文件路径                                | 说明        |
| -- | ----------------------------------- | --------- |
| 1  | `app/services/llm_service.py`       | LLM 服务模块  |
| 2  | `app/services/vector_store.py`      | 向量数据库模块   |
| 3  | `app/services/question_importer.py` | 题库导入模块    |
| 4  | `app/services/rag_recommender.py`   | RAG 推荐引擎  |
| 5  | `app/api/recommendation_api.py`     | 推荐 API 接口 |
| 6  | `tools/recommend_tool.py`           | 智能推荐工具    |
| 7  | `tools/skill_profile_tool.py`       | 技能画像工具    |
| 8  | `tools/explain_tool.py`             | 题目讲解工具    |
| 9  | `tools/search_tool.py`              | 题库搜索工具    |
| 10 | `tools/error_book_tool.py`          | 错题本分析工具   |
| 11 | `tests/test_rag_recommender.py`     | 测试文件      |

### 修改文件（5个）

| # | 文件路径                     | 修改内容                                 |
| - | ------------------------ | ------------------------------------ |
| 1 | `tools/base_tool.py`     | ToolOutput 新增 `data` 字段              |
| 2 | `main.py`                | 追加路由 + lifespan 初始化                  |
| 3 | `app/config/settings.py` | 追加 15 个配置字段                          |
| 4 | `tools/__init__.py`      | 注册所有工具                               |
| 5 | `requirements.txt`       | 追加 chromadb, pandas, openpyxl, numpy |

***

## 附录B: 依赖安装命令

> **重要**: Trae coding agent 在沙箱中操作，每次安装依赖前必须先激活虚拟环境。
> 所有 pip 命令使用清华源加速下载。

```bash
# 1. 激活虚拟环境（必须最先执行）
venv\Scripts\activate

# 2. 安装基础依赖
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 3. 安装 RAG 额外依赖
pip install chromadb pandas openpyxl numpy -i https://pypi.tuna.tsinghua.edu.cn/simple

# 4. 安装测试依赖
pip install pytest pytest-asyncio pytest-cov -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 虚拟环境说明

| 项目                   | 说明                                              |
| -------------------- | ----------------------------------------------- |
| **环境名称**             | `venv`（项目根目录下）                                  |
| **创建命令**             | `python -m venv venv`                           |
| **激活命令 (Windows)**   | `venv\Scripts\activate`                         |
| **激活命令 (Linux/Mac)** | `source venv/bin/activate`                      |
| **pip 源**            | 清华源: `https://pypi.tuna.tsinghua.edu.cn/simple` |

### Agent 操作规范

Agent 在终端执行任何 pip install 或 python 命令时，**必须遵循以下顺序**：

```bash
# 正确操作流程：
Step 1: venv\Scripts\activate          # 先激活虚拟环境
Step 2: pip install xxx -i https://pypi.tuna.tsinghua.edu.cn/simple  # 再安装（用清华源）
Step 3: python main.py                  # 最后运行

# 错误示例（不要这样做）：
# ❌ 直接 pip install（未激活虚拟环境，安装到沙箱系统 Python）
# ❌ 不加清华源（下载速度慢，可能超时）
```

***

## 附录C: 关键配置项汇总

```python
# app/config/settings.py 新增字段
LLM_API_KEY = ""                          # 环境变量 LLM_API_KEY
LLM_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_MODEL = "qwen-max"
LLM_MATH_MODEL = "qwen-turbo"
LLM_TEMPERATURE = 0.3
LLM_MAX_TOKENS = 4096
LLM_STREAMING = True
VECTOR_DB_PATH = "./data/chroma_db"
RAG_ENABLED = True
RAG_ENABLE_AI_EXPLANATION = True
RAG_ENABLE_VECTOR_SEARCH = True
RAG_DEFAULT_RECOMMEND_COUNT = 5
RAG_HYBRID_SEARCH_TOP_K = 20
```

### 实施顺序

按 Phase Plan（第14节）执行：

1. **Phase 0**: 修改现有文件（base\_tool.py, settings.py, requirements.txt, .env）
2. **Phase 1**: 新建 services 层（llm\_service → vector\_store → question\_importer → rag\_recommender）
3. **Phase 2**: 新建工具层 + API 层 + 修改 tools/__init__.py + 修改 main.py
4. **Phase 3**: 编写测试 → 运行验证 → 覆盖率检查 → 端到端验证

