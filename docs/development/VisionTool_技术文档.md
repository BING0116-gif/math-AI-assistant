# VisionTool 技术文档

## 1. 概述

VisionTool 是数学 AI 助手的视觉-语言（Vision-Language）多模态识别组件，负责将用户上传的图片（截图、照片等）发送给通义千问 VL 模型进行端到端理解，提取题目文字、LaTeX 公式、图形空间关系等结构化信息。

## 2. 架构设计

### 2.1 组件关系图

```
┌─────────────────────────────────────────────────────────────────┐
│                         Agent Layer                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    MathAgent                              │   │
│  │  - ReAct Strategy (推理链)                               │   │
│  │  - Tool Registry (工具注册中心)                           │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Tool Layer                                  │
│  ┌────────────────┐    ┌─────────────────────────────────────┐ │
│  │ ToolRegistry   │───▶│ VisionToolAdapter (BaseTool)        │ │
│  │                │    │   - 适配器模式 (Adapter Pattern)    │ │
│  │ - 注册管理      │    │   - async/await 接口               │ │
│  │ - 执行监控      │    └─────────────────────────────────────┘ │
│  │ - 错误处理      │                    │                       │
│  └────────────────┘                    ▼                       │
│                               ┌─────────────────────────────────┐│
│                               │      VisionTool                 ││
│                               │   - HTTP API 调用                ││
│                               │   - 图片处理                    ││
│                               │   - 响应解析                    ││
│                               └─────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      External Services                            │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              DashScope VL API                              │   │
│  │  - qwen-vl-plus (Primary)                                 │   │
│  │  - qwen-vl-max (Fallback)                                │   │
│  │  - qwen2-vl-72b-instruct (Latest)                        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 设计模式

| 模式 | 应用位置 | 作用 |
|------|----------|------|
| **适配器模式 (Adapter)** | `VisionToolAdapter` | 将 VisionTool 适配到 BaseTool 接口 |
| **单例模式 (Singleton)** | `get_registry()` | 全局唯一的 ToolRegistry 实例 |
| **策略模式 (Strategy)** | `AgentStrategy` | 支持多种执行策略（ReAct 等） |

## 3. API 参考

### 3.1 VisionTool 类

#### 构造函数

```python
def __init__(
    self,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: float = 60.0,
)
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| model | str | "qwen-vl-plus" | VL 模型名称 |
| api_key | str | None | DashScope API Key |
| timeout | float | 60.0 | 请求超时时间（秒） |

#### 核心方法

##### `recognize()`

同步识别图片，返回结构化结果。

```python
def recognize(
    self,
    image_source: Union[str, Tuple[str, str]],
    user_prompt: Optional[str] = None,
    model: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> Dict[str, Any]
```

**参数：**
- `image_source`: 图片路径或 (mime_type, base64_data) 元组
- `user_prompt`: 可选的自定义用户提示词
- `model`: 可选，指定 VL 模型
- `system_prompt`: 可选，覆盖默认系统提示词

**返回：**
```python
{
    "success": bool,           # 是否成功
    "llm_description": str,    # 发给解题 Agent 的完整描述
    "raw_response": str,       # 模型原始输出
    "error": Optional[str],    # 错误信息（失败时）
    "model_used": str,         # 实际使用的模型名
}
```

##### `recognize_from_base64()`

从 base64 数据直接识别（适合 Streamlit 粘贴图片）。

```python
def recognize_from_base64(
    self,
    mime: str,
    b64_data: str,
    user_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]
```

##### `recognize_stream()`

异步流式识别，逐 token 返回结果。

```python
async def recognize_stream(
    self,
    image_source: Union[str, Tuple[str, str]],
    user_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]
```

### 3.2 VisionToolAdapter 类

BaseTool 适配器，实现异步工具接口。

```python
class VisionToolAdapter(BaseTool):
    name = "vision_tool"
    version = "2.0.0"
    capabilities = [
        ToolCapability.IMAGE_RECOGNITION,
        ToolCapability.FORMULA_RECOGNITION,
    ]

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        """执行图片识别。"""
        ...
```

## 4. 故障排查报告

### 4.1 原始问题

VisionTool 在实际调用时返回错误：
```
'generator' object has no attribute 'json'
```

### 4.2 根本原因

原 `VisionTool._post()` 方法设计存在缺陷：

```python
# 原始代码（错误）
def _post(self, ...):
    with httpx.Client(...) as client:
        # ...
        yield response.content  # 返回生成器！
```

当 `stream=False` 时，方法返回的是生成器对象，但 `recognize()` 方法期望得到 `httpx.Response` 对象并调用 `.json()` 方法。

### 4.3 修复方案

重构为独立的同步和异步 API 调用方法：

```python
# 修复后的代码
def _call_api_sync(self, messages, model, **params) -> httpx.Response:
    """同步调用 API，返回 Response 对象。"""
    with httpx.Client(timeout=self._timeout) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response  # 直接返回 Response

async def _call_api_async(self, messages, model, stream=False, **params):
    """异步调用 API。"""
    async with httpx.AsyncClient(...) as client:
        if stream:
            # 流式返回异步生成器
            return stream_generator()
        else:
            # 非流式返回 Response
            return await client.post(...)
```

## 5. 代码架构优化

### 5.1 SOLID 原则遵循

| 原则 | 实现方式 |
|------|----------|
| **S - 单一职责** | `VisionTool` 专注 API 调用，`VisionToolAdapter` 专注接口适配 |
| **O - 开闭原则** | 通过适配器模式扩展新工具，无需修改核心代码 |
| **L - 里氏替换** | `VisionToolAdapter` 可完全替换 `VisionTool` 使用 |
| **I - 接口隔离** | BaseTool 提供最小接口集 |
| **D - 依赖反转** | 依赖抽象的 `BaseTool` 而非具体实现 |

### 5.2 模块化设计

```
tools/
├── __init__.py          # 导出核心组件
├── base_tool.py         # BaseTool 抽象基类和数据模型
├── registry.py          # 工具注册中心
├── vision_tool.py       # Vision 工具核心实现
├── tool_invoker.py      # 工具调用执行器
└── tool_description.py  # 工具描述生成器
```

## 6. 测试覆盖

### 6.1 测试文件

| 文件 | 说明 | 测试数量 |
|------|------|----------|
| `tests/test_vision_tool.py` | 单元测试 | 25 |
| `tests/test_vision_tool_integration.py` | 集成测试 | 3 |
| `tests/diagnose_vision_tool.py` | 诊断脚本 | - |

### 6.2 测试结果

```
======================== 25 passed in 0.21s ========================

[PASS] Direct API Call
[PASS] Adapter Interface
[PASS] Registry Execution
```

## 7. 配置说明

### 7.1 环境变量

```bash
# .env 文件
DASHSCOPE_API_KEY=your-api-key-here
```

### 7.2 模型优先级

```python
_VL_MODELS = [
    "qwen-vl-plus",           # 优先：数学理解强
    "qwen-vl-max",            # 备选：更大规模
    "qwen2-vl-72b-instruct", # 最新一代
]
```

## 8. 使用示例

### 8.1 直接使用 VisionTool

```python
from tools.vision_tool import VisionTool

# 初始化
vision = VisionTool(api_key="your-api-key")

# 从文件识别
result = vision.recognize("screenshot.png")
if result["success"]:
    print(result["llm_description"])

# 从 base64 识别
result = vision.recognize_from_base64(
    mime="image/png",
    b64_data="iVBORw0KGgo..."
)
```

### 8.2 通过 ToolRegistry 调用

```python
from tools import get_registry
from tools.base_tool import ToolInput

registry = get_registry()
input_data = ToolInput(
    query="image.png",
    parameters={"image_source": "image.png"}
)

result = await registry.execute_safe("vision_tool", input_data)
```

## 9. 性能指标

| 指标 | 数值 |
|------|------|
| API 响应时间 | ~800ms |
| 端到端识别时间 | ~2.7s |
| 成功率 | 100% |

## 10. 未来优化方向

1. **缓存优化**：对相同图片进行去重，避免重复识别
2. **批量处理**：支持多图并行识别
3. **模型选择**：根据图片内容自动选择最优模型
4. **错误恢复**：增加自动重试和降级策略
