# 数学 AI 助手 — Code Wiki

> 版本:1.6.0  
> 最后更新:2026-07-10  
> 适用读者:项目维护者、新加入开发者、代码审查人员

本文档是数学 AI 助手项目的结构化代码百科,涵盖项目整体架构、模块职责、关键类与函数、依赖关系与运行方式。文档基于源码静态分析生成,不包含任何敏感配置内容。

---

## 目录

- [一、项目概览](#一项目概览)
- [二、整体架构](#二整体架构)
- [三、目录结构](#三目录结构)
- [四、后端核心模块](#四后端核心模块)
  - [4.1 应用入口 main.py](#41-应用入口-mainpy)
  - [4.2 应用骨架 app/](#42-应用骨架-app)
  - [4.3 Agent 核心层 agent_core/](#43-agent-核心层-agent_core)
  - [4.4 工具层 tools/](#44-工具层-tools)
  - [4.5 Prompt 工程层 prompts/](#45-prompt-工程层-prompts)
  - [4.6 服务层 app/services/](#46-服务层-appservices)
  - [4.7 API 路由层 app/api/](#47-api-路由层-appapi)
  - [4.8 数据层 app/data/](#48-数据层-appdata)
  - [4.9 中间件层 app/middleware/](#49-中间件层-appmiddleware)
  - [4.10 安全层 app/security/](#410-安全层-appsecurity)
  - [4.11 根目录独立脚本](#411-根目录独立脚本)
- [五、前端架构 frontend/](#五前端架构-frontend)
- [六、数据与配置文件](#六数据与配置文件)
- [七、依赖关系](#七依赖关系)
- [八、运行方式](#八运行方式)
- [九、测试与 CI/CD](#九测试与-cicd)
- [十、设计模式速查表](#十设计模式速查表)

---

## 一、项目概览

### 1.1 项目定位

数学 AI 助手是一个面向高等数学(及部分高中数学)学习的智能辅导系统,核心能力包括:

- **智能解题**:基于通义千问(Qwen-Max)的分步解题,支持基础解法、进阶解法、步骤依据、易错点提醒
- **图片识别**:基于 Qwen-VL 多模态模型识别截图中的数学公式与题目
- **错题本**:错题收集、分类标签、掌握度跟踪、统计分析
- **个性化推荐**:基于 RAG + 用户画像 + 知识图谱的自适应题目推荐
- **学习记忆**:短期 + 长期双层记忆系统,跨会话上下文召回
- **技能画像**:基于 Elo-style 时间加权评分的技能熟练度建模

### 1.2 技术栈一览

| 层级 | 技术 | 用途 |
|------|------|------|
| 后端框架 | FastAPI >=0.104.0 | 高性能异步 API |
| ASGI 服务器 | Uvicorn >=0.24.0 | 服务运行 |
| LLM | 通义千问 Qwen-Max / Qwen-VL | 文本解题 + 图片识别 |
| Agent 框架 | LangChain >=0.1.0 | ReAct 工具调用 |
| 向量数据库 | Qdrant >=1.7.0 | 语义检索(已从 ChromaDB 迁移) |
| Embedding | sentence-transformers (all-MiniLM-L6-v2) | 向量生成 |
| 关系数据库 | SQLAlchemy 2.0 + SQLite/PostgreSQL | 业务数据持久化 |
| 缓存 | Redis >=5.0.0 | 二级缓存 L2 |
| 前端框架 | Vue 3.4 + Vite 5 | SPA 单页应用 |
| 状态管理 | Pinia 2 | 前端状态 |
| UI 库 | Element Plus 2 | 组件库 |
| 公式渲染 | KaTeX + @mdit/plugin-katex | LaTeX 渲染 |
| Markdown | markdown-it 14 | 富文本渲染 |
| 容器化 | Docker + Docker Compose | 部署编排 |

### 1.3 设计哲学

项目贯穿以下核心设计原则:

1. **多级降级**:几乎所有依赖外部资源(LLM/Qdrant/Redis/Embedding)的模块都设计了降级路径,保证主流程不中断
2. **单例 + 工厂模式**:核心服务通过模块级 `get_xxx()` 工厂懒加载,全项目共享实例
3. **事件驱动 + 异步优先**:行为追踪、错题本同步、事件缓冲采用事件驱动模型,`asyncio.gather` 并行化关键路径
4. **配置对象 + 数据驱动**:难度权重、技能 DAG、意图关键词等以常量/YAML 外部化,支持动态调优
5. **前后端契约清晰**:LLM 输出必须用 `$...$` / `$$...$$` 包裹数学内容,前端通过统一管线渲染

---

## 二、整体架构

### 2.1 系统分层架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (Vue 3 SPA)                       │
│  HomeView / ChatView / ErrorBookView                         │
│  Pinia Stores (chat / errorBook / theme)                    │
│  渲染管线: markdown-it + KaTeX + DOMPurify                    │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP / SSE (通过 Nginx 反代)
┌────────────────────────▼────────────────────────────────────┐
│                     FastAPI 应用 (main.py)                    │
│  ┌─────────────┐ ┌──────────────┐ ┌────────────────────┐    │
│  │ 中间件栈     │ │  路由层       │ │  生命周期管理       │    │
│  │ CORS        │ │ app/api/*    │ │ lifespan.py        │    │
│  │ 安全头       │ │              │ │ (DB/Cache/Vector)  │    │
│  │ 限流         │ │              │ │                    │    │
│  │ JWT 认证     │ │              │ │                    │    │
│  └─────────────┘ └──────┬───────┘ └────────────────────┘    │
└─────────────────────────┼───────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│  Agent 核心    │ │  服务层        │ │  数据层        │
│ agent_core/   │ │ app/services/ │ │ app/data/     │
│               │ │               │ │               │
│ MathAgent     │ │ LLMService    │ │ SQLAlchemy ORM│
│ TaskPlanner   │ │ VectorStore   │ │ Repositories  │
│ Classifier    │ │ RAGRecommender│ │ Migrations    │
│ Strategies    │ │ MemorySystem  │ │               │
│ Tools         │ │ DifficultyEst │ │               │
└───────┬───────┘ └───────┬───────┘ └───────┬───────┘
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ▼
        ┌─────────────────────────────────────┐
        │           外部依赖                    │
        │  ┌─────────┐ ┌───────┐ ┌─────────┐  │
        │  │ Qwen API│ │Qdrant │ │PostgreSQL│  │
        │  │(DashScope)│ │      │ │ /SQLite │  │
        │  └─────────┘ └───────┘ └─────────┘  │
        │  ┌─────────┐ ┌───────────────────┐  │
        │  │ Redis   │ │ SentenceTransformer│  │
        │  └─────────┘ └───────────────────┘  │
        └─────────────────────────────────────┘
```

### 2.2 请求处理流程(以聊天为例)

```
用户输入 → Nginx反代 → FastAPI 中间件栈(CORS→安全头→限流→JWT认证)
    → POST /api/chat → chat_api.py
    → stream_handler.stream_agent_response()
    → MathAgent.stream()
        → _build_context() [注入用户技能画像]
        → _select_strategy() [意图分类→复杂度分类→动态参数]
        → LangChainReActStrategy.stream()
            → create_agent (LangChain)
            → astream_events (v2)
            → 工具调用 (VisionTool/RecommendTool/...)
            → ThoughtRecordingCallbackHandler [思维链记录]
        → 跟进推荐去重检测
    → SSE 流式响应 → 前端 parseSSEStream → 打字机渲染
```

### 2.3 智能推荐流程(RAG)

```
POST /api/recommend/questions
    → RAGRecommender.recommend()
        → Step1: 获取用户画像 + 技能数据
        → Step2: 确定目标分类 + 自适应难度
        → Step3: 三路并行检索 (asyncio.gather)
            ├─ SQL 精确检索 (QuestionRepository)
            ├─ 向量语义检索 (QdrantVectorStore)
            └─ 知识图谱分析 (MathSkillDAG)
        → Step4: 融合排序 (SQL优先 + 向量补充 + 去重)
        → Step5: AI 分析 (LLMService, 15s超时降级)
        → Step6: 封装结果 (含 processing_time_ms)
```

---

## 三、目录结构

```
math AI assistant/
├── main.py                         # FastAPI 应用入口
├── error_book.py                   # 错题本管理(JSON 持久化)
├── calibrate_questions.py          # LLM 题目批量校准 CLI
├── docker-compose.yml              # 容器编排
├── Dockerfile                      # 后端镜像
├── requirements.txt                # Python 依赖
├── README.md                       # 项目说明
│
├── app/                            # 应用主包
│   ├── api/                        # API 路由层
│   │   ├── auth.py                 # 认证(注册/登录/刷新/登出)
│   │   ├── chat_api.py             # 聊天/识别/多模态
│   │   ├── agent_api.py            # Agent 状态/工具/健康检查
│   │   ├── data_api.py             # 数据导出/清除(GDPR)
│   │   ├── error_api.py            # 错题本 CRUD
│   │   ├── memory_api.py           # 记忆系统 + 错题本技能同步
│   │   ├── profile_api.py          # 用户画像/学习报告/技能画像
│   │   └── recommendation_api.py   # RAG 推荐/导入/向量搜索
│   ├── config/                     # 配置管理
│   │   ├── settings.py             # 全局配置(pydantic-settings)
│   │   └── middleware_config.py    # 中间件专用配置
│   ├── data/                       # 数据访问层
│   │   ├── models.py               # ORM 模型(8 张表)
│   │   ├── database.py             # 异步引擎/会话工厂
│   │   ├── repositories.py         # 仓储模式(BaseRepository)
│   │   ├── migrations.py           # JSON→SQL 数据迁移
│   │   ├── math_skill_graph.yml    # 数学技能 DAG(30+ 知识点)
│   │   └── migrations/             # SQL 迁移脚本
│   ├── middleware/                 # 中间件层
│   │   ├── auth.py                 # JWT 工具 + 内存用户存储
│   │   ├── auth_middleware.py      # ASGI 认证中间件
│   │   ├── path_matcher.py         # 路径白名单匹配器
│   │   ├── rate_limit.py           # 滑动窗口限流
│   │   ├── security.py             # 输入校验/威胁检测
│   │   └── security_headers.py     # HTTP 安全响应头
│   ├── security/                   # 安全层
│   │   ├── access_control.py       # RBAC 权限 + 所有权校验
│   │   ├── audit.py                # 审计日志
│   │   └── encryption.py           # 字段级加密 + 密码哈希
│   ├── services/                   # 业务服务层(18 个模块)
│   │   ├── llm_service.py          # LLM 服务(单例+缓存+TIR)
│   │   ├── vector_store.py         # Qdrant 向量存储
│   │   ├── rag_recommender.py      # RAG 推荐引擎
│   │   ├── stream_handler.py       # SSE 流式响应
│   │   ├── difficulty_estimator.py # 难度评估器(四因子加权)
│   │   ├── skill_aggregator.py     # 技能聚合(Elo-style)
│   │   ├── behavior_tracker.py     # 行为追踪(LLM+规则降级)
│   │   ├── cache.py                # 两级缓存(L1内存+L2Redis)
│   │   ├── memory.py               # 双层记忆系统
│   │   ├── profile_analyzer.py     # 用户画像分析
│   │   ├── question_importer.py    # 题目批量导入
│   │   ├── pdf_question_parser.py  # PDF 题目解析
│   │   ├── vision_pdf_parser.py    # VL 视觉 PDF 解析
│   │   ├── math_skill_dag.py       # 数学技能 DAG
│   │   ├── follow_up_recommender.py# 后续推荐(双难度梯度)
│   │   ├── error_book_sync.py      # 错题本↔技能同步
│   │   ├── event_buffer.py         # 事件缓冲器
│   │   └── __init__.py             # 包导出
│   ├── dependencies.py             # 依赖注入中心(Protocol)
│   ├── lifespan.py                 # 应用生命周期
│   └── middleware_setup.py         # 中间件集中注册
│
├── agent_core/                     # Agent 核心层
│   ├── agent.py                    # MathAgent 统一入口
│   ├── langchain_adapter.py        # BaseTool→StructuredTool 适配器
│   ├── callbacks.py                # LangChain 回调处理器
│   ├── memory_persistence.py       # 记忆持久化门面(Facade)
│   ├── metrics.py                  # Prometheus 指标(优雅降级)
│   ├── task_planner.py             # DAG 任务规划器
│   ├── thought.py                  # 思维链记录器
│   ├── classifier/                 # 复杂度分类器
│   │   ├── complexity_levels.py    # 五级复杂度标准
│   │   ├── llm_classifier.py       # LLM 分类器(三级降级)
│   │   └── output_parser.py        # 鲁棒输出解析
│   └── strategies/                 # 执行策略
│       ├── base.py                 # AgentStrategy 抽象基类
│       └── langchain_react.py      # LangChain ReAct 实现
│
├── tools/                          # 工具层
│   ├── __init__.py                 # 注册中心单例 + 内置工具注册
│   ├── base_tool.py                # BaseTool 抽象基类
│   ├── hybrid_registry.py          # HybridToolRegistry 双模式注册
│   ├── tool_description.py         # 工具描述生成器
│   ├── tool_call_parser.py         # 工具调用解析
│   ├── tool_invoker.py             # 工具调用执行
│   ├── vision_tool.py              # 图片识别工具
│   ├── recommend_tool.py           # 推荐题目工具
│   ├── skill_profile_tool.py       # 技能画像工具
│   ├── search_tool.py              # 检索工具
│   ├── explain_tool.py             # 讲解工具
│   └── error_book_tool.py          # 错题本工具
│
├── prompts/                        # Prompt 工程层
│   ├── system_prompt.py            # 四层 System Prompt 管理器
│   ├── react_prompt.py             # ReAct 指令模板
│   ├── planning_prompt.py          # 任务规划 Prompt
│   ├── classifier_prompt.py        # 复杂度分类 Prompt
│   ├── behavior_classify_prompt.py # 行为分类 Prompt
│   └── dynamic_params.py           # 动态参数映射 + LLM 工厂
│
├── frontend/                       # 前端 Vue 3 应用
│   ├── src/
│   │   ├── main.js                 # 应用入口
│   │   ├── App.vue                 # 根组件
│   │   ├── router/index.js         # 路由配置
│   │   ├── api/                    # API 调用封装
│   │   ├── stores/                 # Pinia 状态管理
│   │   ├── utils/                  # 工具函数(markdown.js 核心渲染)
│   │   ├── views/                  # 视图组件
│   │   ├── components/             # UI 组件
│   │   └── styles/                 # 全局样式
│   ├── Dockerfile                  # 前端多阶段构建
│   ├── nginx.conf                  # 生产 Nginx 配置
│   ├── vite.config.js              # Vite 构建配置
│   └── package.json                # npm 依赖
│
├── data/                           # 数据文件
│   ├── seed_questions.csv          # 种子题目
│   └── template_import_questions.csv # 导入模板
│
├── data_processing/                # 数据处理工具
│   ├── formatters.py
│   └── validators.py
│
├── docs/                           # 项目文档
│   ├── architecture/               # 架构设计
│   ├── development/                # 开发文档
│   ├── api/                        # API 文档
│   ├── prd/                        # PRD 文档
│   └── migration/                  # 迁移文档
│
├── qdrant_storage/                 # Qdrant 本地存储
├── .github/workflows/ci.yml        # CI/CD 配置
└── .devcontainer/devcontainer.json # Dev Container 配置
```

---

## 四、后端核心模块

### 4.1 应用入口 main.py

**文件路径**:[main.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/main.py)

**职责**:FastAPI 应用创建、中间件配置、路由注册、核心组件初始化、静态文件服务与 SPA 回退。

**关键流程**:
1. 创建 `FastAPI` 实例(docs/redoc 仅在 DEBUG 模式开放)
2. 调用 `setup_middleware(app)` 注册中间件栈
3. 注册 8 个路由模块(auth/memory/profile/data/recommendation/chat/error/agent)
4. 初始化核心组件:`get_registry()`、`init_dynamic_llm_factory()`、`MathAgent`、`ErrorBookManager`、`init_default_admin()`
5. 注册异常处理器(`SecurityValidationError` + 全局异常)
6. 挂载静态文件(`/static`、`/assets`)与 SPA 回退路由

**关键对象**:
- `app: FastAPI` — 全局应用实例
- `agent: MathAgent` — 全局 Agent 实例(供 `app.dependencies.get_agent()` 引用)
- `error_book_manager: ErrorBookManager` — 全局错题本管理器
- `registry` — 全局工具注册中心

**启动信息输出**:启动时打印数据库 URL、Redis 状态、CORS 配置、安全特性、速率限制等关键运行时信息。

---

### 4.2 应用骨架 app/

#### 4.2.1 app/dependencies.py — 依赖注入中心

**职责**:用 `Protocol` 定义服务接口,降低耦合,便于测试 Mock。

**关键 Protocol**:
- `LLMServiceProtocol`:`chat()` / `chat_stream()` / `model` 属性
- `VectorStoreProtocol`:`initialize()` / `search()` / `hybrid_search()` / `add_question()` / `is_initialized` 属性

**依赖工厂函数**:
- `get_llm_service() -> LLMService` — 单例
- `async get_vector_store() -> VectorStoreManager` — 单例
- `get_agent()` / `get_registry()` / `get_error_book_manager()` — 从 main 模块取全局实例

**测试辅助**:`override_llm_service(mock)`、`override_vector_store(mock)`、`reset_dependencies()`

#### 4.2.2 app/lifespan.py — 应用生命周期

**职责**:FastAPI 生命周期管理(替代旧 `@app.on_event`)。

**启动阶段**:
1. `await init_db()` — 初始化数据库
2. 若 `RAG_ENABLED`:
   - 初始化向量库(`RAG_ENABLE_VECTOR_SEARCH`)
   - 初始化 LLM 服务(`RAG_ENABLE_AI_EXPLANATION`)
3. `get_cache_manager().initialize()` — 初始化缓存(若 REDIS_URL 非空)

**关闭阶段**:`cache_mgr.close()` + `close_db()`

#### 4.2.3 app/middleware_setup.py — 中间件集中注册

**职责**:`setup_middleware(app: FastAPI)` 按栈式顺序注册中间件(后注册先执行):
1. `CORSMiddleware` — 跨域(允许 Authorization/Content-Type/Accept/X-Session-Id 头)
2. `SecurityHeadersMiddleware` — 安全响应头
3. `RateLimitMiddleware` — 限流(默认 30 次/分钟)
4. `AuthenticationMiddleware` — JWT 认证

---

### 4.3 Agent 核心层 agent_core/

#### 4.3.1 agent_core/agent.py — MathAgent 统一入口

**职责**:系统统一入口,管理 LLM 实例、会话历史、工具注册、图片处理、动态参数、复杂度分类器、用户画像注入和跟进推荐。

**配置对象(dataclass)**:
- `LLMConfig(model, temperature, base_url)`
- `StrategyConfig(max_iterations, stream)`
- `DynamicParamsConfig(enabled)`
- `AgentClassifierConfig(enabled, model, cache_max_size, classification_timeout, enable_cache, enable_fallback)`
- `MathAgentConfig(api_key, llm, strategy, dynamic_params, classifier, registry)` — 完整配置,`__post_init__` 校验 api_key 非空

**核心类 `MathAgent`**:
- `__init__(config: MathAgentConfig)` — 初始化 LLM、动态参数工厂、会话历史(`InMemoryChatMessageHistory`)、分类器、意图分类器、构建 `LangChainReActStrategy`、注册 VisionTool、初始化 `MemoryPersistenceFacade` 和 `LearningBehaviorTracker`
- `@classmethod create(api_key, registry=None, model="qwen-max", ...)` — 向后兼容工厂方法
- `async process(user_input, session_id, user_id) -> str` — 同步处理入口
- `async stream(user_input, session_id, user_id) -> AsyncGenerator[str, None]` — 流式处理入口,含**跟进推荐去重机制**
- `async stream_multimodal(image_path, user_message, ...)` — 图片+文字多模态流式
- `async _build_context(session_id, user_input, user_id) -> Dict` — 构建上下文,**注入用户技能画像**
- `@staticmethod _format_skill_profile_for_llm(profile) -> str` — 画像格式化(<300 tokens,含正确率/薄弱点/已掌握/推荐难度/易错模式/认知风格)
- `_build_system_prompt(tools, style, skill_profile) -> str` — 组装四层 System Prompt
- `_classify_intent(user_input) -> ClassificationResult` — 轻量规则意图分类(<1ms)
- `async _select_strategy(user_input, session_id) -> AgentStrategy` — 策略选择(意图→动态参数→复杂度分类)

**模块级工厂**:`create_math_agent(api_key, ...) -> MathAgent`

#### 4.3.2 agent_core/strategies/ — 执行策略层

**base.py** — 抽象基类:
- `class AgentStrategy(ABC)`:`async execute()` / `async stream()`

**langchain_react.py** — LangChain ReAct 实现:
- `class MaxIterationsMiddleware(AgentMiddleware)` — 限制最大迭代次数
- `class LangChainReActStrategy(AgentStrategy)`:
  - `__init__(llm, registry, system_prompt, max_iterations=5, timeout_seconds=120.0)`
  - `_ensure_agent_initialized()` — **延迟初始化**(首次调用才创建 Agent)
  - `async stream(user_input, session_id, context)` — 核心流式执行,用 `astream_events(version="v2")` 过滤 `on_chat_model_stream` 事件
  - 含可观测性埋点(输出 hash、工具调用集、RAG 内容检测)
  - **替代了原有自定义 ReAct,工具调用准确率从 85% 提升至 99%+**

#### 4.3.3 agent_core/classifier/ — 复杂度分类器

**complexity_levels.py**:
- `ComplexityLevel(IntEnum)`:TRIVIAL(1)/BASIC(2)/MODERATE(3)/ADVANCED(4)/COMPLEX(5)
- `ComplexityCategory` — 各级元数据(中文标签、定义、示例、推荐策略)
- `level_to_strategy(score)` — 1-3 → "react",4-5 → "planned"

**llm_classifier.py**:
- `LLMComplexityClassifier` — LLM 驱动分类器(qwen-turbo)
  - `async classify(problem) -> ClassificationResult` — 核心分类(查缓存→调LLM→解析→校验→存缓存)
  - **三级降级**:LLM → 缓存 → 规则兜底(`_rule_based_fallback`:文本长度+关键词权重+数学符号密度)
  - **MD5 缓存 + LRU 淘汰**
  - **结果合理性校验**(`_validate_result`):极简问题被判高分则修正

**output_parser.py**:
- `RobustOutputParser` — 鲁棒解析 LLM 非标准输出(分层降级匹配:精确→短语→中文数字→范围→任意数字)

#### 4.3.4 agent_core/task_planner.py — DAG 任务规划器

**职责**:将复杂数学问题分解为结构化子任务序列,支持 DAG 依赖、并行分组、缓存、安全、重规划。

**核心类**:
- `Task` — 单个任务单元(含 id/name/tool_name/parameters/dependencies/priority/retry_count/max_retries)
- `TaskDAG` — 轻量有向无环图(`topological_sort` Kahn 算法、`get_parallel_groups` 分层并行、`get_critical_path` 关键路径、`has_cycle` DFS 检测)
- `ExecutionPlan` — 可执行计划(`get_ready_tasks` / `mark_completed` / `is_complete`)
- `PlanCache` — SHA256 签名 TTL 缓存(LRU 淘汰)
- `RateLimiter` — 滑动窗口频率限制
- `DataPrivacyManager` — 数据隐私(正则脱敏卡号/电话/邮箱)
- `SecureErrorHandler` — 安全错误处理(生成 error_id + 用户友好消息)
- `PerformanceMonitor` — 性能监控
- `TaskPlanner` — 核心规划器
  - `should_plan(problem) -> bool` — 判断是否需要规划
  - `async plan(problem, context) -> ExecutionPlan` — 核心规划(清洗→校验→查缓存→分析→生成→构建DAG→验证→缓存)
  - `async replan(failed_task, error, original_plan) -> ExecutionPlan` — 重规划
  - **降级**:LLM 失败回退单任务推理(`_create_fallback_plan`)

#### 4.3.5 agent_core/memory_persistence.py — 记忆持久化门面

**职责**:Facade 统一入口,委托 LongTermMemory、MemoryRetrievalEngine、SkillAggregator、DifficultyEstimator、EnhancedEventBuffer。

**核心类 `MemoryPersistenceFacade`**:
- `async record_event(user_id, event_data) -> bool` — 记录学习事件,自动触发技能重计算
- `async retrieve_context(user_id, query, session_id, limit, min_score) -> List` — 检索相关记忆
- `async get_profile(user_id) -> UserProfile` — 聚合画像(统计+技能+错误模式+认知风格+难度)
- `async estimate_difficulty(user_id, category, sub_category, context) -> int`
- `async trigger_skill_recalculation(user_id, skill_codes) -> int`

**自动重计算机制**:
- `RECALC_TRIGGER`:事件数阈值 3、最小间隔 30s、批量阈值 50
- `_maybe_trigger_recalc` — 非阻塞 `asyncio.ensure_future`

**意图感知持久化**:`INTENT_PERSISTENCE_MAP`(problem_solving/concept_inquiry/error_analysis/exam_practice/casual_chat 不同 TTL 与记录粒度)

#### 4.3.6 其他 agent_core 模块

| 文件 | 职责 | 关键类/函数 |
|------|------|------------|
| `langchain_adapter.py` | BaseTool→StructuredTool 适配器 | `LangChainToolConverter`、`convert_tools_to_langchain()` |
| `callbacks.py` | LangChain 回调处理器(观察者模式) | `ThoughtRecordingCallbackHandler`、`LCThoughtProcess` |
| `metrics.py` | Prometheus 指标(优雅降级) | `METRICS_AVAILABLE`、`_NoopMetric`、`get_metrics_response()` |
| `thought.py` | 思维链记录器 | `ThoughtRecorder`、`ThoughtProcess`、`ThoughtStep` |

---

### 4.4 工具层 tools/

#### 4.4.1 tools/__init__.py — 注册中心入口

**关键函数**:
- `get_registry() -> HybridToolRegistry` — 全局单例(惰性初始化 + 注册内置工具)
- `init_registry(registry=None)` — 初始化或替换全局单例
- `_register_builtin_tools(registry, api_key=None)` — 注册 VisionTool/RecommendTool/SkillProfileTool/ExplainTool/SearchTool/ErrorBookTool

**类型别名**:`ToolRegistry = HybridToolRegistry`

#### 4.4.2 tools/base_tool.py — 工具抽象基类

**关键类**:
- `ToolCapability(str, Enum)` — 能力枚举(SYMBOLIC_COMPUTATION/IMAGE_RECOGNITION/PLOTTING/PRACTICE_GENERATION/KNOWLEDGE_RETRIEVAL/VERIFICATION/ERROR_BOOK_MANAGEMENT 等)
- `ToolInput(BaseModel)` — 标准输入(query/parameters/context)
- `ToolOutput(BaseModel)` — 标准输出(success/result/data/error/tool_name/execution_time_ms/metadata)
- `BaseTool(ABC)` — 工具抽象基类
  - `@abstractmethod async execute(input_data: ToolInput) -> ToolOutput`
  - `get_info()` / `get_description_for_llm()` / `validate_input()`

#### 4.4.3 tools/hybrid_registry.py — 混合工具注册中心

**职责**:双模式访问(自定义模式保留能力标签/统计;LangChain 模式提供 StructuredTool),自动同步两份存储。

**核心类 `HybridToolRegistry`**:
- `register(tool)` — 注册并自动同步双存储
- `search_tools(capability)` — 按能力搜索
- `async execute_safe(tool_name, input_data) -> ToolOutput` — **Agent 调用工具的唯一推荐入口**(存在性检查+输入校验+超时保护+异常捕获+耗时统计+历史记录,失败返回 ToolOutput 而非抛异常)
- `get_execution_stats()` / `get_hybrid_stats()` — 统计监控
- **优雅降级**:无 langchain 依赖时纯自定义模式

#### 4.4.4 内置工具

| 工具文件 | 能力 | 职责 |
|---------|------|------|
| `vision_tool.py` | IMAGE_RECOGNITION | Qwen-VL 图片识别 |
| `recommend_tool.py` | PRACTICE_GENERATION | 推荐练习题 |
| `skill_profile_tool.py` | KNOWLEDGE_RETRIEVAL | 技能画像查询 |
| `search_tool.py` | KNOWLEDGE_RETRIEVAL | 知识检索 |
| `explain_tool.py` | KNOWLEDGE_RETRIEVAL | 概念讲解 |
| `error_book_tool.py` | ERROR_BOOK_MANAGEMENT | 错题本操作 |

---

### 4.5 Prompt 工程层 prompts/

#### 4.5.1 prompts/system_prompt.py — 四层 System Prompt 管理器

**四层架构**:
- **LAYER 0 元指令层**(`LAYER0_META`):角色定义("贸大数助")、角色铁律、安全边界、工具结果铁律
- **LAYER 1 任务路由层**(`LAYER1_ROUTING`):T1-T6 意图路由表(知识点问询/快速答案/概念讲解/图片提问/完整解题/出题推荐)
- **LAYER 2 场景模板层**(`LAYER2_TEMPLATE_T1`~`T5`):各场景输出模板
- **LAYER 3 动态注入层**:工具描述、记忆上下文、ReAct 指令、技能画像、教学风格

**核心类 `SystemPromptManager`**:
- `update_tools(tool_descriptions)` — 更新工具描述(哈希变化才刷新版本)
- `update_react_instruction()` / `update_style_instruction()` / `update_skill_profile()`
- `get_prompt() -> str` — 获取完整 System Prompt
- `get_prompt_for_task_type(task_type) -> str` — 按任务类型返回精简/完整 Prompt
- **版本缓存**:SHA256 哈希变化检测,缓存上限 10

#### 4.5.2 prompts/dynamic_params.py — 动态参数映射

**关键类**:
- `TaskType(str, Enum)`:T1-T5 + PLANNED_SOLUTION + DEFAULT,属性 `max_output_length` / `needs_tools` / `needs_profile` / `max_history_turns`
- `LLMParams` — temperature/top_p/max_tokens/presence_penalty/frequency_penalty
- `TASK_PARAMS_MAP` — 任务类型→LLMParams(T1:800/0、T2:300/0、T3:2000/0.1、T4:4096/0、T5:8192/0.3、Planned:12288/0.1)
- `COMPLEXITY_TOKEN_MAP` — 复杂度1-5→max_tokens(1024/2048/4096/8192/12288)
- `get_adaptive_max_tokens(complexity_score, task_type)` — 自适应 Token
- `TaskClassifier` — 轻量规则意图分类器(纯关键词匹配,<1ms,零 Token,缓存上限 1000)
- `DynamicLLMFactory` — 动态 LLM 实例工厂(按任务类型获取/创建 LLM,缓存复用)
- `init_dynamic_llm_factory()` / `get_dynamic_llm_factory()` — 全局单例

#### 4.5.3 其他 Prompt 模块

| 文件 | 职责 |
|------|------|
| `react_prompt.py` | 精简版 ReAct 指令模板(~10 行,工具调用格式与规则) |
| `planning_prompt.py` | 任务规划三阶段 Prompt(分析/生成/重规划),防 Prompt 注入 |
| `classifier_prompt.py` | 复杂度分类 Prompt(20年教学经验教授角色,五级评分标准) |
| `behavior_classify_prompt.py` | 行为分类 Prompt(event_type 5选1、category 8选1,~150 tokens) |

---

### 4.6 服务层 app/services/

#### 4.6.1 llm_service.py — LLM 服务(单例)

**职责**:统一管理 LLM 调用(通义千问 DashScope,兼容 OpenAI SDK),支持流式、TIR 数学推理、AI 难度分析。

**核心类 `LLMService`**:
- `async generate(prompt, system_prompt, model, temperature, max_tokens, use_cache) -> LLMResponse`
- `async generate_stream(...) -> AsyncGenerator[str, None]`
- `async generate_with_math_model(prompt, system_prompt, use_tir=True) -> LLMResponse` — TIR 模式(自然语言→Python代码→最终答案)
- `async analyze_question_difficulty(question_content, category) -> Dict`

**设计模式**:
- **单例模式**:`__new__` + `_initialized`
- **内存缓存**:TTL 300s,LRU 淘汰上限 100,md5(prompt+system+model) 生成 key
- **降级**:JSON 解析失败返回默认难度 3;流式异常 yield 错误信息

**工厂**:`get_llm_service() -> LLMService`

#### 4.6.2 vector_store.py — Qdrant 向量存储

**职责**:基于 Qdrant 的题目向量存储与语义检索,支持混合搜索。

**核心类 `QdrantVectorStoreManager`**:
- `async initialize()` / `async check_availability() -> bool`
- `async add_question(question_id, content, metadata, vector) -> bool`
- `async add_questions_batch(questions, batch_size=100) -> int`
- `async semantic_search(query_vector, n_results, where) -> List[VectorSearchResult]`
- `async hybrid_search(query_vector, query_text, category_filter, difficulty_range, n_results, vector_weight=0.7)` — 向量召回 + 关键词 Jaccard 加权融合
- `async get_collection_stats() / get_all_ids()`

**状态机**:`VectorStoreStatus`(INITIALIZING/READY/ERROR/DEGRADED)

**设计模式**:
- **多级降级**:Qdrant 不可用→内存模式;Embedding 模型不可用→随机向量;HF 模型加载超时(30s)→降级
- **重试机制**:初始化失败重试 3 次,间隔 5 秒
- **可用性探测**:30 秒间隔缓存,DEGRADED 可自动恢复为 READY
- **可选量化**:ScalarQuantization(INT8)

**工厂**:`async get_vector_store() -> QdrantVectorStoreManager`

#### 4.6.3 rag_recommender.py — RAG 推荐引擎

**职责**:整合用户画像、技能、向量库、知识图谱,实现 6 步自适应题目推荐。

**数据类**:
- `RecommendationRequest`(user_id/target_category/count=5/context/exclude_ids/request_id)
- `RecommendationResult`(questions/ai_analysis/meta/request_id/generated_at/processing_time_ms)

**核心类 `RAGRecommender`**:
- `async recommend(request: RecommendationRequest) -> RecommendationResult`

**6 步工作流**:
1. 用户画像 → 2. 目标/难度确定 → 3. 三路并行检索(`asyncio.gather`:SQL+向量+知识图谱)→ 4. 融合排序 → 5. AI 分析(15s 超时降级)→ 6. 结果封装

**降级**:AI 分析超时→默认分析;整体异常→fallback 推荐(difficulty=3)

#### 4.6.4 其他服务模块

| 文件 | 职责 | 关键设计 |
|------|------|---------|
| `stream_handler.py` | SSE 流式响应封装 | 临时文件管理、容错降级、多模态分流 |
| `difficulty_estimator.py` | 难度评估 | 四因子加权(掌握度0.35+正确率0.20+趋势0.25+遗忘0.15+奖励0.05),遗忘曲线 `e^(-days/14)` |
| `skill_aggregator.py` | 技能聚合 | Elo-style 时间加权(`0.5^(days/14)`),UPSERT 幂等写入 |
| `behavior_tracker.py` | 行为追踪 | 三级降级(LLM→规则→默认),3次重试指数退避 |
| `cache.py` | 两级缓存 | L1内存(FIFO上限1000)+L2Redis,装饰器 `cache_result` |
| `memory.py` | 双层记忆 | 短期(内存LRU+TTL)+长期(数据库),加权融合(短期0.4+长期0.6),Jaccard相似度 |
| `profile_analyzer.py` | 用户画像 | 多维聚合,线性回归趋势,连续学习天数 |
| `question_importer.py` | 题目导入 | CSV/Excel/字典,必需列校验,幂等导入,双写一致性 |
| `pdf_question_parser.py` | PDF 解析 | 双引擎(fitz→pdfplumber),分层分割,答案合并 |
| `vision_pdf_parser.py` | VL 视觉解析 | PDF→图片→VL模型,JSON 容错,三层降级 |
| `math_skill_dag.py` | 技能 DAG | YAML 数据驱动,前置依赖/解锁/可学性查询 |
| `follow_up_recommender.py` | 后续推荐 | 双难度梯度(Q1=base-1,Q2=base+1),五轮渐进检索,LLM 原创生成兜底 |
| `error_book_sync.py` | 错题本↔技能同步 | 事件驱动,JSON 操作 SQLite,懒加载依赖 |
| `event_buffer.py` | 事件缓冲 | deque 有界(200),三条件触发刷新(50条/30秒/强制),去重(5分钟窗口) |

---

### 4.7 API 路由层 app/api/

#### 4.7.1 路由端点总览

| 路由模块 | 前缀 | 主要端点 |
|---------|------|---------|
| `auth.py` | `/api/auth` | POST register/login/refresh/logout |
| `chat_api.py` | (无统一前缀) | POST /api/chat、/api/chat/react、/api/recognize、/api/chat/multimodal |
| `agent_api.py` | (无统一前缀) | GET /api/agent/thought/{session_id}、/api/agent/stats、/api/tools、/api/tools/{name}、/api/tools/stats、/api/tools/search、/api/health、/api/health/detailed |
| `data_api.py` | `/api/data` | GET export、DELETE purge(GDPR) |
| `error_api.py` | (无统一前缀) | GET/POST/PUT/DELETE /api/error-book |
| `memory_api.py` | `/api/memory` | POST events、GET retrieve、GET stats、DELETE clear、POST error-book/sync、POST error-book/mastery、POST error-book/batch-sync、GET skill-impact |
| `profile_api.py` | `/api/profile` | GET /{user_id}、GET /{user_id}/report、GET /{user_id}/recommendations、PUT /{user_id}/preferences、GET /{user_id}/skills、POST track |
| `recommendation_api.py` | `/api/recommend` | POST questions、POST explain、GET skill-profile、POST ai-analyze、POST questions/import、POST vector-search、POST pdf-import、GET health |

#### 4.7.2 关键请求模型

```python
# chat_api.py
class ChatRequest(BaseModel): message: str, session_id: str
class RecognizeRequest(BaseModel): image: str, session_id: str
class MultimodalChatRequest(BaseModel): message: str, image: str, session_id: str

# recommendation_api.py
class RecommendQuestionsRequest(BaseModel): target_category, count: 1-20, context, exclude_ids
class ImportQuestionsRequest(BaseModel): questions: List[Dict]
class VectorSearchRequest(BaseModel): query, category, difficulty_min/max, n_results: 1-50

# memory_api.py
class LearningEventRequest(BaseModel): event_type ∈ {ask, answer_correct, answer_wrong, review, skip}, question_content, category, difficulty 1-5, ...
```

#### 4.7.3 认证与授权

- **认证**:JWT Bearer Token(`AuthenticationMiddleware`),白名单路径(login/register/refresh/chat/error-book/tools/agent/health 等)免认证
- **授权**:RBAC(`access_control.py`),student/teacher/admin 三级权限,`require_permission` 装饰器 + `verify_resource_ownership`
- **数据导出/清除**:`data_api.py` 实现 GDPR 风格的用户数据导出(JSON/CSV)与清除(需显式 `confirm=DELETE_MY_DATA`)

---

### 4.8 数据层 app/data/

#### 4.8.1 app/data/models.py — ORM 数据模型

**基类**:`class Base(DeclarativeBase): pass`(SQLAlchemy 2.0 风格)

**数据表(8 张)**:

| 表名 | 模型类 | 关键字段 |
|------|--------|---------|
| `users` | `User` | id(UUID)、username(唯一)、email(唯一)、password_hash、role、is_active、preferences(JSON)、last_login_at/ip、failed_login_count、locked_until |
| `learning_records` | `LearningRecord` | id、user_id FK、question_id FK、event_type、question_content、category、difficulty、is_correct、time_spent、error_reason、metadata(JSON)、created_at(复合索引+部分索引) |
| `user_skills` | `UserSkill` | id、user_id FK、skill_code、display_name、mastery_level(0-1)、status(novice/learning/proficient/mastered)、total_attempts、correct_count、recent_streak、best_streak、evolution_history(JSON)、UNIQUE(user_id, skill_code) |
| `questions` | `Question` | id(str20)、content(Text)、question_type、options(JSON)、answer(Text)、analysis、solution_steps(JSON)、category、knowledge_points、difficulty、complexity_score、estimated_time、usage_count、correct_rate、avg_time_spent |
| `chat_sessions` | `ChatSession` | id(UUID)、user_id FK、title、status、message_count、total_tokens、agent_strategy、tools_used |
| `chat_messages` | `ChatMessage` | id、session_id FK、role、content(Text)、token_count、metadata(JSON)、learning_record_id FK |
| `exam_papers` | `ExamPaper` | id、user_id FK、title、config(JSON)、question_ids(JSON)、status、score、max_score |
| `exam_submissions` | `ExamSubmission` | id、paper_id FK、question_id FK、user_answer、is_correct、score、max_score、time_spent |

#### 4.8.2 app/data/database.py — 数据库配置

**关键函数**:
- `_get_database_url()` — 优先 `ASYNC_DATABASE_URL`,自动转 `sqlite+aiosqlite:///`
- `init_db()` — 创建 async engine(PostgreSQL:pool_size=20/max_overflow=10/pool_pre_ping;SQLite:WAL模式+busy_timeout=5000)、`Base.metadata.create_all`、执行迁移SQL
- `close_db()` — dispose engine
- `get_db_session()` — async context manager(自动 commit/rollback/close)
- `check_database_health()` — `SELECT 1` + latency_ms

#### 4.8.3 app/data/repositories.py — 仓储模式

**基类**:`BaseRepository(Generic[T])` — create/get_by_id/get_all/update/delete/count/exists/bulk_create

**子仓储**:
- `UserRepository` — get_by_username/get_by_email/increment_failed_login/get_user_stats
- `LearningRecordRepository` — get_by_user(支持过滤)/get_user_category_stats/get_errors_by_user/get_recent_records
- `QuestionRepository` — get_by_category/search_questions(ilike)/update_usage_stats(增量更新)
- `ChatSessionRepository` / `ChatMessageRepository` / `ExamPaperRepository` / `ExamSubmissionRepository`

#### 4.8.4 app/data/migrations.py — 数据迁移

**职责**:从遗留 JSON 文件迁移到关系数据库。

**核心类**:
- `DataMigrator` — `run_all_migrations()` → `_migrate_error_book()`(读 JSON 写 questions 表) + `_migrate_users_from_auth_file()`(读 users.json 写 users 表)
- `verify_migration()` — 统计对比
- `run_migration_cli()` — argparse 支持 `--dry-run` / `--verify`

#### 4.8.5 app/data/math_skill_graph.yml — 知识图谱

**职责**:数学技能依赖图(YAML),定义 `skill_code → {display_name, prerequisites, category}`。

**覆盖范畴**:
- 代数:basic_operations → linear_equations → quadratic_equations → polynomials
- 函数:function_concept → elementary_functions → composite_functions
- 三角函数:trig_basic_values → trig_identities → trig_sum_formula → trig_double_angle → trig_equation
- 极限与导数:limit_concept → limit_calculation → derivative_definition → derivative_rules → derivative_application
- 积分:integ_indefinite → integ_definite / integ_by_parts / integ_trig

被 `MathSkillDAG` 加载,服务于技能画像与解锁推荐。

---

### 4.9 中间件层 app/middleware/

| 文件 | 职责 | 关键类/函数 |
|------|------|------------|
| `auth.py` | JWT 认证工具 + 内存用户存储 | `TokenPayload`、`TokenPair`、`create_token_pair`、`verify_access_token`、`init_default_admin` |
| `auth_middleware.py` | ASGI 认证中间件 | `AuthenticationMiddleware` |
| `path_matcher.py` | 路径白名单匹配器 | `PathMatcher.should_skip_auth` / `should_skip_rate_limit` |
| `rate_limit.py` | 滑动窗口限流 | `RateLimitMiddleware`(默认 30次/60秒,429 响应) |
| `security.py` | 输入校验/威胁检测 | `XSS_PATTERNS`、`SQL_INJECTION_PATTERNS`、`PATH_TRAVERSAL_PATTERNS`、`validate_input`、`is_safe_image_data` |
| `security_headers.py` | HTTP 安全响应头 | `SecurityHeadersMiddleware`(CSP/X-Content-Type-Options/X-Frame-Options 等) |

**认证白名单**(`_DEFAULT_NO_AUTH_PATHS`):login/register/refresh/chat/error-book/tools/agent/health 等,可通过 `middleware_config.NO_AUTH_PATHS` 环境变量覆盖。

---

### 4.10 安全层 app/security/

| 文件 | 职责 | 关键类/函数 |
|------|------|------------|
| `access_control.py` | RBAC 权限映射 + 所有权校验 | `Permission` 枚举、`RolePermissionMapping`(student/teacher/admin)、`require_permission` 装饰器、`verify_resource_ownership` |
| `audit.py` | 审计日志(JSON 格式,写入 logs/audit.log) | `AuditLogger`(log_access/log_modification/log_deletion/log_export/log_login)、`_sanitize`(脱敏 password/token/secret)、`get_audit_logger()` 单例 |
| `encryption.py` | 字段级加密 + 密码哈希 | `DataEncryption`(Fernet 对称加密,encrypt_field/decrypt_field/encrypt_sensitive_user_data)、`hash_password`/`verify_password`(PBKDF2HMAC-SHA256,600000次迭代) |

**注意**:项目存在两套密码哈希实现——`app/middleware/auth.py._hash_password`(hashlib.pbkdf2_hmac,`salt$hex` 格式)与 `app/security/encryption.py.DataEncryption.hash_password`(cryptography.PBKDF2HMAC,base64 `salt+key` 格式),二者不兼容。

---

### 4.11 根目录独立脚本

#### error_book.py — 错题本管理

**职责**:数学错题的收集、存储(JSON 文件持久化)和复习管理。

**核心类**:
- `ErrorItem`(dataclass)— id/question/question_type/image_path/error_reason/categories/original_answer/correct_answer/notes/added_at/mastery_level/is_mastered
- `ErrorBookManager`:
  - 持久化:`_load` / `_save`(同步) / `_async_save`(异步)
  - CRUD:`add` / `add_async` / `remove` / `update` / `get` / `get_all`
  - 查询:`filter(categories, search_text, mastered, mastery_level)`
  - 统计:`get_statistics`(总数/已掌握/分类计数/掌握度分布)

#### calibrate_questions.py — LLM 题目批量校准

**职责**:独立 CLI 脚本,对数据库中所有题目调用 LLM 进行智能分类校准。

**关键函数**:
- `parse_llm_response(content) -> dict` — 鲁棒解析 LLM JSON
- `async calibrate_one(llm, q, dry_run=False)` — 校准单题(不走缓存)
- `async run_calibration(args)` — 批量校准(支持 `--dry-run`/`--limit`/`--category`/`--from-id`/`--skip-calibrated`/`--interval`)

**特性**:断点续传(`--from-id`)、限流保护(interval sleep)、字段模糊匹配清洗

---

## 五、前端架构 frontend/

### 5.1 技术栈

- **框架**:Vue 3.4(Composition API)+ Vite 5
- **状态管理**:Pinia 2
- **路由**:Vue Router 4(history 模式)
- **UI 库**:Element Plus 2(中文语言包)
- **渲染管线**:markdown-it 14 + @mdit/plugin-katex 0.25 + KaTeX 0.16 + DOMPurify 3.4
- **HTTP**:axios 1.6(REST)+ 原生 fetch(SSE 流式)
- **样式**:Sass

### 5.2 路由配置

[frontend/src/router/index.js](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/frontend/src/router/index.js)

| path | name | 组件 | meta.title |
|------|------|------|-----------|
| `/` | Home | HomeView.vue | 数学AI助手 |
| `/chat` | Chat | ChatView.vue | 智能对话 - 数学AI助手 |
| `/chat/:chatId` | ChatDetail | ChatView.vue | 智能对话 - 数学AI助手 |
| `/error-book` | ErrorBook | ErrorBookView.vue | 错题本 - 数学AI助手 |
| `/error-book/:errorId` | ErrorDetail | ErrorBookView.vue | 错题详情 - 数学AI助手 |

全部使用懒加载 `() => import(...)`,全局前置守卫动态设置 `document.title`。

### 5.3 API 调用封装

[frontend/src/api/](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/frontend/src/api)

| 文件 | 职责 | 关键函数 |
|------|------|---------|
| `index.js` | axios 实例工厂(baseURL=/api,timeout=30s,请求拦截器注入 Bearer Token,响应拦截器统一处理 401/403/429/500) | 默认导出 `api` 实例 |
| `chat.js` | 对话接口(用原生 fetch 支持 SSE) | `sendChatMessage`、`sendRecognizeRequest`、`sendMultimodalRequest`、`parseSSEStream` |
| `errorBook.js` | 错题本 CRUD | `getErrorBook`、`addErrorBook`、`updateErrorBook`、`deleteErrorBook` |

**SSE 解析器** `parseSSEStream(response, onData, onDone, onError)`:
- 用 `response.body.getReader()` + `TextDecoder` 按 `\n\n` 分块
- 识别 `data: ` 前缀,处理 `[DONE]`、`type==='done'`、`type==='error'`、`type==='content'`
- 忽略 `AbortError`/`ERR_CANCELED`(用于"停止生成")

### 5.4 Pinia 状态管理

| Store | 持久化 key | 状态 | 关键方法 |
|-------|-----------|------|---------|
| `chatStore` | `math_ai_chats` | chats、currentChatId、isLoading、pendingImage | createNewChat、switchChat、addMessage、setErrorBookStatus、persistChats |
| `errorBookStore` | (本地缓存) | errors、loading、filter | loadErrors、addError、updateError、toggleMastery、**extractBestAnswer**(从 AI 回复智能提取最佳答案) |
| `themeStore` | `math_ai_theme` | theme(light/dark) | setTheme、toggleTheme、applyTheme |

### 5.5 渲染管线 ⭐

[frontend/src/utils/markdown.js](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/frontend/src/utils/markdown.js)

**管线**:`MarkdownIt 解析 → @mdit/plugin-katex 公式渲染 → DOMPurify 净化 → HTML 输出`

**关键配置**:
- markdown-it:`html:true`、`linkify:true`、`breaks:true`、`typographer:true`
- KaTeX 插件:`md.use(katex, { delimiters: 'dollars', throwOnError: false, strict: false })` — 自动识别 `$...$` 和 `$$...$$`,**在解析阶段直接渲染为 HTML,无需二次处理**
- DOMPurify:两套配置(`purifyOptions` 完整版允许 MathML/SVG 标签;`streamPurifyOptions` 流式轻量版)

**导出**:
- `renderMarkdown(text)` — 完整渲染,异常降级为转义纯文本
- `formatStreamText(text)` — 流式格式化

### 5.6 视图组件

| 视图 | 职责 | 核心机制 |
|------|------|---------|
| `HomeView.vue` | 首页(欢迎横幅+输入框+功能卡片) | handleSend 创建会话并跳转 /chat |
| `ChatView.vue` ⭐ | 对话主界面(最复杂) | 打字机效果(typingBuffer+rawContentBuffer 双缓冲)、节流渲染(%50 或数学符号触发)、停止生成(AbortController)、错题本弹窗(Teleport) |
| `ErrorBookView.vue` | 错题本列表 | 统计/筛选/详情模态、键盘导航(Esc/←→) |

### 5.7 关键组件

| 组件 | 职责 |
|------|------|
| `common/MathRenderer.vue` | 独立公式渲染(实际项目统一走 markdown.js 管线,此组件备用) |
| `chat/MessageItem.vue` | 单条消息渲染(AI 走 renderMarkdown,用户纯文本,图片 img,错题本操作区) |
| `chat/InputArea.vue` | 对话输入框(图片粘贴 base64 预览,Enter 发送/Shift+Enter 换行,自适应高度) |
| `layout/Sidebar.vue` | 左侧导航(品牌区+主题切换+新对话+历史列表+错题本入口,右键菜单重命名/删除) |
| `layout/TopBar.vue` | 顶部栏(汉堡菜单动画+插槽) |
| `layout/LayoutDefault.vue` | 主布局骨架(Sidebar+TopBar+内容插槽) |
| `home/ChatInput.vue` | 首页输入框(含语音按钮+QuickTools) |
| `home/WelcomeHero.vue` | 欢迎区(SVG 动画+fadeInUp,支持 prefers-reduced-motion) |
| `home/FeatureCards.vue` | 6 个功能卡片(响应式 3→2→1 列) |
| `errorBook/ErrorStats.vue` | 三宫格统计 |
| `errorBook/ErrorFilter.vue` | 筛选面板(搜索/分类/掌握度) |
| `errorBook/ErrorCard.vue` | 错题卡片(可展开,图片查看器) |
| `errorBook/ErrorDetailModal.vue` | 详情模态(上一题/下一题导航) |

### 5.8 构建与部署配置

**vite.config.js**:
- 别名 `@` → `src`
- 开发服务器 port 5173,代理 `/api` → `http://localhost:8000`
- 构建 `manualChunks`:`element-plus` 和 `katex` 单独分包

**nginx.conf**:
- 监听 80,SPA history 回退
- `/api/` 反代到 `http://web:8000`,**`proxy_buffering off`**(SSE 必需)、**`proxy_read_timeout 300s`**(长连接必需)
- 开启 gzip

---

## 六、数据与配置文件

### 6.1 种子数据

[data/seed_questions.csv](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/data/seed_questions.csv)

**表头(12 列)**:`id, content, question_type, options, answer, analysis, category, sub_categories, knowledge_points, difficulty, estimated_time, source`

- 题型:填空题、选择题
- 知识域:导数、不等式、集合、三角函数、命题逻辑等
- `options`:选择题为 JSON 数组,填空题为 `[]`
- `knowledge_points`:双引号转义的 JSON 字符串数组
- 难度 1-5,`estimated_time` 单位分钟

[data/template_import_questions.csv](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/data/template_import_questions.csv) — 导入模板,格式与 seed 一致。

### 6.2 配置项总览(app/config/settings.py)

| 配置组 | 关键配置项 | 默认值 |
|--------|-----------|--------|
| 应用 | APP_NAME / APP_VERSION / DEBUG | 数学AI助手 / 1.6.0 / False |
| 数据库 | DATABASE_URL / ASYNC_DATABASE_URL | sqlite:///./data/math_ai.db |
| Redis | REDIS_URL | redis://localhost:6379/0 |
| CORS | CORS_ORIGINS / CORS_MAX_AGE | 6 个 localhost 端口 / 600 |
| JWT | JWT_SECRET_KEY / JWT_ALGORITHM / ACCESS_TOKEN_EXPIRE / REFRESH_TOKEN_EXPIRE | (占位需覆盖) / HS256 / 1440分钟 / 30天 |
| LLM | DASHSCOPE_API_KEY / LLM_API_BASE / LLM_MODEL / LLM_MATH_MODEL / LLM_TEMPERATURE / LLM_MAX_TOKENS / LLM_STREAMING | "" / dashscope compatible-mode / qwen-max / qwen-turbo / 0.3 / 4096 / True |
| 安全 | ENCRYPTION_KEY / INPUT_MAX_LENGTH / RATE_LIMIT_PER_MINUTE / AUTO_MIGRATE | "" / 50000 / 30 / False |
| 分类器 | CLASSIFIER_ENABLED / CLASSIFIER_MODEL / CLASSIFIER_CACHE_SIZE / CLASSIFIER_TIMEOUT | True / qwen-turbo / 2000 / 5.0 |
| 向量库 | VECTOR_DB_PATH / VECTOR_EMBEDDING_MODEL | ./data/chroma_db / all-MiniLM-L6-v2 |
| RAG | RAG_ENABLED / RAG_ENABLE_AI_EXPLANATION / RAG_ENABLE_VECTOR_SEARCH / RAG_DEFAULT_RECOMMEND_COUNT / RAG_HYBRID_SEARCH_TOP_K | True / True / True / 5 / 20 |

**配置来源**:`.env` 文件(utf-8 编码),`extra="ignore"` 忽略未定义字段。

> **注意**:根据安全要求,本文档不读取也不包含 `.env` 文件内容。所有配置项均通过环境变量或 `.env` 文件注入,代码中仅保留默认值。

---

## 七、依赖关系

### 7.1 Python 依赖(requirements.txt)

| 分类 | 依赖 | 用途 |
|------|------|------|
| Web 框架 | fastapi>=0.104.0 | API 框架 |
| ASGI 服务器 | uvicorn>=0.24.0 | 服务运行 |
| AI/LLM | langchain>=0.1.0、langchain-core>=0.1.0、langchain-openai>=0.0.5、openai>=1.0.0 | Agent + LLM 调用 |
| 图像处理 | Pillow>=9.0.0 | 图片处理 |
| 数学计算 | sympy>=1.12 | 符号计算与答案验证 |
| 数据库 | sqlalchemy>=2.0.0、aiosqlite>=0.19.0、asyncpg>=0.29.0、psycopg2-binary>=2.9.0 | ORM + 异步驱动 |
| 缓存 | redis>=5.0.0 | L2 缓存 |
| 加密 | cryptography>=41.0.0 | 字段级加密 |
| HTTP | httpx>=0.25.0 | 异步 HTTP |
| 数据校验 | pydantic>=2.0.0、pydantic-settings>=2.0.0 | 模型校验 + 配置 |
| 安全 | PyJWT>=2.8.0 | JWT |
| 监控 | psutil>=5.9.0 | 系统指标 |
| 测试 | pytest>=7.4.0、pytest-asyncio>=0.23.0 | 单元测试 |
| 配置 | pyyaml>=6.0 | YAML 加载 |
| 向量库 | qdrant-client>=1.7.0 | 向量存储 |
| 数据处理 | pandas>=2.0.0、openpyxl>=3.1.0、numpy>=1.24.0 | CSV/Excel 导入 |
| Embedding | sentence-transformers>=2.2.0 | 向量生成 |

### 7.2 前端依赖(package.json)

**运行时依赖**:
- vue@^3.4.21、vue-router@^4.3.0、pinia@^2.1.7
- element-plus@^2.8.0
- markdown-it@^14.2.0、@mdit/plugin-katex@^0.25.2、katex@^0.16.9
- dompurify@^3.4.2、marked@^18.0.3
- axios@^1.6.7

**开发依赖**:
- vite@^5.1.4、@vitejs/plugin-vue@^5.0.4、sass@^1.71.1

### 7.3 模块依赖关系图

```
main.py
  ├─ app.config.settings          (配置)
  ├─ app.lifespan                 (生命周期)
  ├─ app.middleware_setup         (中间件注册)
  │    ├─ app.middleware.*        (5 个中间件)
  │    └─ app.config.middleware_config
  ├─ app.api.*                    (8 个路由模块)
  │    ├─ app.services.*          (18 个服务)
  │    ├─ app.data.repositories   (仓储)
  │    ├─ app.security.*          (安全)
  │    └─ app.dependencies        (依赖注入)
  ├─ tools                        (工具注册中心)
  │    ├─ tools.base_tool
  │    └─ tools.hybrid_registry
  ├─ agent_core                   (Agent 核心)
  │    ├─ agent_core.agent
  │    ├─ agent_core.strategies
  │    ├─ agent_core.classifier
  │    ├─ agent_core.task_planner
  │    ├─ agent_core.memory_persistence
  │    │    └─ app.services.memory / skill_aggregator / difficulty_estimator
  │    └─ agent_core.callbacks
  ├─ prompts                      (Prompt 工程)
  │    └─ prompts.dynamic_params  (DynamicLLMFactory)
  └─ error_book                   (错题本管理)

app.services.*
  ├─ llm_service                  → openai SDK → DashScope API
  ├─ vector_store                 → qdrant-client + sentence-transformers
  ├─ rag_recommender              → llm_service + vector_store + math_skill_dag + repositories
  ├─ difficulty_estimator         → skill_aggregator
  ├─ skill_aggregator             → repositories + math_skill_dag
  ├─ memory                       → repositories (LongTermMemory)
  └─ cache                        → redis

agent_core.agent
  ├─ prompts.system_prompt        (四层 Prompt)
  ├─ prompts.dynamic_params       (DynamicLLMFactory)
  ├─ agent_core.classifier        (复杂度分类)
  ├─ agent_core.strategies        (LangChain ReAct)
  │    └─ agent_core.langchain_adapter → tools.hybrid_registry
  ├─ agent_core.memory_persistence
  └─ agent_core.callbacks         (思维链记录)
```

### 7.4 循环依赖处理

项目通过以下方式避免循环导入:
1. **懒加载**:`error_book_sync.py` 的 `_get_skill_aggregator()` 延迟初始化
2. **Protocol 解耦**:`app/dependencies.py` 用 `@runtime_checkable Protocol` 定义接口
3. **全局实例引用**:`get_agent()` / `get_error_book_manager()` 从 `main` 模块取全局实例
4. **门面模式**:`MemoryPersistenceFacade` 统一访问多个服务

---

## 八、运行方式

### 8.1 本地开发运行

#### 8.1.1 环境要求

- Python 3.10+
- Node.js 18+(前端开发)
- 阿里云 DashScope API Key

#### 8.1.2 后端启动

```bash
# 1. 创建虚拟环境
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量(在项目根目录创建 .env 文件)
# DASHSCOPE_API_KEY=你的API密钥
# JWT_SECRET_KEY=你的JWT密钥
# (其他配置项参见 app/config/settings.py 的默认值)

# 4. 启动应用
python main.py
```

应用启动后:
- 访问地址:http://localhost:8000
- API 文档(Swagger):http://localhost:8000/docs(仅 DEBUG 模式)
- ReDoc:http://localhost:8000/redoc(仅 DEBUG 模式)

#### 8.1.3 前端开发服务器

```bash
cd frontend
npm install        # 或 npm ci
npm run dev        # 启动 Vite 开发服务器,默认 http://localhost:5173
```

Vite 开发服务器配置了代理:`/api` → `http://localhost:8000`,因此前端开发时需同时运行后端。

#### 8.1.4 前端构建

```bash
cd frontend
npm run build      # 产物输出到 frontend/dist/
npm run preview    # 预览构建产物
```

构建后,后端 `main.py` 会挂载 `frontend/dist/assets` 到 `/assets`,并提供 SPA 回退路由。

### 8.2 生产部署

#### 8.2.1 服务器部署(无 Docker)

```bash
# 1. 构建前端
cd frontend && npm ci && npm run build && cd ..

# 2. 安装后端依赖
pip install -r requirements.txt

# 3. 配置环境变量(通过 .env 或系统环境变量)

# 4. 使用 uvicorn 启动(支持多进程)
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

#### 8.2.2 Docker Compose 部署(推荐)

[docker-compose.yml](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/docker-compose.yml) 定义 4 个服务:

| 服务 | 镜像 | 端口 | 说明 |
|------|------|------|------|
| `web` | 本地构建(根 Dockerfile) | ${PORT:-8000}:8000 | FastAPI 后端 |
| `frontend` | 本地构建(frontend/Dockerfile) | ${FRONTEND_PORT:-3000}:80 | Nginx 前端 |
| `db` | postgres:15-alpine | ${DB_PORT:-5432}:5432 | PostgreSQL 数据库 |
| `redis` | redis:7-alpine | ${REDIS_PORT:-6379}:6379 | Redis 缓存 |

**启动命令**:

```bash
# 创建 .env 文件配置环境变量(参见 docker-compose.yml 中的 environment 段)
docker-compose up -d

# 查看日志
docker-compose logs -f web

# 停止
docker-compose down
```

**资源限制**:
- web:2 CPU / 2G 内存
- db:2 CPU / 2G 内存
- redis:1 CPU / 512M 内存

**网络**:所有服务接入 `mathai-network` bridge 网络。

**数据卷**:`postgres_data`(数据库)、`redis_data`(缓存)持久化。

#### 8.2.3 Docker 镜像说明

**后端 Dockerfile**(根目录):
- 基础镜像:`python:3.10-slim`
- 安装 `git`、`gcc`、`libpq-dev`
- 使用清华镜像源加速 pip
- 启动命令:`python -m uvicorn main:app --host 0.0.0.0 --port 8000`

**前端 Dockerfile**(多阶段构建):
- 阶段 1:`node:18-alpine` → `npm ci`(npmmirror 镜像)→ `npm run build`
- 阶段 2:`nginx:alpine` → 拷贝 dist + nginx.conf

### 8.3 关键运行时配置

#### 8.3.1 数据库切换

- **开发环境**:默认 SQLite(`sqlite+aiosqlite:///./data/math_ai.db`),WAL 模式
- **生产环境**:通过 `DATABASE_URL` / `ASYNC_DATABASE_URL` 环境变量切换到 PostgreSQL

#### 8.3.2 降级策略

系统支持以下自动降级:
- **向量库不可用**:RAG 推荐切换为纯 SQL 查询
- **LLM 不可用**:复杂度分类降级为规则匹配;AI 分析降级为默认分析
- **Redis 不可用**:缓存降级为仅 L1 内存
- **Embedding 模型不可用**:向量库降级为随机向量(开发模式)

#### 8.3.3 迁移工具

```bash
# 数据迁移(JSON → SQL)
python -m app.data.migrations --dry-run    # 预览
python -m app.data.migrations --verify     # 验证

# 题目校准
python calibrate_questions.py --dry-run
python calibrate_questions.py --limit 10 --skip-calibrated
```

---

## 九、测试与 CI/CD

### 9.1 测试

项目包含 27 个测试文件,覆盖核心模块(Agent、RAG、向量库、难度评估、安全、错题本、工具注册、任务规划器等)。

**运行测试**:

```bash
pytest tests/ --ignore=tests/test_vector_store.py --ignore=tests/test_api_integration.py \
    --cov=app --cov=agent_core --cov-report=html --cov-report=term --cov-fail-under=40
```

- 覆盖率门槛:40%
- `conftest.py` 提供测试 fixtures
- `locustfile.py` 提供压力测试

### 9.2 CI/CD

[.github/workflows/ci.yml](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/.github/workflows/ci.yml)

**触发条件**:push 到 main/master/cleanup/refactor,PR 到 main/master

**3 个 Job**:

1. **backend-test**(Python 3.10):
   - flake8 lint(`app/` + `agent_core/`)
   - pytest(覆盖率门槛 40%)
   - 上传 htmlcov artifact

2. **frontend-build**(Node 18):
   - `npm ci`
   - `npm run build`

3. **docker-build**(仅 push 到 main 时,依赖前两个 Job):
   - `docker build -t math-ai-assistant .`

### 9.3 Dev Container

[.devcontainer/devcontainer.json](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/.devcontainer/devcontainer.json)

- 镜像:`mcr.microsoft.com/devcontainers/python:3.10`
- VSCode 扩展:Python、Pylance
- 转发端口:8000
- `postCreateCommand`:`pip install -r requirements.txt`

---

## 十、设计模式速查表

| 设计模式 | 应用位置 | 说明 |
|---------|---------|------|
| **配置对象模式** | `MathAgentConfig` | dataclass 聚合参数,避免构造函数参数爆炸 |
| **策略模式** | `AgentStrategy` + `LangChainReActStrategy` | 抽象基类 + 可插拔实现 |
| **适配器模式** | `LangChainToolConverter` | BaseTool → StructuredTool |
| **Facade 模式** | `MemoryPersistenceFacade` | 统一访问记忆/技能/难度多个服务 |
| **观察者模式** | `ThoughtRecordingCallbackHandler` | 监听 LangChain 事件流 |
| **工厂模式** | `DynamicLLMFactory`、各 `get_xxx()` | 懒加载单例创建 |
| **单例模式** | `LLMService`、`HybridToolRegistry`、`AuditLogger` 等 | 全局唯一实例 |
| **DAG 任务编排** | `TaskPlanner` + `TaskDAG` | 拓扑排序 + 并行分组 + 关键路径 |
| **多级降级** | `LLMComplexityClassifier`(LLM→缓存→规则) | 保证主流程不中断 |
| **两级缓存** | `CacheManager`(L1内存+L2Redis) | 分层缓存提升命中 |
| **事件驱动** | `EnhancedEventBuffer`、`ErrorBookSkillSyncService` | 异步事件 + 回调链 |
| **模板方法** | `BaseTool.execute()` | 抽象基类定义契约 |
| **能力标签系统** | `ToolCapability` 枚举 | 驱动工具搜索 |
| **版本缓存** | `SystemPromptManager` | SHA256 哈希变化检测 |
| **双写兼容** | `ThoughtRecordingCallbackHandler` | 同时维护新旧两套记录 |
| **安全执行门面** | `HybridToolRegistry.execute_safe` | 统一容错入口 |
| **意图感知持久化** | `INTENT_PERSISTENCE_MAP` | 按意图决定 TTL 与记录粒度 |
| **乐观更新** | 前端 `errorBookStore` | 先本地后同步,弱网友好 |

---

## 附录:关键文件索引

| 文件 | 一句话职责 |
|------|-----------|
| [main.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/main.py) | FastAPI 应用入口 |
| [app/config/settings.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/config/settings.py) | 全局配置(pydantic-settings) |
| [app/lifespan.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/lifespan.py) | 应用生命周期(DB/Cache/Vector 初始化) |
| [app/middleware_setup.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/middleware_setup.py) | 中间件集中注册 |
| [app/dependencies.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/dependencies.py) | 依赖注入中心(Protocol) |
| [agent_core/agent.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/agent_core/agent.py) | MathAgent 统一入口 |
| [agent_core/strategies/langchain_react.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/agent_core/strategies/langchain_react.py) | LangChain ReAct 策略实现 |
| [agent_core/classifier/llm_classifier.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/agent_core/classifier/llm_classifier.py) | LLM 复杂度分类器 |
| [agent_core/task_planner.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/agent_core/task_planner.py) | DAG 任务规划器 |
| [agent_core/memory_persistence.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/agent_core/memory_persistence.py) | 记忆持久化门面 |
| [tools/hybrid_registry.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/tools/hybrid_registry.py) | 混合工具注册中心 |
| [prompts/system_prompt.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/prompts/system_prompt.py) | 四层 System Prompt 管理器 |
| [prompts/dynamic_params.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/prompts/dynamic_params.py) | 动态参数映射 + LLM 工厂 |
| [app/services/llm_service.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/services/llm_service.py) | LLM 服务(单例+缓存+TIR) |
| [app/services/vector_store.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/services/vector_store.py) | Qdrant 向量存储 |
| [app/services/rag_recommender.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/services/rag_recommender.py) | RAG 推荐引擎 |
| [app/services/difficulty_estimator.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/services/difficulty_estimator.py) | 难度评估器(四因子加权) |
| [app/services/skill_aggregator.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/services/skill_aggregator.py) | 技能聚合(Elo-style) |
| [app/services/memory.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/services/memory.py) | 双层记忆系统 |
| [app/data/models.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/data/models.py) | ORM 数据模型(8 张表) |
| [app/data/database.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/data/database.py) | 数据库配置(异步引擎) |
| [app/data/repositories.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/data/repositories.py) | 仓储模式(BaseRepository) |
| [app/middleware/auth.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/middleware/auth.py) | JWT 认证工具 |
| [app/middleware/security.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/middleware/security.py) | 输入校验/威胁检测 |
| [app/security/access_control.py](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/app/security/access_control.py) | RBAC 权限映射 |
| [frontend/src/utils/markdown.js](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/frontend/src/utils/markdown.js) | LaTeX 渲染管线核心 |
| [frontend/src/views/ChatView.vue](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/frontend/src/views/ChatView.vue) | 对话主界面(流式输出) |
| [frontend/src/stores/chatStore.js](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/frontend/src/stores/chatStore.js) | 多会话聊天状态 |
| [frontend/nginx.conf](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/frontend/nginx.conf) | 生产 Nginx 配置(SSE 关键) |
| [docker-compose.yml](file:///c:/Users/HUAWEI/Desktop/math%20AI%20assistant/docker-compose.yml) | 容器编排(4 服务) |

---

> **文档说明**:本文档基于项目源码静态分析生成,涵盖项目整体架构、主要模块职责、关键类与函数说明、依赖关系以及项目运行方式。文档未读取 `.env` 文件内容,所有配置项均来自代码中的默认值与类型定义。如需了解各模块的详细设计思路,请参阅 `docs/architecture/`、`docs/development/`、`docs/api/` 目录下的专项文档。
