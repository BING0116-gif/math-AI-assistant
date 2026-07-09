# 数学AI助手项目代码清理与架构优化 - 任务清单

## Phase 0: 准备工作（第1周）

### E0.1: 创建清理分支
- [ ] 创建 `cleanup/refactor` 分支
- [ ] 备份当前代码到 `backup/` 目录
- [ ] 确认可以回滚到原始状态
- [ ] 验证分支创建成功

### E0.2: 建立测试基准
- [ ] 运行 `pytest --cov=app` 记录当前覆盖率
- [ ] 生成覆盖率报告到 `htmlcov/` 目录
- [ ] 识别测试盲区并记录
- [ ] 保存基准数据到 `docs/baseline/coverage_baseline.md`

### E0.3: 识别死代码和过度设计模块
- [ ] 使用静态分析工具识别未使用的代码
- [ ] 列出所有标记为 @deprecated 的代码
- [ ] 识别未使用的导入和变量
- [ ] 生成死代码清单到 `docs/baseline/dead_code_list.md`

### E0.4: 制定清理清单和风险评估
- [ ] 创建详细的文件删除清单
- [ ] 评估每个删除操作的风险等级
- [ ] 制定回滚计划
- [ ] 获得团队评审通过

---

## Phase 1: 核心清理（第2-3周）

### E1.1: 删除过度设计模块
- [ ] 删除 `agent_core/context_manager.py`
- [ ] 删除 `agent_core/strategies/react.py`
- [ ] 删除 `agent_core/strategies/planned.py`
- [ ] 更新 `agent_core/__init__.py` 移除相关导入
- [ ] 运行 `pytest tests/test_agent.py` 验证功能正常
- [ ] 确认无循环依赖

### E1.2: 拆分main.py
- [ ] 创建 `app/api/chat_api.py` - 聊天相关路由
- [ ] 创建 `app/api/error_api.py` - 错题本相关路由
- [ ] 创建 `app/api/agent_api.py` - Agent相关路由
- [ ] 创建 `app/services/stream_handler.py` - 流式响应处理
- [ ] 创建 `app/lifespan.py` - 应用生命周期管理
- [ ] 创建 `app/middleware_setup.py` - 中间件配置
- [ ] 重构 `main.py` 仅保留应用入口
- [ ] 验证 `wc -l main.py < 200`
- [ ] 运行 `pytest tests/test_api.py` 验证所有API端点

### E1.3: 统一前端LaTeX渲染
- [ ] 备份现有渲染相关文件
- [ ] 删除 `frontend/src/utils/latexPreprocessor.js`
- [ ] 删除 `frontend/src/utils/mathRender.js`
- [ ] 更新 `frontend/src/utils/markdown.js` 确保功能完整
- [ ] 更新所有引用这些文件的组件
- [ ] 运行 `cd frontend && npm run build` 验证构建
- [ ] 浏览器测试各种LaTeX公式渲染
- [ ] 确认无控制台错误和警告

### E1.4: 删除重复的测试文件和脚本
- [ ] 识别 `tests/` 目录下的僵尸测试
- [ ] 删除 `test_legacy_parser.py`
- [ ] 删除 `test_deprecated_api.py`
- [ ] 删除所有 `manual_test_*.py` 文件
- [ ] 清理 `fixtures/` 中未使用的文件
- [ ] 识别 `scripts/` 目录下的一次性脚本
- [ ] 删除 `migrate_db_v1_to_v2.py`
- [ ] 删除 `fix_encoding.py`
- [ ] 删除 `generate_fake_data.py`
- [ ] 删除所有 `adhoc_*.py` 文件
- [ ] 运行 `pytest --collect-only` 验证测试收集正常

---

## Phase 2: 架构优化（第4-5周）

### E2.1: 依赖注入改造
- [ ] 创建 `app/dependencies.py` - 依赖注入配置
- [ ] 修改 `MathAgent.__init__` 接受依赖参数
- [ ] 创建 `LLMServiceProtocol` 接口
- [ ] 创建 `VectorStoreProtocol` 接口
- [ ] 实现 `get_llm_service()` 依赖工厂
- [ ] 实现 `get_vector_store()` 依赖工厂
- [ ] 更新所有API路由使用依赖注入
- [ ] 更新测试用例使用Mock依赖
- [ ] 运行 `pytest tests/test_agent.py` 验证功能

### E2.2: 补充单元测试
- [ ] 为 `app/services/llm_service.py` 编写单元测试
- [ ] 为 `app/services/rag_recommender.py` 编写单元测试
- [ ] 为 `app/services/vector_store.py` 编写单元测试
- [ ] 为 `app/services/difficulty_estimator.py` 编写单元测试
- [ ] 为 `app/services/skill_aggregator.py` 编写单元测试
- [ ] 为 `agent_core/agent.py` 编写单元测试
- [ ] 为 `agent_core/tool_registry.py` 编写单元测试
- [ ] 运行 `pytest --cov=app --cov-fail-under=60` 验证覆盖率

### E2.3: 补充集成测试
- [ ] 为 `/api/chat/message` 编写集成测试
- [ ] 为 `/api/chat/history` 编写集成测试
- [ ] 为 `/api/error-book/add` 编写集成测试
- [ ] 为 `/api/error-book/list` 编写集成测试
- [ ] 为 `/api/recommendation` 编写集成测试
- [ ] 编写端到端测试验证完整流程
- [ ] 运行 `pytest tests/integration/` 验证集成测试

### E2.4: 文档集中化管理
- [ ] 创建 `docs/architecture/` 目录
- [ ] 创建 `docs/development/` 目录
- [ ] 创建 `docs/api/` 目录
- [ ] 创建 `docs/prd/` 目录
- [ ] 移动根目录的 Markdown 文件到 `docs/`
- [ ] 创建 `docs/README.md` 作为文档索引
- [ ] 更新所有文档链接
- [ ] 验证所有文档链接有效

---

## Phase 3: 生产就绪（第6周）

### E3.1: Docker容器化配置
- [ ] 创建 `Dockerfile` - 后端镜像
- [ ] 创建 `frontend/Dockerfile` - 前端镜像
- [ ] 创建 `docker-compose.yml` - 多服务编排
- [ ] 创建 `.dockerignore` 文件
- [ ] 测试 `docker build -t math-ai-assistant .`
- [ ] 测试 `docker-compose up -d`
- [ ] 验证 `curl http://localhost:8000/api/health`
- [ ] 验证前端服务正常访问

### E3.2: CI/CD流水线配置
- [ ] 创建 `.github/workflows/ci.yml`
- [ ] 配置代码检查步骤（flake8, mypy, black）
- [ ] 配置测试执行步骤（pytest）
- [ ] 配置覆盖率报告上传
- [ ] 配置Docker镜像构建
- [ ] 配置镜像推送到仓库
- [ ] 测试CI流水线在PR时触发
- [ ] 验证所有检查通过

### E3.3: 性能测试和优化
- [ ] 使用 `locust` 编写性能测试脚本
- [ ] 测试API响应时间（目标P95 < 500ms）
- [ ] 测试流式响应首字节时间（目标 < 1s）
- [ ] 测试数据库查询性能
- [ ] 识别性能瓶颈
- [ ] 优化慢查询和热点代码
- [ ] 生成性能测试报告

### E3.4: 安全扫描和漏洞修复
- [ ] 运行 `pip-audit` 检查Python依赖漏洞
- [ ] 运行 `npm audit` 检查Node.js依赖漏洞
- [ ] 使用 `bandit` 进行Python代码安全扫描
- [ ] 检查硬编码密钥和密码
- [ ] 验证所有敏感信息从环境变量读取
- [ ] 验证日志不包含敏感信息
- [ ] 修复所有高危漏洞
- [ ] 生成安全扫描报告

---

## 任务依赖关系

```
E0.1 → E0.2 → E0.3 → E0.4
                  ↓
E1.1, E1.2, E1.3, E1.4 (可并行)
                  ↓
E2.1 → E2.2, E2.3 (可并行)
                  ↓
E2.4
                  ↓
E3.1, E3.2, E3.3, E3.4 (可并行)
```

## 关键里程碑

- **M1 (第1周末)**: Phase 0 完成，建立测试基准
- **M2 (第3周末)**: Phase 1 完成，核心清理完成
- **M3 (第5周末)**: Phase 2 完成，架构优化完成
- **M4 (第6周末)**: Phase 3 完成，生产就绪

## 验收标准汇总

### 代码清理
- [ ] 代码体积减少30%（从15000行到10500行）
- [ ] main.py行数 < 200行
- [ ] 删除所有过度设计模块
- [ ] 删除所有死代码
- [ ] 统一前端LaTeX渲染

### 架构优化
- [ ] 依赖注入改造完成
- [ ] 循环依赖数 = 0
- [ ] 模块可以独立测试
- [ ] 代码重复率 < 10%

### 测试覆盖
- [ ] 单元测试覆盖率 > 60%
- [ ] 集成测试覆盖率 > 40%
- [ ] 所有测试通过
- [ ] 测试执行时间 < 60秒

### 文档完善
- [ ] 所有文档集中在docs/目录
- [ ] 文档结构清晰，有索引
- [ ] 所有文档链接有效
- [ ] 关键模块有文档说明

### 生产就绪
- [ ] Docker容器化配置完成
- [ ] CI/CD流水线配置完成
- [ ] 性能测试通过
- [ ] 安全扫描通过
- [ ] 无高危漏洞
