# 数学AI助手项目代码清理与架构优化 - 验收检查清单

## 一、代码清理验收

- [ ] Python代码总行数从约15000行减少到约10500行（减少30%），使用 `cloc` 工具验证
- [ ] `main.py` 行数 < 200行，仅保留应用入口和路由注册
- [ ] `agent_core/context_manager.py` 已删除，Agent核心功能正常
- [ ] `agent_core/strategies/react.py` 已删除（标记@deprecated的废弃代码）
- [ ] `agent_core/strategies/planned.py` 已删除（未使用的PlannedStrategy）
- [ ] `frontend/src/utils/latexPreprocessor.js` 已删除
- [ ] `frontend/src/utils/mathRender.js` 已删除
- [ ] `markdown.js` 作为前端唯一LaTeX渲染入口，所有公式正确渲染
- [ ] 所有僵尸测试文件已删除（test_legacy_parser.py, test_deprecated_api.py, manual_test_*.py）
- [ ] 所有一次性脚本已删除（migrate_db_v1_to_v2.py, fix_encoding.py, generate_fake_data.py, adhoc_*.py）
- [ ] 构建产物和缓存已清理（__pycache__, .pytest_cache, node_modules等）
- [ ] `.gitignore` 已更新，排除构建产物和缓存文件

## 二、架构优化验收

- [ ] `app/api/chat_api.py` 已创建，包含所有聊天相关路由
- [ ] `app/api/error_api.py` 已创建，包含所有错题本相关路由
- [ ] `app/api/agent_api.py` 已创建，包含所有Agent相关路由
- [ ] `app/services/stream_handler.py` 已创建，流式响应处理独立
- [ ] `app/lifespan.py` 已创建，应用生命周期管理独立
- [ ] `app/middleware_setup.py` 已创建，中间件配置独立
- [ ] 依赖注入改造完成：MathAgent通过构造函数接收依赖
- [ ] 循环依赖数 = 0，使用依赖图分析工具验证
- [ ] 代码重复率 < 10%
- [ ] 单文件行数 < 500行

## 三、测试覆盖验收

- [ ] 单元测试覆盖率 > 60%，使用 `pytest --cov=app --cov-fail-under=60` 验证
- [ ] 集成测试覆盖率 > 40%
- [ ] 所有测试通过，`pytest` 执行无失败
- [ ] 测试执行时间 < 60秒
- [ ] 核心模块（LLM服务、RAG推荐、向量存储）有单元测试
- [ ] 关键API端点有集成测试
- [ ] 测试可以方便地Mock依赖

## 四、文档验收

- [ ] 所有文档集中在 `docs/` 目录
- [ ] `docs/README.md` 作为文档索引已创建
- [ ] `docs/architecture/` 目录已创建，包含架构文档
- [ ] `docs/development/` 目录已创建，包含开发指南
- [ ] `docs/api/` 目录已创建，包含API文档
- [ ] 所有文档链接有效，无死链
- [ ] 关键模块有文档字符串说明

## 五、生产就绪验收

- [ ] `Dockerfile` 已创建，可以成功构建后端镜像
- [ ] `docker-compose.yml` 已创建，可以成功启动多服务
- [ ] `.github/workflows/ci.yml` 已创建，CI流水线在PR时自动触发
- [ ] CI流水线包含代码检查（flake8, mypy, black）
- [ ] CI流水线包含测试执行和覆盖率报告
- [ ] API响应时间 P95 < 500ms
- [ ] 流式响应首字节时间 < 1秒
- [ ] 无硬编码密钥/密码，所有敏感信息从环境变量读取
- [ ] 无高危依赖漏洞（pip-audit, npm audit）
- [ ] 所有数据库操作使用ORM或参数化查询

## 六、功能回归验收

- [ ] 聊天API端点功能正常（/api/chat/message, /api/chat/history）
- [ ] 错题本API端点功能正常（/api/error-book/add, /api/error-book/list）
- [ ] 推荐API端点功能正常（/api/recommendation）
- [ ] 流式响应功能正常，延迟 < 1秒
- [ ] 前端页面正常渲染
- [ ] LaTeX公式正确渲染，无控制台错误
- [ ] 前端构建成功（npm run build）
