# 代码清理 PRD — 数学AI助手项目

> 版本: 1.1 | 日期: 2026-06-07 | 状态: ✅ 已完成

---

## 1. 项目概况

### 1.1 项目规模
- **总文件数**: ~110+ 个源代码文件
- **Python模块**: ~70 个 (.py)
- **前端文件**: ~25 个 (.vue/.js/.scss)
- **测试文件**: ~30 个
- **文档文件**: ~35 个 (.md)
- **脚本文件**: ~22 个

### 1.2 核心架构
```
main.py (入口)
├── agent_core/     (Agent核心层 - 15个文件)
├── tools/          (工具层 - 11个文件)
├── app/            (应用层 - 35个文件)
│   ├── api/        (5个路由)
│   ├── config/     (2个配置)
│   ├── data/       (5个数据模块)
│   ├── middleware/ (6个中间件)
│   ├── plugins/    (2个插件文件)
│   ├── security/   (4个安全模块)
│   └── services/   (14个服务)
├── prompts/        (6个Prompt模块)
├── data_processing/(2个数据处理)
├── frontend/       (Vue.js前端)
├── scripts/        (22个脚本)
├── tests/          (30个测试)
└── docs/           (35个文档)
```

---

## 2. 清理范围

### 2.1 P0 - 高优先级（确认无效/冗余）

| # | 路径 | 类型 | 说明 | 风险 |
|---|------|------|------|------|
| 1 | `backup/static_backup/` | 废弃前端 | 旧版静态HTML前端，已被Vue.js替代 | 无 |
| 2 | `agent_core/strategies/react.py` | 废弃代码 | 已标记@deprecated，默认使用LangChainReActStrategy | 低（需保留回退兼容） |
| 3 | `app/plugins/` | 未使用模块 | 插件系统未被main.py或任何路由使用，仅测试引用 | 无 |
| 4 | `prometheus-client` (依赖) | 无效依赖 | 代码库中无任何import | 无 |
| 5 | `frontend/data/math_ai.db` | 重复数据库 | 与`data/math_ai.db`重复 | 无 |

### 2.2 P1 - 中优先级（冗余资源/过时文件）

| # | 路径 | 类型 | 说明 | 风险 |
|---|------|------|------|------|
| 6 | `data/error_book.json.backup.*` | 旧备份 | 日期20260521的备份文件 | 无 |
| 7 | `data/seed_questions.xlsx` | 重复数据 | 与CSV重复，importer使用CSV | 无 |
| 8 | `context_memory_test_report.json` | 临时输出 | 一次性测试输出 | 无 |
| 9 | `tests/*.html` (5个) | 原型文件 | katex_test.html, latex_fix_verification.html, qianwen_ui_light_theme.html, qianwen_ui_prototype.html, render_test.html | 无 |
| 10 | `agent_core/metrics.py` | 未使用模块 | 仅a03_verify.py脚本引用，生产代码无引用 | 低 |

### 2.3 P2 - 低优先级（可选清理）

| # | 路径 | 类型 | 说明 | 风险 |
|---|------|------|------|------|
| 11 | `.agents/` `.claude/` | IDE配置 | AI agent skill定义，非项目代码 | 无 |
| 12 | `docs/` (部分) | 文档 | 部分开发计划文档已过时 | 中（需人工判断） |
| 13 | `DOCKER_GUIDE.md` | 文档 | 部署指南，可合并到README | 无 |
| 14 | `scripts/` (部分) | 脚本 | 一次性开发/调试脚本 | 中（需逐一确认） |

---

## 3. 副作用代码模块分析

### 3.1 模块级副作用

| 模块 | 副作用 | 影响 |
|------|--------|------|
| `agent_core/strategies/react.py` | 模块加载时触发`warnings.warn()`，输出DeprecationWarning | 日志噪音 |
| `agent_core/agent.py` (L37) | `warnings.warn("ReActStrategy 已弃用...")` | 仅当`use_langchain_agent=False`时触发 |

### 3.2 全局状态副作用

| 位置 | 变量 | 影响 |
|------|------|------|
| `tools/__init__.py` | `_registry` (全局单例) | 正常设计模式 |
| `app/plugins/interface.py` | `_plugin_manager` (全局单例) | 未使用，可安全移除 |
| `agent_core/langchain_adapter.py` | `_converter_instance` (全局单例) | 正常设计模式 |

---

## 4. 依赖分析

### 4.1 可移除的依赖

| 依赖 | 原因 | 影响 |
|------|------|------|
| `prometheus-client>=0.19.0` | 代码库中无任何import | 减小安装体积 |

### 4.2 保留但需确认的依赖

| 依赖 | 使用位置 | 备注 |
|------|----------|------|
| `sympy>=1.12` | VisionTool | 符号计算核心 |
| `chromadb>=0.4.22` | vector_store.py | 向量检索核心 |
| `pandas>=2.0.0` | question_importer.py | CSV/Excel导入 |
| `openpyxl>=3.1.0` | question_importer.py | Excel导入 |
| `networkx` (未在requirements.txt) | math_skill_dag.py | 需确认是否漏加 |

---

## 5. 实施步骤

### 阶段一：P0清理（5项）

1. **删除 `backup/` 目录**
   ```bash
   Remove-Item -Recurse -Force "backup/"
   ```

2. **处理 `agent_core/strategies/react.py`**
   - 保留文件（提供回退兼容）
   - 移除模块级 `warnings.warn()` 调用，改为 `logger.debug()`
   - 在 `agent_core/strategies/__init__.py` 中使用延迟导入

3. **删除 `app/plugins/` 目录**
   ```bash
   Remove-Item -Recurse -Force "app/plugins/"
   ```

4. **移除 `prometheus-client` 依赖**
   - 从 `requirements.txt` 中删除 `prometheus-client>=0.19.0`

5. **删除 `frontend/data/math_ai.db`**
   ```bash
   Remove-Item "frontend/data/math_ai.db"
   ```

### 阶段二：P1清理（5项）

6. **删除旧备份文件**
7. **删除 `data/seed_questions.xlsx`**
8. **删除 `context_memory_test_report.json`**
9. **删除 `tests/` 下的HTML原型文件**
10. **处理 `agent_core/metrics.py`** — 保留但标记为deprecated

### 阶段三：P2清理（可选，4项）

11-14. 需要人工决策，本次执行P0+P1为主

---

## 6. 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| 删除backup/后需要回退到旧前端 | 低 | 旧前端已被Vue.js完全替代，且可通过git恢复 |
| 删除react.py影响回退兼容 | 低 | 仅移除副作用警告，保留代码逻辑 |
| 删除plugins/影响测试 | 低 | 仅test_system_integration.py中1处引用，修改测试即可 |
| 删除prometheus-client影响运行时 | 无 | 已验证无任何import |
| 删除frontend/data/math_ai.db | 无 | 前端使用API，不直接读取文件数据库 |

---

## 7. 测试验证计划

### 7.1 单元测试
```bash
cd "c:\Users\HUAWEI\Desktop\math AI assistant"
python -m pytest tests/ -x -v --tb=short
```

### 7.2 集成测试
```bash
python scripts/system_integration_test.py
```

### 7.3 系统功能验证
- 启动服务器: `python main.py`
- 验证 `/api/health` 返回正常
- 验证 `/api/chat` 流式响应正常
- 验证 `/api/recommend/` 推荐接口正常
- 验证前端页面正常加载

### 7.4 回滚方案
所有删除操作均通过git版本控制，可随时恢复：
```bash
git checkout -- <deleted_file>
```