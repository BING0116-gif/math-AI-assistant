# ToolRegistry（工具注册中心）技术开发文档

> **文档版本**：v1.0
> **编写日期**：2026-05-03
> **目标读者**：Cursor 中的大模型（用于指导功能实现）、开发人员
> **关联设计文档**：`docs/AI_Agent 实现方案.md`、`docs/技术架构全面评估与优化方案.md`

---

## 一、功能概述

### 1.1 功能定位

ToolRegistry 是数学 AI Agent 系统的**工具基础设施层**，充当 Agent 核心层与工具层之间的统一中间件。它负责将分散的工具实现统一纳管，为上层组件（TaskPlanner、ToolSelector、Agent 主类）提供标准化的工具注册、发现、获取和调用能力。

### 1.2 解决的痛点

| 当前问题 | 具体表现 | ToolRegistry 如何解决 |
|---------|---------|---------------------|
| 工具管理散乱 | `SimpleAgent` 中 `tools: Dict` + `vision_tool` 分离存放 | 统一注册入口，所有工具归入同一 Registry |
| 无工具元数据 | 工具无描述、无能力标签，LLM 无法感知可用工具 | 每个工具携带 `description`、`capabilities` 等元数据 |
| LLM 无法选工具 | 当前 LLM 仅靠 prompt 回答，不知道有哪些工具可用 | `get_all_descriptions()` 聚合描述注入 LLM prompt |
| 扩展性差 | 添加新工具需修改 Agent 构造函数 | 新工具只需实现 `BaseTool` 接口并 `register()` |
| 无统一容错 | 各工具调用点需单独编写异常处理 | `execute_safe()` 统一提供监控和容错 |

### 1.3 核心价值

让 LLM 从"盲目回答"升级为"按需调用工具"，是实现 Agent 自主规划+智能工具选择能力的**基石模块**。

---

## 二、技术栈要求

### 2.1 已有依赖（直接使用，无需新增）

| 依赖 | 版本 | 用途 |
|-----|------|------|
| Python | >=3.10 | 运行时（使用 `match` 语法、`\|` 类型联合语法） |
| pydantic | >=2.0.0 | 数据模型定义与校验（`BaseModel`、`Field`） |
| fastapi | >=0.104.0 | API 框架（ToolRegistry 的管理接口） |
| langchain | >=0.1.0 | Agent 框架（与 LangChain Tool 互操作） |

### 2.2 需新增依赖

| 依赖 | 版本 | 用途 |
|-----|------|------|
| 无新增 | — | ToolRegistry 核心功能仅依赖标准库 + 已有依赖 |

### 2.3 标准库依赖

| 模块 | 用途 |
|-----|------|
| `abc` | 定义 `BaseTool` 抽象基类 |
| `enum` | 定义 `ToolCapability` 枚举 |
| `logging` | 工具注册/调用日志 |
| `time` | 执行耗时统计 |
| `typing` | 类型注解 |
| `dataclasses` | 数据模型 |
| `uuid` | 生成工具调用唯一 ID |
| `traceback` | 异常堆栈提取 |

---

## 三、系统架构设计

### 3.1 分层架构定位

```
┌─────────────────────────────────────────────────────────┐
│                    用户界面层 (UI)                        │
│              FastAPI + HTML + JavaScript                  │
└────────────────────────┬────────────────────────────────┘
                         ↓
┌────────────────────────┴────────────────────────────────┐
│                  Agent 核心层 (Core)                      │
│                                                          │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐           │
│  │TaskPlanner│  │ToolSelector│  │MemoryManager│          │
│  └─────┬─────┘  └─────┬─────┘  └───────────┘           │
│        │              │                                   │
│        └──────┬───────┘                                  │
│               ↓                                          │
│  ┌─────────────────────────┐  ┌───────────┐             │
│  │     ToolRegistry ★      │  │Reflexion  │             │
│  │   (本次开发目标)         │  │Validator  │             │
│  └────────────┬────────────┘  └───────────┘             │
└───────────────┼─────────────────────────────────────────┘
                ↓
┌───────────────────────────────────────────────────────────┐
│                    工具层 (Tools)                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│  │MathSolver│ │VisionTool│ │PlotTool  │ │Practice  │    │
│  │          │ │          │ │(新增)    │ │Generator │    │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                 │
│  │Knowledge │ │ErrorBook │ │更多工具  │                 │
│  │Retriever │ │Tool      │ │...       │                 │
│  └──────────┘ └──────────┘ └──────────┘                 │
└───────────────────────────────────────────────────────────┘
```

**ToolRegistry 处于 Agent 核心层与工具层之间的枢纽位置**，是所有工具的"注册局"和"调度中心"。

### 3.2 组件交互关系

```
                    ┌──────────────┐
                    │  TaskPlanner │
                    └──────┬───────┘
                           │ get_all_descriptions()
                           │ search_tools()
                           ↓
┌──────────────┐   ┌───────────────┐   ┌──────────────┐
│ ToolSelector │──→│  ToolRegistry │←──│ Agent 主类   │
└──────────────┘   │               │   └──────────────┘
                   │  register()   │          │
                   │  get_tool()   │          │ execute_safe()
                   │  search_tools │          ↓
                   │  unregister() │   ┌──────────────┐
                   │  list_tools() │   │  BaseTool    │
                   └───────┬───────┘   │  实例         │
                           │           └──────────────┘
                           ↓
                   ┌──────────────┐
                   │ Reflexion    │
                   │ Validator    │
                   └──────────────┘
```

### 3.3 数据流

```
用户提问
  → Agent 接收
    → TaskPlanner.plan()
      → ToolRegistry.get_all_descriptions()  // 获取工具全景
      → LLM 生成任务计划（含 tool_name）
    → ToolSelector.select()
      → ToolRegistry.search_tools(capability)  // 按能力搜索
      → ToolRegistry.get_tool(name)  // 获取工具实例
    → Agent 执行
      → ToolRegistry.execute_safe(tool_name, params)  // 安全调用
      → 返回 ToolOutput
    → ReflexionValidator.validate()
      → ToolRegistry.search_tools("verification")  // 查找验证工具
```

---

## 四、核心功能模块详细说明

### 4.1 模块文件结构

```
tools/
├── __init__.py                # 导出 BaseTool、ToolRegistry 等
├── base_tool.py               # BaseTool 抽象基类 + 数据模型
├── registry.py                # ToolRegistry 核心实现
├── vision_tool.py             # 已有，需改造适配 BaseTool
├── math_solver.py             # 新增，数学求解器
├── plot_tool.py               # 新增，图形绘制
├── practice_generator.py      # 新增，练习生成
└── knowledge_retriever.py     # 新增，知识检索
```

### 4.2 BaseTool 抽象基类（`tools/base_tool.py`）

#### 4.2.1 设计说明

所有工具必须继承 `BaseTool`，实现标准化的接口。这是插件系统的核心契约。

#### 4.2.2 完整类定义

```python
from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolCapability(str, Enum):
    SYMBOLIC_COMPUTATION = "symbolic_computation"
    NUMERICAL_COMPUTATION = "numerical_computation"
    IMAGE_RECOGNITION = "image_recognition"
    FORMULA_RECOGNITION = "formula_recognition"
    PLOTTING = "plotting"
    PRACTICE_GENERATION = "practice_generation"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    VERIFICATION = "verification"
    ERROR_BOOK_MANAGEMENT = "error_book_management"


class ToolInput(BaseModel):
    query: str = Field(..., description="用户问题或工具输入文本")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="工具执行参数"
    )
    context: Dict[str, Any] = Field(
        default_factory=dict, description="上下文信息（用户历史、会话状态等）"
    )


class ToolOutput(BaseModel):
    success: bool = Field(..., description="执行是否成功")
    result: Any = Field(None, description="执行结果数据")
    error: Optional[str] = Field(None, description="错误信息")
    tool_name: str = Field("", description="执行工具名称")
    execution_time_ms: float = Field(0.0, description="执行耗时（毫秒）")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="附加元数据"
    )


class BaseTool(ABC):
    """
    工具抽象基类 - 插件系统的核心接口

    所有工具必须继承此类并实现 execute() 方法。
    工具通过 ToolRegistry.register() 注册后即可被 Agent 系统发现和调用。

    Attributes:
        name: 工具唯一标识符（全局唯一，用于注册和检索）
        description: 工具功能的自然语言描述（供 LLM 理解）
        version: 工具版本号（语义化版本）
        capabilities: 工具能力标签列表（用于能力搜索和匹配）

    Example:
        class MathSolverTool(BaseTool):
            name = "math_solver"
            description = "数学符号计算与求解"
            capabilities = [ToolCapability.SYMBOLIC_COMPUTATION, ToolCapability.VERIFICATION]

            async def execute(self, input_data: ToolInput) -> ToolOutput:
                result = sympy.solve(input_data.query)
                return ToolOutput(success=True, result=str(result), tool_name=self.name)
    """

    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    capabilities: List[ToolCapability] = []

    @abstractmethod
    async def execute(self, input_data: ToolInput) -> ToolOutput:
        """
        执行工具逻辑

        Args:
            input_data: 标准化的工具输入

        Returns:
            ToolOutput: 标准化的工具输出

        Raises:
            ToolExecutionError: 工具执行失败时抛出
        """
        pass

    def get_info(self) -> Dict[str, Any]:
        """
        返回工具完整信息（用于注册发现、文档生成、LLM 工具描述）

        Returns:
            包含 name、description、version、capabilities、input_schema 的字典
        """
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [cap.value for cap in self.capabilities],
            "input_schema": ToolInput.model_json_schema(),
        }

    def get_description_for_llm(self) -> str:
        """
        生成供 LLM 理解的工具描述文本

        Returns:
            格式化的工具描述字符串
        """
        caps = ", ".join(cap.value for cap in self.capabilities)
        return f"工具名: {self.name}\n描述: {self.description}\n能力: {caps}\n版本: {self.version}"

    def validate_input(self, input_data: ToolInput) -> Optional[str]:
        """
        验证输入数据的合法性（子类可覆写以添加自定义校验）

        Args:
            input_data: 待验证的输入

        Returns:
            错误信息字符串，验证通过返回 None
        """
        if not input_data.query.strip():
            return "输入查询不能为空"
        return None
```

#### 4.2.3 关键设计决策

| 决策 | 原因 |
|------|------|
| 使用 Pydantic `BaseModel` 定义 `ToolInput`/`ToolOutput` | 与项目现有 Pydantic v2 生态一致，自带数据校验和 JSON Schema 生成 |
| `capabilities` 使用 `Enum` 而非字符串 | 类型安全，防止拼写错误，IDE 自动补全 |
| `execute()` 为 `async` 方法 | 与 FastAPI 异步生态对齐，支持 I/O 密集型工具 |
| `get_description_for_llm()` 独立方法 | LLM 需要的结构化描述与 `get_info()` 的 JSON 格式不同 |

### 4.3 ToolRegistry 核心实现（`tools/registry.py`）

#### 4.3.1 完整类定义

```python
from __future__ import annotations

import logging
import time
import traceback
import uuid
from typing import Any, Callable, Dict, List, Optional

from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability

logger = logging.getLogger(__name__)


class ToolNotFoundError(Exception):
    """工具未找到异常"""
    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"工具未注册: '{tool_name}'")


class ToolExecutionError(Exception):
    """工具执行异常"""
    def __init__(self, tool_name: str, original_error: str):
        self.tool_name = tool_name
        self.original_error = original_error
        super().__init__(f"工具 '{tool_name}' 执行失败: {original_error}")


class ToolRegistry:
    """
    工具注册中心 - 统一管理所有工具的注册、发现、获取和安全调用

    ToolRegistry 是 Agent 系统的工具基础设施，充当 Agent 核心层与工具层
    之间的统一中间件。所有工具必须通过 register() 注册后才能被系统使用。

    核心职责：
    1. 工具注册与生命周期管理
    2. 工具发现（按名称、按能力搜索）
    3. 工具描述聚合（供 LLM 理解可用工具集）
    4. 安全执行（统一容错、日志、耗时统计）

    Example:
        registry = ToolRegistry()
        registry.register(MathSolverTool())
        registry.register(VisionToolAdapter())

        descriptions = registry.get_all_descriptions()
        tool = registry.get_tool("math_solver")
        result = await registry.execute_safe("math_solver", ToolInput(query="求∫x²dx"))
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._execution_history: List[Dict[str, Any]] = []
        self._max_history: int = 1000

    def register(self, tool: BaseTool) -> None:
        """
        注册工具到注册中心

        如果同名工具已存在，将发出警告并覆盖（支持热更新）。

        Args:
            tool: 实现 BaseTool 接口的工具实例

        Raises:
            ValueError: 工具 name 为空时抛出
        """
        if not tool.name:
            raise ValueError("工具的 name 属性不能为空")

        if tool.name in self._tools:
            existing_version = self._tools[tool.name].version
            logger.warning(
                f"工具 [{tool.name}] 已存在(v{existing_version})，"
                f"将被覆盖为 v{tool.version}"
            )

        self._tools[tool.name] = tool
        logger.info(f"工具已注册: [{tool.name}] v{tool.version}")

    def unregister(self, tool_name: str) -> bool:
        """
        注销工具

        Args:
            tool_name: 工具名称

        Returns:
            是否成功注销（工具不存在时返回 False）
        """
        if tool_name in self._tools:
            del self._tools[tool_name]
            logger.info(f"工具已注销: [{tool_name}]")
            return True
        logger.warning(f"注销失败，工具不存在: [{tool_name}]")
        return False

    def get_tool(self, tool_name: str) -> BaseTool:
        """
        按名称获取工具实例

        Args:
            tool_name: 工具名称

        Returns:
            BaseTool 实例

        Raises:
            ToolNotFoundError: 工具未注册时抛出
        """
        if tool_name not in self._tools:
            raise ToolNotFoundError(tool_name)
        return self._tools[tool_name]

    def has_tool(self, tool_name: str) -> bool:
        """
        检查工具是否已注册

        Args:
            tool_name: 工具名称

        Returns:
            工具是否存在
        """
        return tool_name in self._tools

    def search_tools(self, capability: str) -> List[str]:
        """
        根据能力标签搜索工具

        Args:
            capability: 能力标签值（如 "symbolic_computation"）

        Returns:
            具备该能力的工具名称列表
        """
        result = []
        for name, tool in self._tools.items():
            if any(cap.value == capability for cap in tool.capabilities):
                result.append(name)
        return result

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        列举所有已注册工具的完整信息

        Returns:
            工具信息字典列表
        """
        return [tool.get_info() for tool in self._tools.values()]

    def get_all_descriptions(self) -> str:
        """
        获取所有工具的描述文本（用于注入 LLM prompt）

        LLM 通过此文本了解当前可用的工具集，从而做出工具选择决策。

        Returns:
            格式化的工具描述文本
        """
        if not self._tools:
            return "当前无可用工具。"

        descriptions = []
        for tool in self._tools.values():
            descriptions.append(tool.get_description_for_llm())

        header = "当前可用工具列表：\n" + "=" * 40
        return header + "\n\n" + "\n\n".join(descriptions)

    def get_tools_by_names(self, tool_names: List[str]) -> List[BaseTool]:
        """
        批量获取工具实例（忽略不存在的工具名）

        Args:
            tool_names: 工具名称列表

        Returns:
            工具实例列表
        """
        tools = []
        for name in tool_names:
            if name in self._tools:
                tools.append(self._tools[name])
            else:
                logger.warning(f"工具不存在，已跳过: [{name}]")
        return tools

    async def execute_safe(
        self,
        tool_name: str,
        input_data: ToolInput,
    ) -> ToolOutput:
        """
        安全执行工具（带完整监控、容错和耗时统计）

        此方法是 Agent 调用工具的唯一推荐入口，提供：
        1. 工具存在性检查
        2. 输入数据校验
        3. 执行超时保护
        4. 异常捕获与友好错误信息
        5. 执行耗时统计
        6. 执行历史记录

        Args:
            tool_name: 工具名称
            input_data: 工具输入数据

        Returns:
            ToolOutput: 标准化的工具输出（即使执行失败也返回 ToolOutput 而非抛异常）
        """
        start_time = time.time()
        execution_id = str(uuid.uuid4())[:8]

        if not self.has_tool(tool_name):
            return ToolOutput(
                success=False,
                error=f"工具未注册: '{tool_name}'",
                tool_name=tool_name,
                execution_time_ms=0,
            )

        tool = self._tools[tool_name]

        validation_error = tool.validate_input(input_data)
        if validation_error:
            elapsed = (time.time() - start_time) * 1000
            return ToolOutput(
                success=False,
                error=f"输入校验失败: {validation_error}",
                tool_name=tool_name,
                execution_time_ms=elapsed,
            )

        try:
            logger.info(
                f"[{execution_id}] 开始执行工具: [{tool_name}] "
                f"query={input_data.query[:50]}..."
            )
            result = await tool.execute(input_data)
            elapsed = (time.time() - start_time) * 1000
            result.execution_time_ms = elapsed
            result.tool_name = tool_name

            self._record_execution(
                execution_id=execution_id,
                tool_name=tool_name,
                success=result.success,
                elapsed_ms=elapsed,
                error=result.error,
            )

            logger.info(
                f"[{execution_id}] 工具执行完成: [{tool_name}] "
                f"success={result.success} 耗时={elapsed:.1f}ms"
            )
            return result

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(
                f"[{execution_id}] 工具执行异常: [{tool_name}] {error_msg}\n"
                f"{traceback.format_exc()}"
            )

            self._record_execution(
                execution_id=execution_id,
                tool_name=tool_name,
                success=False,
                elapsed_ms=elapsed,
                error=error_msg,
            )

            return ToolOutput(
                success=False,
                error=error_msg,
                tool_name=tool_name,
                execution_time_ms=elapsed,
            )

    def _record_execution(
        self,
        execution_id: str,
        tool_name: str,
        success: bool,
        elapsed_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """
        记录工具执行历史

        Args:
            execution_id: 执行唯一标识
            tool_name: 工具名称
            success: 是否成功
            elapsed_ms: 执行耗时（毫秒）
            error: 错误信息
        """
        record = {
            "execution_id": execution_id,
            "tool_name": tool_name,
            "success": success,
            "elapsed_ms": elapsed_ms,
            "error": error,
            "timestamp": time.time(),
        }
        self._execution_history.append(record)

        if len(self._execution_history) > self._max_history:
            self._execution_history = self._execution_history[-self._max_history:]

    def get_execution_stats(self) -> Dict[str, Any]:
        """
        获取工具执行统计信息

        Returns:
            包含总调用次数、成功率、平均耗时等统计数据的字典
        """
        if not self._execution_history:
            return {
                "total_calls": 0,
                "success_count": 0,
                "failure_count": 0,
                "success_rate": 0.0,
                "avg_elapsed_ms": 0.0,
                "tool_stats": {},
            }

        total = len(self._execution_history)
        success_count = sum(1 for r in self._execution_history if r["success"])
        failure_count = total - success_count
        avg_elapsed = sum(r["elapsed_ms"] for r in self._execution_history) / total

        tool_stats: Dict[str, Dict[str, Any]] = {}
        for record in self._execution_history:
            name = record["tool_name"]
            if name not in tool_stats:
                tool_stats[name] = {
                    "calls": 0,
                    "successes": 0,
                    "failures": 0,
                    "total_elapsed_ms": 0.0,
                }
            stats = tool_stats[name]
            stats["calls"] += 1
            if record["success"]:
                stats["successes"] += 1
            else:
                stats["failures"] += 1
            stats["total_elapsed_ms"] += record["elapsed_ms"]

        for name, stats in tool_stats.items():
            stats["avg_elapsed_ms"] = stats["total_elapsed_ms"] / stats["calls"]
            stats["success_rate"] = stats["successes"] / stats["calls"]

        return {
            "total_calls": total,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": success_count / total if total > 0 else 0.0,
            "avg_elapsed_ms": avg_elapsed,
            "tool_stats": tool_stats,
        }

    @property
    def tool_count(self) -> int:
        """已注册工具数量"""
        return len(self._tools)

    @property
    def tool_names(self) -> List[str]:
        """所有已注册工具的名称列表"""
        return list(self._tools.keys())
```

#### 4.3.2 关键设计决策

| 决策 | 原因 |
|------|------|
| `execute_safe()` 返回 `ToolOutput` 而非抛异常 | 调用方无需 try/except，统一通过 `output.success` 判断结果 |
| 执行历史记录内置于 Registry | 无需外部 APM 即可获得基础可观测性 |
| `search_tools()` 接受字符串而非 Enum | LLM 输出的是字符串，避免调用方需要 import Enum |
| 同名工具覆盖注册而非拒绝 | 支持工具热更新和测试替换 |
| `_execution_history` 有上限 | 防止长时间运行导致内存泄漏 |

### 4.4 VisionTool 适配器（`tools/vision_tool.py` 改造）

#### 4.4.1 改造说明

现有的 `VisionTool` 类不继承 `BaseTool`，需要创建适配器包装，**不修改原始 VisionTool 代码**。

#### 4.4.2 适配器实现

在 `tools/vision_tool.py` 文件末尾追加以下代码：

```python
from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability


class VisionToolAdapter(BaseTool):
    """
    VisionTool 的 BaseTool 适配器

    将现有 VisionTool 包装为符合 BaseTool 接口的工具，
    无需修改 VisionTool 原始代码。
    """

    name = "vision_tool"
    description = (
        "多模态图片理解：截图直接发给 Qwen-VL，"
        "输出题目文字、LaTeX 公式、图形空间关系的结构化描述。"
    )
    version = "1.0.0"
    capabilities = [
        ToolCapability.IMAGE_RECOGNITION,
        ToolCapability.FORMULA_RECOGNITION,
    ]

    def __init__(self, vision_tool: VisionTool):
        self._vision_tool = vision_tool

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        image_source = input_data.parameters.get("image_source", input_data.query)
        user_prompt = input_data.parameters.get("user_prompt")

        result = self._vision_tool.recognize(
            image_source=image_source,
            user_prompt=user_prompt,
        )

        if result.get("success"):
            return ToolOutput(
                success=True,
                result=result.get("llm_description", ""),
                tool_name=self.name,
                metadata={
                    "model_used": result.get("model_used", ""),
                    "raw_response": result.get("raw_response", ""),
                },
            )
        else:
            return ToolOutput(
                success=False,
                error=result.get("error", "图片识别失败"),
                tool_name=self.name,
            )
```

### 4.5 全局 Registry 实例与初始化（`tools/__init__.py`）

```python
from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability
from tools.registry import ToolRegistry, ToolNotFoundError, ToolExecutionError

_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    """
    获取全局 ToolRegistry 单例

    首次调用时自动初始化并注册所有内置工具。

    Returns:
        ToolRegistry 全局实例
    """
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_builtin_tools(_registry)
    return _registry


def _register_builtin_tools(registry: ToolRegistry) -> None:
    """
    注册所有内置工具

    Args:
        registry: ToolRegistry 实例
    """
    from app.config.settings import settings

    api_key = settings.DASHSCOPE_API_KEY

    if api_key:
        from tools.vision_tool import VisionTool, VisionToolAdapter
        vision = VisionTool(api_key=api_key)
        registry.register(VisionToolAdapter(vision))

    logger.info(f"内置工具注册完成，共 {registry.tool_count} 个工具")


__all__ = [
    "BaseTool",
    "ToolInput",
    "ToolOutput",
    "ToolCapability",
    "ToolRegistry",
    "ToolNotFoundError",
    "ToolExecutionError",
    "get_registry",
]
```

---

## 五、API 接口规范

### 5.1 ToolRegistry 管理 API（`main.py` 中新增）

以下 API 端点用于管理和监控 ToolRegistry。

#### 5.1.1 获取工具列表

```
GET /api/tools
```

**响应**：

```json
{
  "tools": [
    {
      "name": "vision_tool",
      "description": "多模态图片理解：截图直接发给 Qwen-VL...",
      "version": "1.0.0",
      "capabilities": ["image_recognition", "formula_recognition"],
      "input_schema": { ... }
    }
  ],
  "total": 1
}
```

#### 5.1.2 获取单个工具信息

```
GET /api/tools/{tool_name}
```

**响应**：

```json
{
  "name": "vision_tool",
  "description": "多模态图片理解...",
  "version": "1.0.0",
  "capabilities": ["image_recognition", "formula_recognition"],
  "input_schema": { ... }
}
```

**错误响应**（工具不存在）：

```json
{
  "detail": "工具未注册: 'nonexistent_tool'"
}
```

#### 5.1.3 获取工具执行统计

```
GET /api/tools/stats
```

**响应**：

```json
{
  "total_calls": 42,
  "success_count": 40,
  "failure_count": 2,
  "success_rate": 0.952,
  "avg_elapsed_ms": 1234.5,
  "tool_stats": {
    "vision_tool": {
      "calls": 30,
      "successes": 29,
      "failures": 1,
      "avg_elapsed_ms": 1500.0,
      "success_rate": 0.967
    }
  }
}
```

#### 5.1.4 按能力搜索工具

```
GET /api/tools/search?capability=image_recognition
```

**响应**：

```json
{
  "capability": "image_recognition",
  "tools": ["vision_tool"]
}
```

### 5.2 内部调用接口（Python API）

以下接口供 Agent 核心层组件调用，不暴露为 HTTP 端点。

| 方法 | 签名 | 调用方 | 说明 |
|------|------|--------|------|
| 注册工具 | `registry.register(tool)` | 初始化代码 | 注册工具实例 |
| 注销工具 | `registry.unregister(name)` | 管理接口 | 动态卸载工具 |
| 获取工具 | `registry.get_tool(name)` | ToolSelector, Agent | 按名称获取 |
| 能力搜索 | `registry.search_tools(cap)` | TaskPlanner, ToolSelector | 按能力搜索 |
| 描述聚合 | `registry.get_all_descriptions()` | TaskPlanner | 注入 LLM prompt |
| 安全执行 | `await registry.execute_safe(name, input)` | Agent 主类 | 带容错的工具调用 |
| 批量获取 | `registry.get_tools_by_names(names)` | ToolSelector | 批量获取 |

---

## 六、数据模型定义

### 6.1 核心数据模型汇总

| 模型 | 文件位置 | 用途 |
|------|---------|------|
| `ToolCapability` | `tools/base_tool.py` | 工具能力枚举 |
| `ToolInput` | `tools/base_tool.py` | 工具输入标准模型 |
| `ToolOutput` | `tools/base_tool.py` | 工具输出标准模型 |
| `BaseTool` | `tools/base_tool.py` | 工具抽象基类 |
| `ToolRegistry` | `tools/registry.py` | 工具注册中心 |
| `ToolNotFoundError` | `tools/registry.py` | 工具未找到异常 |
| `ToolExecutionError` | `tools/registry.py` | 工具执行异常 |

### 6.2 ToolInput 字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | `str` | 是 | — | 用户问题或工具输入文本 |
| `parameters` | `Dict[str, Any]` | 否 | `{}` | 工具执行参数（如图像数据、计算参数） |
| `context` | `Dict[str, Any]` | 否 | `{}` | 上下文信息（用户历史、会话状态） |

### 6.3 ToolOutput 字段说明

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `success` | `bool` | 是 | — | 执行是否成功 |
| `result` | `Any` | 否 | `None` | 执行结果数据 |
| `error` | `Optional[str]` | 否 | `None` | 错误信息 |
| `tool_name` | `str` | 否 | `""` | 执行工具名称 |
| `execution_time_ms` | `float` | 否 | `0.0` | 执行耗时（毫秒） |
| `metadata` | `Dict[str, Any]` | 否 | `{}` | 附加元数据 |

### 6.4 ToolCapability 枚举值

| 枚举值 | 字符串值 | 适用工具 |
|--------|---------|---------|
| `SYMBOLIC_COMPUTATION` | `symbolic_computation` | MathSolver |
| `NUMERICAL_COMPUTATION` | `numerical_computation` | MathSolver |
| `IMAGE_RECOGNITION` | `image_recognition` | VisionTool |
| `FORMULA_RECOGNITION` | `formula_recognition` | VisionTool |
| `PLOTTING` | `plotting` | PlotTool |
| `PRACTICE_GENERATION` | `practice_generation` | PracticeGenerator |
| `KNOWLEDGE_RETRIEVAL` | `knowledge_retrieval` | KnowledgeRetriever |
| `VERIFICATION` | `verification` | MathSolver (验证模式) |
| `ERROR_BOOK_MANAGEMENT` | `error_book_management` | ErrorBookTool |

### 6.5 执行历史记录结构

```json
{
  "execution_id": "a1b2c3d4",
  "tool_name": "vision_tool",
  "success": true,
  "elapsed_ms": 1523.4,
  "error": null,
  "timestamp": 1746268800.0
}
```

---

## 七、实现步骤与时间节点

### 7.1 实现步骤（按顺序执行）

#### Step 1：创建 BaseTool 抽象基类

- **文件**：`tools/base_tool.py`（新建）
- **内容**：`ToolCapability` 枚举、`ToolInput` 模型、`ToolOutput` 模型、`BaseTool` 抽象类
- **验收**：文件创建成功，所有类可正常 import

#### Step 2：创建 ToolRegistry 核心实现

- **文件**：`tools/registry.py`（新建）
- **内容**：`ToolRegistry` 类、`ToolNotFoundError`、`ToolExecutionError`
- **验收**：所有方法可正常调用，单元测试通过

#### Step 3：改造 VisionTool 适配器

- **文件**：`tools/vision_tool.py`（修改，追加适配器类）
- **内容**：在文件末尾追加 `VisionToolAdapter` 类
- **验收**：适配器可正常包装现有 VisionTool，`execute()` 返回标准 `ToolOutput`

#### Step 4：创建 tools 包初始化文件

- **文件**：`tools/__init__.py`（新建）
- **内容**：全局 Registry 单例、内置工具自动注册、公共 API 导出
- **验收**：`from tools import get_registry` 可正常工作

#### Step 5：集成到 main.py

- **文件**：`main.py`（修改）
- **内容**：
  1. 替换 `SimpleAgent` 的工具初始化方式，使用 `get_registry()`
  2. 新增 `/api/tools`、`/api/tools/stats`、`/api/tools/search` 端点
- **验收**：服务器启动正常，API 端点可访问

#### Step 6：改造 SimpleAgent 使用 ToolRegistry

- **文件**：`agent_core/agent.py`（修改）
- **内容**：
  1. 构造函数接受 `ToolRegistry` 实例
  2. 图片处理逻辑通过 `registry.execute_safe()` 调用
  3. 保留向后兼容（`vision_tool` 参数仍可用但标记为 deprecated）
- **验收**：Agent 功能不受影响，内部走 Registry 调用

#### Step 7：编写单元测试

- **文件**：`tests/test_tool_registry.py`（新建）
- **内容**：覆盖所有公共方法的测试用例
- **验收**：测试覆盖率 > 90%

### 7.2 时间节点

| 步骤 | 预计耗时 | 交付物 |
|------|---------|--------|
| Step 1 | 0.5 天 | `tools/base_tool.py` |
| Step 2 | 1 天 | `tools/registry.py` |
| Step 3 | 0.5 天 | `tools/vision_tool.py` 修改 |
| Step 4 | 0.5 天 | `tools/__init__.py` |
| Step 5 | 0.5 天 | `main.py` 修改 |
| Step 6 | 1 天 | `agent_core/agent.py` 修改 |
| Step 7 | 1 天 | `tests/test_tool_registry.py` |
| **合计** | **5 天** | 完整的 ToolRegistry 模块 |

---

## 八、测试策略与验收标准

### 8.1 单元测试（`tests/test_tool_registry.py`）

#### 8.1.1 BaseTool 测试

| 测试用例 | 测试内容 | 预期结果 |
|---------|---------|---------|
| `test_base_tool_get_info` | 调用 `get_info()` | 返回包含 name、description、version、capabilities 的字典 |
| `test_base_tool_get_description_for_llm` | 调用 `get_description_for_llm()` | 返回格式化的文本描述 |
| `test_base_tool_validate_input_empty` | 传入空 query | 返回错误信息字符串 |
| `test_base_tool_validate_input_valid` | 传入有效 query | 返回 None |
| `test_base_tool_cannot_instantiate` | 尝试直接实例化 BaseTool | 抛出 TypeError |

#### 8.1.2 ToolRegistry 注册/注销测试

| 测试用例 | 测试内容 | 预期结果 |
|---------|---------|---------|
| `test_register_tool` | 注册一个工具 | `tool_count` 增加 1，`has_tool()` 返回 True |
| `test_register_tool_empty_name` | 注册 name 为空的工具 | 抛出 ValueError |
| `test_register_duplicate_overwrites` | 注册同名工具 | 覆盖旧工具，发出 warning |
| `test_unregister_tool` | 注销已注册工具 | `tool_count` 减少 1，返回 True |
| `test_unregister_nonexistent` | 注销不存在的工具 | 返回 False |

#### 8.1.3 ToolRegistry 查询测试

| 测试用例 | 测试内容 | 预期结果 |
|---------|---------|---------|
| `test_get_tool` | 按名称获取工具 | 返回正确的 BaseTool 实例 |
| `test_get_tool_not_found` | 获取不存在的工具 | 抛出 ToolNotFoundError |
| `test_has_tool` | 检查工具是否存在 | 已注册返回 True，未注册返回 False |
| `test_search_tools_by_capability` | 按能力搜索 | 返回具备该能力的工具名称列表 |
| `test_search_tools_no_match` | 搜索无匹配能力 | 返回空列表 |
| `test_list_tools` | 列举所有工具 | 返回所有工具的 info 字典列表 |
| `test_get_all_descriptions` | 获取描述文本 | 返回格式化的文本，包含所有工具信息 |
| `test_get_all_descriptions_empty` | Registry 为空时 | 返回"当前无可用工具。" |
| `test_get_tools_by_names` | 批量获取 | 返回存在的工具列表，忽略不存在的 |
| `test_tool_names_property` | 获取工具名称列表 | 返回所有已注册工具名称 |

#### 8.1.4 ToolRegistry 执行测试

| 测试用例 | 测试内容 | 预期结果 |
|---------|---------|---------|
| `test_execute_safe_success` | 成功执行工具 | `ToolOutput.success=True`，包含结果 |
| `test_execute_safe_tool_not_found` | 调用不存在的工具 | `ToolOutput.success=False`，error 包含工具名 |
| `test_execute_safe_input_validation_fail` | 输入校验失败 | `ToolOutput.success=False`，error 包含校验信息 |
| `test_execute_safe_tool_exception` | 工具内部抛异常 | `ToolOutput.success=False`，error 包含异常信息 |
| `test_execute_safe_execution_time` | 检查耗时统计 | `execution_time_ms > 0` |

#### 8.1.5 执行历史与统计测试

| 测试用例 | 测试内容 | 预期结果 |
|---------|---------|---------|
| `test_execution_stats_empty` | 无执行记录 | total_calls=0 |
| `test_execution_stats_after_calls` | 执行若干次后 | 统计数据正确 |
| `test_execution_history_max_size` | 超过 1000 条记录 | 保留最新 1000 条 |

#### 8.1.6 VisionToolAdapter 测试

| 测试用例 | 测试内容 | 预期结果 |
|---------|---------|---------|
| `test_adapter_inherits_basetool` | 检查继承关系 | isinstance(adapter, BaseTool) 为 True |
| `test_adapter_capabilities` | 检查能力标签 | 包含 IMAGE_RECOGNITION 和 FORMULA_RECOGNITION |
| `test_adapter_execute_success` | 模拟成功识别 | ToolOutput.success=True |
| `test_adapter_execute_failure` | 模拟识别失败 | ToolOutput.success=False |

### 8.2 集成测试

| 测试场景 | 测试内容 | 预期结果 |
|---------|---------|---------|
| 全局 Registry 初始化 | 调用 `get_registry()` | 自动注册 VisionToolAdapter |
| API 端点访问 | `GET /api/tools` | 返回工具列表 JSON |
| Agent 集成调用 | 通过 Agent 发送图片 | 走 Registry 调用链，功能正常 |
| 向后兼容 | 使用旧方式初始化 SimpleAgent | 功能不受影响 |

### 8.3 验收标准

| 指标 | 要求 |
|------|------|
| 单元测试覆盖率 | > 90% |
| 所有测试用例通过 | 100% |
| API 端点响应正常 | 所有端点返回正确状态码和数据格式 |
| 现有功能无回归 | 原有的对话和图片识别功能不受影响 |
| 日志输出完整 | 工具注册、调用、异常均有日志记录 |
| 执行统计准确 | `get_execution_stats()` 数据与实际调用一致 |

---

## 九、部署流程

### 9.1 开发环境部署

```bash
# 1. 确保在项目根目录
cd c:\Users\HUAWEI\Desktop\math AI assistant

# 2. 安装依赖（无需新增依赖）
pip install -r requirements.txt

# 3. 创建新文件
#    - tools/base_tool.py
#    - tools/registry.py
#    - tools/__init__.py
#    - tests/test_tool_registry.py

# 4. 修改现有文件
#    - tools/vision_tool.py（追加 VisionToolAdapter）
#    - main.py（集成 Registry + 新增 API 端点）
#    - agent_core/agent.py（使用 Registry 调用工具）

# 5. 运行测试
python -m pytest tests/test_tool_registry.py -v

# 6. 启动开发服务器
python main.py
```

### 9.2 验证部署

```bash
# 验证工具列表 API
curl http://localhost:8000/api/tools

# 验证工具统计 API
curl http://localhost:8000/api/tools/stats

# 验证能力搜索 API
curl "http://localhost:8000/api/tools/search?capability=image_recognition"

# 验证对话功能（确保无回归）
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "求∫x²dx", "session_id": "test"}'
```

### 9.3 Docker 部署

无需修改现有 `Dockerfile` 和 `docker-compose.yml`，ToolRegistry 是纯 Python 模块，无额外系统依赖。

---

## 十、注意事项

### 10.1 向后兼容性

- **SimpleAgent 构造函数**：保留 `tools: Dict` 和 `vision_tool` 参数，内部优先使用 Registry，旧参数作为 fallback
- **VisionTool 原始类**：不修改 `VisionTool` 类本身，通过适配器包装
- **现有 API 端点**：`/api/chat` 和 `/api/recognize` 行为不变

### 10.2 线程安全

- 当前 `ToolRegistry` 使用普通字典，在 FastAPI 的异步环境中，同一请求内是单线程的
- 如果未来需要多线程并发写入（如动态注册/注销），需改用 `threading.Lock` 或 `asyncio.Lock`
- `_execution_history` 的追加操作在 CPython 中受 GIL 保护，当前可接受

### 10.3 性能考量

- `search_tools()` 是 O(n) 遍历，当前工具数量 < 20，无需优化
- `get_all_descriptions()` 每次调用都重新拼接字符串，如果频繁调用可考虑缓存
- `_execution_history` 有 1000 条上限，不会导致内存泄漏

### 10.4 错误处理原则

- `execute_safe()` 永远返回 `ToolOutput`，不抛异常给调用方
- `get_tool()` 在工具不存在时抛 `ToolNotFoundError`，因为这是调用方的逻辑错误
- `register()` 在 name 为空时抛 `ValueError`，因为这是配置错误

### 10.5 日志规范

- 工具注册：`INFO` 级别，格式 `工具已注册: [{tool_name}] v{version}`
- 工具注销：`INFO` 级别，格式 `工具已注销: [{tool_name}]`
- 工具执行开始：`INFO` 级别，包含 execution_id
- 工具执行完成：`INFO` 级别，包含 success 和耗时
- 工具执行异常：`ERROR` 级别，包含完整堆栈
- 同名覆盖：`WARNING` 级别

### 10.6 扩展指引

后续添加新工具时，只需：

1. 在 `tools/` 下创建新文件，实现 `BaseTool` 子类
2. 在 `tools/__init__.py` 的 `_register_builtin_tools()` 中添加注册代码
3. 无需修改 `ToolRegistry`、`SimpleAgent` 或 `main.py` 的核心逻辑

示例：

```python
# tools/math_solver.py
from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability


class MathSolverTool(BaseTool):
    name = "math_solver"
    description = "数学符号计算与求解，支持微积分、方程、矩阵等"
    version = "1.0.0"
    capabilities = [
        ToolCapability.SYMBOLIC_COMPUTATION,
        ToolCapability.VERIFICATION,
    ]

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        import sympy
        try:
            x = sympy.Symbol("x")
            result = sympy.integrate(sympy.sympify(input_data.query), x)
            return ToolOutput(success=True, result=str(result), tool_name=self.name)
        except Exception as e:
            return ToolOutput(success=False, error=str(e), tool_name=self.name)
```

### 10.7 与 LangChain 工具的互操作

ToolRegistry 的 `BaseTool` 与 LangChain 的 `Tool`/`StructuredTool` 是不同的接口。如果需要将 Registry 中的工具暴露给 LangChain AgentExecutor，需要编写转换层：

```python
from langchain_core.tools import StructuredTool


def to_langchain_tool(base_tool: BaseTool) -> StructuredTool:
    """将 BaseTool 转换为 LangChain StructuredTool"""
    async def _arun(query: str, **kwargs) -> str:
        input_data = ToolInput(query=query, parameters=kwargs)
        output = await base_tool.execute(input_data)
        return str(output.result) if output.success else f"错误: {output.error}"

    return StructuredTool.from_function(
        coroutine=_arun,
        name=base_tool.name,
        description=base_tool.description,
    )
```

此转换层在后续集成 LangChain AgentExecutor 时实现，当前阶段不需要。
