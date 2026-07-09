# 🧹 项目清理指南 — Math AI Assistant（完整版 v2）

> 生成日期：2026-07-03 | 修订：v2（补充遗漏项）
> 目标：清除无用/冗余/废弃内容，为后续重构铺路

---

## 一、可直接删除的内容（确认无用）

### 1.1 重复的 Agent Skill 目录（二选一）

项目同时存在 `.agents/` 和 `.claude/` 两套完全相同的 Skill 定义。

| 目录 | 建议 |
|---|---|
| `.agents/skills/` | **保留**（更通用） |
| `.claude/skills/` | **删除**（与 .agents 完全重复） |

两套目录下的 grill-master、prd-writer、slice-the-spec、spec-to-plan、spec-writer、ui-ux-pro-max 完全一致。

### 1.2 废弃的测试 Skill

| 路径 | 原因 |
|---|---|
| `.agents/skills/test-hello/` | 测试/调试用 Skill，正式项目不需要 |

### 1.3 非核心的 UI 设计 Skill（可选删除）

`ui-ux-pro-max` 包含 **20+ CSV 数据文件、3 个 Python 脚本、18+ 平台模板 JSON**——对于一个数学 AI 助手项目，这个 UI 设计 Skill 的数据文件完全不必要。

| 操作 | 说明 |
|---|---|
| 如前端 UI 已确定 | 整体删除 `ui-ux-pro-max`，可减少数百个文件 |
| 如仍有 UI 迭代需求 | 移入独立 Skill 仓库，不在本项目中维护 |

### 1.4 重复的 frontend 构建产物

| 路径 | 原因 |
|---|---|
| `frontend/frontend/` | 嵌套重复目录，疑似构建配置错误 |
| `frontend/dist/` 与 `frontend/frontend/dist/` | 两套构建产物，仅保留 `frontend/dist/` |

### 1.5 构建缓存和产物

以下应加入 `.gitignore` 并从仓库移除：

- `__pycache__/`（所有层级）
- `.pytest_cache/`
- `.coverage`
- `frontend/node_modules/`（**如已提交到 Git，这是最高优先级问题**）
- `*.pyc`、`*.pyo`
- `data/chroma_db/`（ChromaDB 持久化二进制文件，动辄数百 MB）

---

## 二、高优先级风险项（P0 - 先处理）

### 🚨 P0-1：检查 `frontend/node_modules/` 的 Git 追踪状态

目录列表显示 `frontend/node_modules/` 树完整存在，这可能意味着 node_modules 已被提交到 Git。

**检查命令**：
```bash
git ls-files frontend/node_modules/ | head -20
```

**如果已提交，立即执行**：
```bash
git rm -r --cached frontend/node_modules/
echo "frontend/node_modules/" >> .gitignore
git add .gitignore
git commit -m "chore: remove node_modules from git tracking"
```

### 🚨 P0-2：`data/chroma_db/` 加入 .gitignore

ChromaDB 持久化文件是二进制格式，体积大且不可 diff，绝不应进入版本控制。

```bash
echo "data/chroma_db/" >> .gitignore
git rm -r --cached data/chroma_db/  # 如已追踪
git add .gitignore
```

---

## 三、需要合并/整合的内容

### 3.1 根目录散落的脚本

| 文件 | 建议 |
|---|---|
| `calibrate_questions.py` | 移到 `scripts/` 目录 |
| `error_book.py` | 移到 `scripts/` 或 `data_processing/` |
| `view_questions.py` | 移到 `scripts/` 目录 |

### 3.2 可疑的模块职责重叠

| 模块对 | 需要审查的内容 |
|---|---|
| `agent_core/` vs `engines/` | 两者是否都封装了 Agent 引擎或 LLM 调用？如有重复需合并 |
| `agent_core/` vs `app/services/llm_service.py` | 是否有两套独立的 LLM 配置，导致双重 API Key 消费？ |

### 3.3 `main.py` 的拆分建议

当前 `main.py` 承担了过多职责（路由、Pydantic 模型、Agent 初始化、错误本管理器），建议：

| 内容 | 目标位置 |
|---|---|
| Pydantic 模型（ChatRequest 等） | `app/models/schemas.py` |
| Chat/ErrorBook 路由处理函数 | `app/api/chat.py`、`app/api/errorbook.py` |
| Agent 初始化逻辑 | `app/services/agent_factory.py` |

### 3.4 其他散落文件

| 文件 | 建议 |
|---|---|
| `DOCKER_GUIDE.md` | 移到 `docs/` |

---

## 四、清理执行步骤（修正顺序）

| 优先级 | 步骤 | 预估收益 |
|---|---|---|
| 🔴 P0 | 检查并处理 `node_modules` Git 追踪 | 仓库缩小 100MB+ |
| 🔴 P0 | `data/chroma_db/` 加入 `.gitignore` | 仓库缩小 50-500MB |
| 🔴 P0 | 估算各清理目标目录大小（`du` 命令） | 确认收益 |
| 🟠 P1 | 删除 `.claude/skills/`（重复） | 减少 50% Skill 文件 |
| 🟠 P1 | 删除或移走 `ui-ux-pro-max` | 减少数百个文件 |
| 🟡 P2 | 删除 `test-hello/` | 清理测试残留 |
| 🟡 P2 | 审计 `engines/` 与 `agent_core/` 重复 | 消除核心逻辑冗余 |
| 🟡 P2 | 移动根目录脚本到 `scripts/` | 根目录整洁 |
| 🟢 P3 | 移动 `DOCKER_GUIDE.md` 到 `docs/` | 文档归位 |

### 前置检查

在执行任何删除前：

1. **备份** — `git checkout -b cleanup/remove-junk`
2. **测量** — 用 `Get-ChildItem -Recurse | Measure-Object Length -Sum` 统计各目录大小
3. **检查依赖** — 确认 `Dockerfile`、`docker-compose.yml`、`start.bat` 不依赖被删目录
4. **准备回滚** — 保留原始分支，确认 `git checkout main` 可恢复

---

## 五、PRD 自评（锐评摘要）

| 维度 | 评分 | 说明 |
|---|---|---|
| 问题发现准确度 | ⭐⭐⭐⭐ | 已发现 5 个确认无误的冗余项 |
| 遗漏项（本次补充） | — | node_modules 追踪、ChromaDB 体积、ui-ux-pro-max 冗余、engines 重叠、main.py 拆分、CI/CD 影响 |
| 执行可行性 | ⭐⭐⭐⭐ | 修正后按 P0→P3 顺序执行，风险可控 |

> ⚠️ 以上基于目录扫描结果。实际删除前请用 `grep -r "引用关键词" .` 确认无代码引用。
