# 数学AI助手项目代码清理与架构优化 PRD Spec

## Why

数学AI助手项目经过多轮迭代开发，已形成功能完整但代码质量参差不齐的半成品状态。当前存在以下核心问题：

* **代码冗余严重**：800行的 `main.py` 承载了路由、业务逻辑、数据验证等多重职责

* **过度设计**：`SmartContextManager` 等模块实现了未使用的复杂功能，增加了认知负担

* **死代码堆积**：废弃的策略、重复的工具函数、过时的文档文件混杂在代码库中

* **架构偏离**：实际实现与理想架构存在偏差，循环依赖和全局可变状态问题突出

本次代码清理和架构优化旨在将"功能丰富但难以维护的半成品"转变为"功能精简但架构清晰的可持续演进系统"，为后续的生产环境部署奠定基础。

## What Changes

### 核心变更

* **代码体积缩减30%**：从15000行减少到10500行

* **main.py拆分**：从800行拆分到200行以内，职责单一化

* **测试覆盖率提升**：从<30%提升到>60%

* **文档集中化管理**：所有文档集中在docs/目录，结构清晰

* **删除过度设计模块**：移除未使用的SmartContextManager、废弃策略等

* **前端LaTeX渲染统一**：删除重叠的渲染模块，统一渲染管线

* **依赖注入改造**：降低模块耦合，提高可测试性

### 不变的部分

* **技术栈保持不变**：FastAPI + Vue 3 + LangChain

* **核心功能保持不变**：聊天、错题本、推荐等功能逻辑不变

* **数据库结构保持不变**：不改变现有数据表结构

## Impact

### Affected specs

* 代码组织结构

* 模块依赖关系

* 测试覆盖范围

* 文档结构

### Affected code

* `main.py` → 拆分为多个路由文件

* `agent_core/context_manager.py` → 删除

* `agent_core/strategies/react.py` → 删除

* `agent_core/strategies/planned.py` → 删除

* `frontend/src/utils/latexPreprocessor.js` → 删除

* `frontend/src/utils/mathRender.js` → 删除

* `app/services/` → 新增依赖注入支持

* `docs/` → 重新组织文档结构

## ADDED Requirements

### Requirement: main.py拆分重构

系统 SHALL 将800行的 `main.py` 拆分为多个职责单一的文件，每个文件不超过200行。

#### Scenario: 路由拆分成功

* **WHEN** 执行main.py拆分

* **THEN** 生成 `app/api/chat_api.py`、`app/api/error_api.py`、`app/api/agent_api.py` 等路由文件

* **AND** 每个路由文件行数 < 200行

* **AND** 所有API端点功能正常，测试通过

#### Scenario: 流式处理独立

* **WHEN** 拆分流式响应处理逻辑

* **THEN** 生成 `app/services/stream_handler.py`

* **AND** 流式响应功能正常，延迟 < 1秒

### Requirement: 过度设计模块删除

系统 SHALL 删除未使用或过度抽象的模块，简化架构。

#### Scenario: SmartContextManager删除

* **WHEN** 确认SmartContextManager未被使用

* **THEN** 删除 `agent_core/context_manager.py`

* **AND** Agent核心功能正常

* **AND** 相关测试通过

#### Scenario: 废弃策略删除

* **WHEN** 确认react.py和planned.py已废弃

* **THEN** 删除 `agent_core/strategies/react.py` 和 `agent_core/strategies/planned.py`

* **AND** Agent使用LangChainReActStrategy正常工作

### Requirement: 前端LaTeX渲染统一

系统 SHALL 统一前端LaTeX渲染管线，删除重叠模块。

#### Scenario: 渲染入口统一

* **WHEN** 统一LaTeX渲染

* **THEN** 保留 `markdown.js` 作为唯一渲染入口

* **AND** 删除 `latexPreprocessor.js` 和 `mathRender.js`

* **AND** 所有LaTeX公式正确渲染

* **AND** 无控制台错误和警告

### Requirement: 依赖注入改造

系统 SHALL 将模块级的全局单例改为依赖注入模式，降低模块耦合。

#### Scenario: MathAgent依赖注入

* **WHEN** 改造MathAgent依赖

* **THEN** MathAgent的配置通过构造函数注入

* **AND** VectorStoreManager和LLMService通过依赖注入获取

* **AND** 测试可以方便地Mock依赖

* **AND** 生产代码功能不受影响

### Requirement: 测试覆盖率提升

系统 SHALL 提升测试覆盖率到60%以上。

#### Scenario: 单元测试覆盖

* **WHEN** 编写单元测试

* **THEN** 核心模块（LLM服务、RAG推荐、向量存储）有单元测试

* **AND** 测试覆盖率 > 60%

* **AND** 所有测试通过

#### Scenario: 集成测试覆盖

* **WHEN** 编写集成测试

* **THEN** 关键API端点有集成测试

* **AND** 测试覆盖率 > 40%

* **AND** 端到端测试验证功能正常

### Requirement: 文档集中化管理

系统 SHALL 将所有项目文档集中到docs/目录，结构清晰。

#### Scenario: 文档结构重组

* **WHEN** 整理文档结构

* **THEN** 创建 `docs/architecture/`、`docs/development/`、`docs/api/` 等子目录

* **AND** 所有文档集中在docs/目录

* **AND** 创建 `docs/README.md` 作为文档索引

* **AND** 所有文档链接有效

## MODIFIED Requirements

### Requirement: 代码体积缩减

系统 SHALL 通过删除无用文件、合并重复模块、清理死代码，将代码体积缩减30%。

#### Scenario: 代码体积减少

* **WHEN** 执行代码清理

* **THEN** Python代码行数从15000行减少到10500行

* **AND** 使用 `cloc` 工具统计验证

* **AND** 所有功能正常

### Requirement: 模块耦合度降低

系统 SHALL 通过依赖注入改造和模块重组，降低模块耦合度。

#### Scenario: 循环依赖消除

* **WHEN** 执行依赖注入改造

* **THEN** 循环依赖数 = 0

* **AND** 使用依赖图分析工具验证

* **AND** 模块可以独立测试

## REMOVED Requirements

### Requirement: SmartContextManager

**Reason**: 实现了未使用的复杂功能，增加了认知负担，LangChain已内置对话历史管理
**Migration**: 无需迁移，直接删除

### Requirement: ReActStrategy和PlannedStrategy

**Reason**: 已标记为@deprecated，实际使用LangChainReActStrategy
**Migration**: 无需迁移，直接删除

### Requirement: 前端多渲染入口

**Reason**: latexPreprocessor.js和mathRender.js与markdown.js功能重叠，导致渲染不稳定
**Migration**: 统一使用markdown.js作为唯一渲染入口

## Non-Functional Requirements

### Performance

* **测试执行时间**：完整测试套件 < 60秒

* **代码搜索时间**：全项目搜索 < 1秒

* **API响应时间**：P95 < 500ms

* **流式响应首字节时间**：< 1秒

### Maintainability

* **代码复杂度**：单文件行数 < 500行

* **模块耦合度**：循环依赖数 = 0

* **代码重复率**：< 10%

* **注释覆盖率**：> 30%（关键逻辑必须有注释）

### Testability

* **单元测试覆盖率**：> 60%

* **集成测试覆盖率**：> 40%

* **测试执行成功率**：100%（CI环境）

### Security

* **敏感信息泄露**：0个硬编码密钥/密码

* **依赖漏洞**：0个高危漏洞

* **SQL注入风险**：0个（全部使用ORM或参数化查询）

### Compatibility

* **Python版本**：支持Python 3.10+

* **Node.js版本**：支持Node.js 18+

* **浏览器兼容**：Chrome 90+, Firefox 88+, Safari 14+

## Tech Stack Decision

### 保持不变的技术栈

* **后端框架**：FastAPI (Python 3.10+)

* **前端框架**：Vue 3 + Vite

* **AI框架**：LangChain

* **数据库**：SQLite（开发）/ PostgreSQL（生产）

* **向量存储**：ChromaDB

* **UI库**：Element Plus

* **数学渲染**：KaTeX

### 新增工具

* **测试框架**：pytest + pytest-cov + pytest-asyncio

* **代码质量**：flake8 + mypy + black

* **依赖管理**：pip（后端）+ npm（前端）

* **容器化**：Docker + docker-compose

* **CI/CD**：GitHub Actions

### 禁止事项

* 禁止引入新的AI框架（如LlamaIndex）

* 禁止替换数据库（如从SQLite换到MongoDB）

* 禁止替换前端框架（如从Vue换到React）

## Architecture and Repo Boundaries

### 目标架构

```
┌─────────────────────────────────────────┐
│         前端层 (Vue 3 + Element Plus)    │
└─────────────────┬───────────────────────┘
                  │ SSE/REST
┌─────────────────▼───────────────────────┐
│         API路由层 (app/api/)             │
│  - chat_api.py                          │
│  - error_api.py                         │
│  - agent_api.py                         │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│         业务服务层 (app/services/)       │
│  - llm_service.py                       │
│  - rag_recommender.py                   │
│  - stream_handler.py                    │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│         Agent核心层 (agent_core/)        │
│  - agent.py (简化版)                    │
│  - tool_registry.py                     │
└─────────────────┬───────────────────────┘
                  │
┌─────────────────▼───────────────────────┐
│         数据访问层 (app/data/)           │
│  - models.py                            │
│  - repositories.py                      │
│  - database.py                          │
└─────────────────────────────────────────┘
```

### 目录边界

* **可修改**：`app/api/`, `app/services/`, `agent_core/`, `frontend/src/utils/`, `docs/`

* **不可修改**：`app/data/models.py`（数据库结构）, `requirements.txt`（依赖版本）

* **需要审查**：`main.py`（拆分后保留的部分）

## Build/Run/Validate Contract

### Setup Commands

```bash
# 后端环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows
pip install -r requirements.txt

# 前端环境
cd frontend
npm install
```

### Run Commands

```bash
# 启动后端
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 启动前端
cd frontend
npm run dev
```

### Test Commands

```bash
# 运行所有测试
pytest

# 运行测试并生成覆盖率报告
pytest --cov=app --cov-report=html

# 运行特定测试
pytest tests/test_chat_api.py
```

### Lint Commands

```bash
# 代码风格检查
flake8 app/

# 类型检查
mypy app/

# 代码格式化
black app/
```

### Build Commands

```bash
# 构建Docker镜像
docker build -t math-ai-assistant .

# 启动Docker容器
docker-compose up -d
```

### Validate Commands

```bash
# 验证API端点
curl http://localhost:8000/api/health

# 验证前端构建
cd frontend && npm run build

# 验证测试覆盖率
pytest --cov=app --cov-fail-under=60
```

## Security, Risk, and Compliance

### 安全风险

| 风险         | 概率 | 影响 | 缓解措施        |
| ---------- | -- | -- | ----------- |
| 删除文件导致功能异常 | 中  | 高  | 删除前备份，逐步验证  |
| 重构引入新Bug   | 中  | 高  | 完善测试覆盖，小步迭代 |
| 文档更新不及时    | 高  | 中  | 建立文档更新流程    |

### 合规要求

* 所有API端点必须有输入验证

* 所有数据库操作必须使用ORM或参数化查询

* 所有敏感信息必须从环境变量读取

* 所有日志不得包含用户密码、API密钥等敏感信息

### 数据分类

* **公开数据**：文档、README

* **内部数据**：源代码、测试用例

* **敏感数据**：API密钥、数据库密码（必须从环境变量读取）

## Observability and Operational Readiness

### 日志要求

* 所有API请求必须记录日志（INFO级别）

* 所有错误必须记录日志（ERROR级别）

* 日志格式：`[时间] [级别] [模块] 消息`

* 日志保留：本地7天，生产环境30天

### 监控指标

* API响应时间（P50, P95, P99）

* 测试覆盖率

* 代码复杂度

* 错误率

### 告警规则

* API响应时间P95 > 1秒：告警

* 测试覆盖率 < 60%：告警

* 错误率 > 1%：告警

### 运维文档

* 部署文档：`docs/development/deployment.md`

* 故障排查文档：`docs/development/troubleshooting.md`

* API文档：FastAPI自动生成 `/docs`

## Phase Plan

### Phase 0: 准备工作（第1周）

* [ ] E0.1: 创建清理分支，备份当前代码

* [ ] E0.2: 建立测试基准，记录当前测试覆盖率

* [ ] E0.3: 识别所有死代码和过度设计模块

* [ ] E0.4: 制定详细的清理清单和风险评估

### Phase 1: 核心清理（第2-3周）

* [ ] E1.1: 删除SmartContextManager和废弃策略

* [ ] E1.2: 拆分main.py为多个路由文件

* [ ] E1.3: 统一前端LaTeX渲染管线

* [ ] E1.4: 删除重复的测试文件和脚本

### Phase 2: 架构优化（第4-5周）

* [ ] E2.1: 依赖注入改造

* [ ] E2.2: 补充单元测试（覆盖率>60%）

* [ ] E2.3: 补充集成测试（覆盖率>40%）

* [ ] E2.4: 文档集中化管理

### Phase 3: 生产就绪（第6周）

* [ ] E3.1: Docker容器化配置

* [ ] E3.2: CI/CD流水线配置

* [ ] E3.3: 性能测试和优化

* [ ] E3.4: 安全扫描和漏洞修复

## Epic Cards

### E0.1: 创建清理分支

**目标**：建立安全的开发环境
**验收标准**：

* [ ] 创建 `cleanup/refactor` 分支

* [ ] 备份当前代码到 `backup/` 目录

* [ ] 确认可以回滚到原始状态

**验证命令**：

```bash
git checkout -b cleanup/refactor
git branch -a
```

### E0.2: 建立测试基准

**目标**：记录当前测试覆盖率，作为改进基准
**验收标准**：

* [ ] 运行 `pytest --cov=app` 记录当前覆盖率

* [ ] 生成覆盖率报告

* [ ] 识别测试盲区

**验证命令**：

```bash
pytest --cov=app --cov-report=html
```

### E1.1: 删除过度设计模块

**目标**：简化架构，删除未使用的模块
**验收标准**：

* [ ] 删除 `agent_core/context_manager.py`

* [ ] 删除 `agent_core/strategies/react.py`

* [ ] 删除 `agent_core/strategies/planned.py`

* [ ] Agent核心功能正常

* [ ] 所有测试通过

**验证命令**：

```bash
pytest tests/test_agent.py
```

### E1.2: 拆分main.py

**目标**：将800行的main.py拆分为多个职责单一的文件
**验收标准**：

* [ ] 创建 `app/api/chat_api.py`

* [ ] 创建 `app/api/error_api.py`

* [ ] 创建 `app/api/agent_api.py`

* [ ] 创建 `app/services/stream_handler.py`

* [ ] main.py行数 < 200行

* [ ] 所有API端点功能正常

**验证命令**：

```bash
wc -l main.py  # 应该 < 200
pytest tests/test_api.py
```

### E1.3: 统一前端LaTeX渲染

**目标**：删除重叠的渲染模块，统一渲染管线
**验收标准**：

* [ ] 保留 `markdown.js` 作为唯一渲染入口

* [ ] 删除 `latexPreprocessor.js`

* [ ] 删除 `mathRender.js`

* [ ] 所有LaTeX公式正确渲染

* [ ] 无控制台错误和警告

**验证命令**：

```bash
cd frontend && npm run build
# 浏览器测试LaTeX渲染
```

### E2.1: 依赖注入改造

**目标**：降低模块耦合，提高可测试性
**验收标准**：

* [ ] MathAgent的配置通过构造函数注入

* [ ] VectorStoreManager通过依赖注入获取

* [ ] LLMService通过依赖注入获取

* [ ] 测试可以方便地Mock依赖

* [ ] 生产代码功能不受影响

**验证命令**：

```bash
pytest tests/test_agent.py
```

### E2.2: 补充单元测试

**目标**：提升测试覆盖率到60%以上
**验收标准**：

* [ ] 核心模块有单元测试

* [ ] 测试覆盖率 > 60%

* [ ] 所有测试通过

**验证命令**：

```bash
pytest --cov=app --cov-fail-under=60
```

### E3.1: Docker容器化配置

**目标**：实现Docker容器化部署
**验收标准**：

* [ ] 创建 `Dockerfile`

* [ ] 创建 `docker-compose.yml`

* [ ] 可以成功构建和启动容器

* [ ] 容器内服务正常运行

**验证命令**：

```bash
docker build -t math-ai-assistant .
docker-compose up -d
curl http://localhost:8000/api/health
```

## Open Questions and Decision Log

| # | 问题                 | 决策                             | 影响        |
| - | ------------------ | ------------------------------ | --------- |
| 1 | 是否需要迁移到PostgreSQL？ | 否，保持SQLite（开发）/ PostgreSQL（生产） | 不影响当前清理工作 |
| 2 | 是否需要引入新的监控工具？      | 否，使用FastAPI内置日志                | 减少依赖      |
| 3 | 是否需要重写前端？          | 否，保持Vue 3 + Element Plus       | 不影响当前清理工作 |

## Definition of Done

### 代码清理完成标准

* [ ] 代码体积减少30%（从15000行到10500行）

* [ ] main.py行数 < 200行

* [ ] 删除所有过度设计模块

* [ ] 删除所有死代码

* [ ] 统一前端LaTeX渲染

### 架构优化完成标准

* [ ] 依赖注入改造完成

* [ ] 循环依赖数 = 0

* [ ] 模块可以独立测试

* [ ] 代码重复率 < 10%

### 测试覆盖完成标准

* [ ] 单元测试覆盖率 > 60%

* [ ] 集成测试覆盖率 > 40%

* [ ] 所有测试通过

* [ ] 测试执行时间 < 60秒

### 文档完善完成标准

* [ ] 所有文档集中在docs/目录

* [ ] 文档结构清晰，有索引

* [ ] 所有文档链接有效

* [ ] 关键模块有文档说明

### 生产就绪完成标准

* [ ] Docker容器化配置完成

* [ ] CI/CD流水线配置完成

* [ ] 性能测试通过

* [ ] 安全扫描通过

* [ ] 无高危漏洞

### 验收标准

* [ ] 所有功能正常

* [ ] 所有测试通过

* [ ] 代码审查通过

* [ ] 文档审查通过

* [ ] 运维审查通过

