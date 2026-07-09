# Agent 架构统一重构方案

> 文档版本：v1.0
> 创建时间：2026-05-03
> 状态：待评审

---

## 一、问题背景

### 1.1 当前架构现状

项目当前存在两个 Agent 实现，分属不同目录：

```
agent_core/agent.py    → SimpleAgent（LangChain 多轮聊天，非真正的 Agent）
agents/                 → ReActMathAgent + AgentExecutor + ThoughtRecorder（ReAct Agent）
```

表面上这是"两种技术路线"，但经过代码审查发现两者共享了 **85% 的基础设施**：

| 共享组件 | 具体实现 |
|---------|---------|
| LLM 初始化 | `ChatOpenAI(qwen-max, streaming=True)` |
| 会话历史 | `InMemoryChatMessageHistory` + `RunnableWithMessageHistory` |
| Prompt 模板 | `ChatPromptTemplate.from_messages(...)` |
| 工具注册 | `ToolRegistry` 全局单例 |
| 图片检测 | `_is_image_input()` 方法（两份） |
| 图片处理 | `registry.execute_safe("vision_tool", ...)` |

**真正不同的只有一点**：`SimpleAgent` 用 LangChain pipe 直接调用 LLM，不经过任何推理循环；`ReActMathAgent` 用自定义的 `AgentExecutor` 实现了一个 `while` 循环，每次 LLM 输出后检查是否有工具调用，有则执行并注入结果，继续下一轮。

### 1.2 问题总结

| 问题 | 影响 |
|------|------|
| 代码重复 | 两套 `_is_image_input`、两套会话历史管理、两套流式处理 |
| 架构混乱 | `SimpleAgent` 嵌套创建 `ReActMathAgent`（`use_react=True` 时），形成包装链 |
| 资源浪费 | 非 ReAct 模式的 `SimpleAgent` 不调用任何工具，无法发挥工具系统的价值 |
| 维护困难 | 改一个 LLM 配置需要同时改两个文件 |
| 功能浪费 | `/api/chat` 端点绑定了无工具的 SimpleAgent，图片识别能力无法在聊天中自动触发 |

---

## 二、重构目标

1. **消除代码重复**：将共享逻辑统一在一处
2. **统一 Agent 入口**：一个 `MathAgent` 类，支持可配置的"执行策略"
3. **提升 Agent 能力**：`/api/chat` 和 `/api/chat/react` 合并，启用完整 ReAct 工具调用能力
4. **清晰目录结构**：`agent_core/` 作为唯一的 Agent 核心目录，`agents/` 目录消除
5. **可扩展性**：新增执行策略（如 Planner、Chain-of-Thought）不影响现有代码

---

## 三、重构方案

### 3.1 目标目录结构

```
agent_core/
├── __init__.py              # 导出 MathAgent, get_default_agent()
├── agent.py                  # 统一的 MathAgent 类（含策略模式）
├── strategies/
│   ├── __init__.py
│   ├── base.py               # AgentStrategy 基类（抽象接口）
│   ├── react.py              # ReActStrategy（从 agents/agent_executor.py 重构）
│   └── simple.py             # SimpleStrategy（纯聊天，无工具循环）
├── thought.py                # 从 agents/thought_process.py 移动
└── tool_builder.py           # 工具描述生成 + Prompt 管理（从 agents/react_agent.py 提取）

agents/                       # 删除（内容迁移到 agent_core/）
├── react_agent.py            # 删除（内容迁移到 agent_core/agent.py）
├── agent_executor.py         # 删除（内容迁移到 agent_core/strategies/react.py）
└── thought_process.py         # 删除（内容迁移到 agent_core/thought.py）

prompts/                      # 不变
├── system_prompt.py          # SystemPromptManager
├── react_prompt.py          # ReActPromptTemplate
└── tool_prompt.py           # ToolPromptGenerator
```

### 3.2 策略模式设计

引入"执行策略"作为核心抽象：

```python
# agent_core/strategies/base.py
from abc import ABC, abstractmethod

class AgentStrategy(ABC):
    """Agent 执行策略抽象基类。"""

    @abstractmethod
    async def execute(self, user_input: str, session_id: str, context: dict) -> str:
        """同步执行，返回完整答案。"""
        pass

    @abstractmethod
    async def stream(self, user_input: str, session_id: str, context: dict):
        """异步流式执行，yield 文本片段。"""
        pass

    def on_tool_called(self, tool_name: str, result: Any) -> None:
        """工具调用回调（可选实现）。"""
        pass
```

```python
# agent_core/strategies/react.py
class ReActStrategy(AgentStrategy):
    """
    ReAct 执行策略。

    核心循环：Thought → Action → Observation → ... → Final Answer
    """

    def __init__(self, llm_chain, registry, tools, max_iterations=5, thought_recorder=None):
        self._llm_chain = llm_chain
        self._registry = registry
        self._tools = {t.name: t for t in tools}
        self._invoker = ToolInvoker(registry)
        self._recorder = thought_recorder
        self._max_iterations = max_iterations

    async def execute(self, user_input: str, session_id: str, context: dict) -> str:
        # 完整的 ReAct while 循环
        ...

    async def stream(self, user_input: str, session_id: str, context: dict):
        # 先完整执行，再流式输出思维链 + 答案
        ...
```

```python
# agent_core/strategies/simple.py
class SimpleStrategy(AgentStrategy):
    """
    简单聊天策略。

    纯 LLM 调用，无工具循环。适用于需要即时响应的场景。
    """

    def __init__(self, llm_chain):
        self._llm_chain = llm_chain

    async def execute(self, user_input: str, session_id: str, context: dict) -> str:
        chat_history = context.get("chat_history", [])
        result = await self._llm_chain.ainvoke({"input": user_input, "chat_history": chat_history})
        return result

    async def stream(self, user_input: str, session_id: str, context: dict):
        chat_history = context.get("chat_history", [])
        async for chunk in self._llm_chain.astream({"input": user_input, "chat_history": chat_history}):
            yield chunk
```

### 3.3 统一 MathAgent 类

```python
# agent_core/agent.py

class MathAgent:
    """
    统一的数学解题 Agent。

    通过注入不同的执行策略，支持多种 Agent 行为模式：
    - "react"：完整 ReAct 循环，工具自主调用，思维链记录
    - "simple"：纯聊天模式，无工具调用，即时响应

    所有模式共享同一套：
    - LLM 初始化
    - 会话历史管理（InMemoryChatMessageHistory）
    - 图片输入处理（VisionTool）
    - 流式输出基础设施
    """

    SUPPORTED_MODES = {"react", "simple"}

    def __init__(
        self,
        api_key: str,
        registry: Optional[ToolRegistry] = None,
        mode: str = "react",
        model: str = "qwen-max",
        temperature: float = 0,
        max_iterations: int = 5,
        stream: bool = True,
    ):
        assert api_key, "API 密钥必须提供"
        assert mode in self.SUPPORTED_MODES, f"不支持的 mode: {mode}，可选: {self.SUPPORTED_MODES}"

        self._api_key = api_key
        self._registry = registry or get_registry()
        self._mode = mode
        self._max_iterations = max_iterations
        self._stream_enabled = stream
        self._default_session_id = "default"
        self._session_histories: Dict[str, InMemoryChatMessageHistory] = {}
        self._vision_tool = None

        # 统一 LLM 实例
        self._llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            streaming=stream,
        )

        # 统一会话历史访问器
        self._initialize_histories()

        # 构建执行策略
        self._strategy = self._create_strategy(mode)

        # 注册 VisionTool 引用（用于图片处理）
        if self._registry.has_tool("vision_tool"):
            self._vision_tool = self._registry.get_tool("vision_tool")

        print(f"MathAgent 初始化完成（mode={mode}）")

    def _create_strategy(self, mode: str) -> AgentStrategy:
        if mode == "react":
            return self._create_react_strategy()
        elif mode == "simple":
            return self._create_simple_strategy()

    def _create_react_strategy(self) -> AgentStrategy:
        from agent_core.strategies.react import ReActStrategy
        from agent_core.thought import ThoughtRecorder

        tools = list(self._registry._tools.values())
        thought_recorder = ThoughtRecorder()

        # 构建 ReAct Prompt
        prompt_manager = SystemPromptManager()
        tool_descs = ToolDescriptionGenerator().generate_for_registry(tools)
        prompt_manager.update_tools(tool_descs)
        full_prompt = prompt_manager.get_prompt()

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=full_prompt),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad", optional=True),
        ])

        llm_chain = prompt | self._llm | StrOutputParser()

        return ReActStrategy(
            llm_chain=llm_chain,
            registry=self._registry,
            tools=tools,
            max_iterations=self._max_iterations,
            thought_recorder=thought_recorder,
        )

    def _create_simple_strategy(self) -> AgentStrategy:
        from agent_core.strategies.simple import SimpleStrategy

        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}"),
        ])

        llm_chain = prompt | self._llm | StrOutputParser()

        return SimpleStrategy(llm_chain=llm_chain)

    def _initialize_histories(self) -> None:
        self._get_session_history(self._default_session_id)

    def _get_session_history(self, session_id: str) -> BaseChatMessageHistory:
        if session_id not in self._session_histories:
            self._session_histories[session_id] = InMemoryChatMessageHistory()
        return self._session_histories[session_id]

    # ── 公共 API ────────────────────────────────────────────────────────

    async def process(self, user_input: str, session_id: Optional[str] = None) -> str:
        """异步处理用户输入（完整结果返回）。"""
        sid = session_id or self._default_session_id
        context = self._build_context(sid)

        if self._is_image_input(user_input):
            return await self._process_image(user_input, sid, context)

        return await self._strategy.execute(user_input, sid, context)

    async def stream(self, user_input: str, session_id: Optional[str] = None):
        """异步流式处理用户输入，yield 文本片段。"""
        sid = session_id or self._default_session_id
        context = self._build_context(sid)

        if self._is_image_input(user_input):
            yield "【检测到图片输入，调用图片识别...】\n\n"
            result = await self._process_image(user_input, sid, context)
            yield result
            return

        async for chunk in self._strategy.stream(user_input, sid, context):
            yield chunk

    def clear_history(self, session_id: Optional[str] = None) -> None:
        """清空指定会话的对话记忆。"""
        sid = session_id or self._default_session_id
        hist = self._session_histories.get(sid)
        if hist is not None:
            hist.clear()

    def get_thought_recorder(self) -> ThoughtRecorder:
        """获取思维记录器（仅 ReAct 模式可用）。"""
        if isinstance(self._strategy, ReActStrategy):
            return self._strategy._recorder
        raise RuntimeError("思维记录器仅在 react 模式下可用")

    def set_mode(self, mode: str) -> None:
        """运行时切换执行模式。"""
        assert mode in self.SUPPORTED_MODES, f"不支持的 mode: {mode}"
        if mode != self._mode:
            self._mode = mode
            self._strategy = self._create_strategy(mode)
            print(f"Agent 模式已切换为: {mode}")

    # ── 私有辅助方法 ─────────────────────────────────────────────────────

    def _build_context(self, session_id: str) -> dict:
        """构建传递给策略的上下文。"""
        history = self._session_histories.get(session_id)
        return {
            "chat_history": list(history) if history else [],
            "registry": self._registry,
        }

    def _is_image_input(self, user_input: str) -> bool:
        """检查用户输入是否是图片路径。"""
        return any(user_input.lower().strip().endswith(ext)
                   for ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp'])

    async def _process_image(self, image_path: str, session_id: str, context: dict) -> str:
        """处理图片输入。"""
        if not self._registry.has_tool("vision_tool"):
            return "VisionTool 未注册，无法处理图片"

        input_data = ToolInput(query=image_path, parameters={"image_source": image_path})
        result = await self._registry.execute_safe("vision_tool", input_data)

        if result.success:
            recognized_text = result.result or ""
            display_msg = f"【图片识别结果】\n{recognized_text}\n\n"
            answer = await self._strategy.execute(recognized_text, session_id, context)
            return f"{display_msg}{answer}"
        else:
            return f"图片识别失败：{result.error}"
```

---

## 四、实施步骤

### 阶段一：创建新目录结构（低风险）

**步骤 1.1**：创建 `agent_core/strategies/` 目录和 `agent_core/thought.py` 文件

```bash
mkdir agent_core/strategies
touch agent_core/strategies/__init__.py
```

**步骤 1.2**：在 `agent_core/strategies/__init__.py` 中导出策略类

```python
from agent_core.strategies.base import AgentStrategy
from agent_core.strategies.react import ReActStrategy
from agent_core.strategies.simple import SimpleStrategy

__all__ = ["AgentStrategy", "ReActStrategy", "SimpleStrategy"]
```

**步骤 1.3**：在 `agent_core/__init__.py` 中导出公共接口

```python
from agent_core.agent import MathAgent

__all__ = ["MathAgent"]
```

> 验证：运行 `python -c "from agent_core import MathAgent"` 确认无报错。

---

### 阶段二：实现策略基类和 SimpleStrategy（低风险）

**步骤 2.1**：创建 `agent_core/strategies/base.py`——策略抽象基类

**步骤 2.2**：创建 `agent_core/strategies/simple.py`——简单聊天策略，从 `SimpleAgent._initialize_langchain()` 中提取纯聊天链的构建逻辑。

> 验证：创建临时测试脚本，确认 `SimpleStrategy` 能独立处理非工具调用请求。

---

### 阶段三：实现 ReActStrategy（中等风险）

**步骤 3.1**：将 `agents/agent_executor.py` 的核心循环逻辑提取到 `agent_core/strategies/react.py`

**步骤 3.2**：提取 `agents/thought_process.py` 到 `agent_core/thought.py`（仅文件移动，无逻辑修改）

**步骤 3.3**：提取 `agents/react_agent.py` 中的工具描述生成和 Prompt 管理逻辑到 `agent_core/tool_builder.py`

> 验证：创建对比测试脚本，对比 `ReActStrategy` 和原 `ReActMathAgent` 对相同输入的输出是否一致。

---

### 阶段四：实现统一的 MathAgent（高风险）

**步骤 4.1**：创建新的 `agent_core/agent.py`，实现策略模式架构（参考 3.3 节设计）

**步骤 4.2**：更新 `main.py` 中的 Agent 初始化：

```python
# 旧代码
from agent_core.agent import SimpleAgent
agent = SimpleAgent(registry=registry, api_key=api_key)
react_agent = create_react_agent(api_key=api_key, registry=registry)

# 新代码
from agent_core import MathAgent
agent = MathAgent(api_key=api_key, registry=registry, mode="react")
# 不再需要单独的 react_agent，mode="simple" 时等价于原 SimpleAgent
```

**步骤 4.3**：合并 `/api/chat` 和 `/api/chat/react` 为单一端点：

```python
# 新路由设计
@app.post("/api/chat")
async def chat(request: ChatRequest, http_request: Request):
    """统一聊天接口，支持通过参数指定执行模式。"""
    mode = request.extra.get("mode", "react")  # 默认 ReAct
    validated_message = validate_input(request.message, "message", max_length=settings.INPUT_MAX_LENGTH)
    validated_session = validate_input(request.session_id, "session_id", max_length=128)

    # 运行时模式切换（如果请求模式与当前不同）
    if mode != agent._mode:
        agent.set_mode(mode)

    return StreamingResponse(
        stream_chat_response(validated_message, validated_session),
        media_type="text/event-stream",
    )
```

---

### 阶段五：清理旧文件（收尾）

**步骤 5.1**：确认新架构完全正常工作后，删除以下文件：

```bash
# 删除 agents/ 目录
Remove-Item agents/ -Recurse -Force

# 删除旧的 agent_core/agent.py（如果存在冲突）
# 或根据需要重命名备份
```

**步骤 5.2**：更新所有 import 路径：

```python
# 旧
from agents.react_agent import create_react_agent, ReActMathAgent
from agents.agent_executor import AgentExecutor
from agents.thought_process import ThoughtRecorder

# 新
from agent_core import MathAgent
from agent_core.thought import ThoughtRecorder
```

---

## 五、测试计划

| 测试阶段 | 测试内容 | 验证标准 |
|---------|---------|---------|
| 阶段二验证 | `SimpleStrategy` 独立处理纯文本对话 | 回答内容正常，流式输出正常 |
| 阶段三验证 | `ReActStrategy` 处理数学问题 | 工具被正确调用，答案正确 |
| 阶段三验证 | 对比测试：原 `ReActMathAgent` vs `ReActStrategy` | 相同输入，输出一致 |
| 阶段四验证 | `/api/chat` 端点（ReAct 模式） | 工具调用正常，思维链正常输出 |
| 阶段四验证 | `/api/chat` 端点（simple 模式） | 即时响应，无工具调用 |
| 阶段四验证 | 图片上传 + 聊天 | 图片识别 → 文本注入 → 正常回答 |
| 阶段五验证 | 会话历史管理 | 切换 session_id 后上下文正确 |
| 阶段五验证 | 思维链 API | `/api/agent/thought/{session_id}` 返回正确 |

---

## 六、风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| 合并后 `/api/chat` 行为变化（ReAct 有思考过程） | 中 | 提供 `mode` 参数，用户可选择 `simple` 模式保持原有体验 |
| 新架构引入回归 bug | 中 | 阶段一/二/三逐阶段验证后再推进 |
| `SimpleStrategy` 和 `SimpleAgent` 行为不完全一致 | 低 | 提取逻辑时严格遵循原代码 |
| 删除 `agents/` 后有遗漏的 import | 低 | 用 Grep 全局搜索 `from agents` 确认无遗漏 |
| 流式输出格式变化影响前端 | 低 | 确认前端 SSE 解析逻辑兼容 |

---

## 七、预期收益

| 收益 | 说明 |
|------|------|
| 代码量减少 | 消除约 300+ 行重复代码 |
| 维护成本降低 | LLM 配置、Session 管理、图片处理逻辑在一处维护 |
| Agent 能力提升 | `/api/chat` 默认启用工具调用和思维链 |
| 架构清晰 | 执行策略按需注入，新增模式不影响核心代码 |
| 目录结构简化 | `agents/` 目录消除，`agent_core/` 成为唯一的 Agent 核心 |

---

## 八、备选方案

### 方案 B：最小化合并（不删除 agents/）

如果对删除 `agents/` 目录有顾虑，可以采用更保守的方案：

1. **保留 `agents/` 目录**，仅将 `ReActMathAgent` 迁移到 `agent_core/`
2. `SimpleAgent` 重构为使用 `ReActMathAgent` 的 `mode="simple"` 参数
3. `AgentExecutor` 和 `ThoughtRecorder` 保留在 `agents/` 中
4. 目录结构：

```
agent_core/
└── agent.py              # MathAgent（统一入口），依赖 agents/ 中的组件

agents/                   # 保留，但作为 agent_core 的内部实现细节
├── agent_executor.py     # ReActStrategy 的实现
└── thought_process.py   # 思维记录器
```

此方案风险更低，但架构清晰度略差。

---

## 九、决策点（请确认）

在开始实施前，请确认以下决策：

1. **是否删除 `agents/` 目录**？还是采用备选方案 B（保留但重构）？
2. **`/api/chat` 默认模式**：`react` 还是 `simple`？
3. **是否保留 `/api/chat/react` 端点**作为向后兼容？
4. **`simple` 模式是否仍保留**？（如果目标是"让数学助手真正实现 Agent 功能"，可能不需要 simple 模式）
