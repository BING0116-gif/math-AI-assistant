# 知微 · 内容审核工具（Internal Content Review Tool）

三阶段 AI Content Pipeline 的正式 internal review tool。仅面向**管理员**，用于完成
**文档导入 → AI 分析 → 人工审核（Import → AI Analysis → Review → Publish）** 的题库闭环。

## 架构

```text
Streamlit Content Review Tool (scripts/content_admin/)
        ↓ HTTP（httpx）
正式 FastAPI /api/admin/content/*（仅 admin；含新增 /api/admin/content/ai-analysis/*）
        ↓
Application Service（ContentImportService / ContentReviewService / ContentAIAnalysisService）
        ↓
PostgreSQL
```

约束（与 AGENTS.md / Step 1.1-D / 1.1-E2-A0 一致）：

- Streamlit **不直接访问数据库**：无 SQLAlchemy、无 SQLite；
- 不提供第二套权限系统：复用正式 `/api/auth/login` + `require_admin_role`；
  student 登录调用审核 API 将得到 403；
- 不在本工具写入任何密码 / token（token 仅保存在 `st.session_state`）；
- **Mock AI 模式**：AI 分析阶段默认使用 MockContentAIProvider（确定性、无需 Key / 网络），
  结果标记 `ai_provider='mock'`，服务端禁止其正式发布（published）。

## 三阶段 Pipeline（单屏优先，避免逐题进入子界面）

1. **① PDF 解析**
   - 上传 PDF、选择 Parser（mineru / quick）、查看批次列表；
   - 展开批次即可查看候选解析结果与来源页，必要时微调题型（fill / fill_candidate 可映射为 supported 题型），并可拒绝候选。
2. **② AI 分析**
   - 展示当前 AI Provider 能力状态（mock / qwen / 真实 Key 是否已配置）；
   - 「开始分析」对批次内所有 supported 候选各建一次 run；
   - 批次统计（总数 / 已分析 / 通过 / 存疑 / 失败 / 待分析）；
   - 候选列表以 Gate / 处置状态呈现，可展开看分析详情，仅在需要时「重新分析」；
   - 底部折叠「覆盖统计 Coverage」（只读）。
3. **③ 审核（同一界面滚动逐题审核）**
   - 顶部汇总「已通过 / 存疑 / 拒绝 / 待审核」计数；
   - 每道题一张卡片（来源 PDF + 题干 / 原答案 ↔ AI 解析 + 验证）同屏展示；
   - 内联处置三件套：**通过 / 存疑 / 拒绝**，并在 Gate=PASS 且 approved 时「生成题目」落正式草稿；
   - 无需逐题进入子页面，靠顶部「筛选」或滚动即可连续审核。
   - 🧪 Mock 提示：Mock 结果禁止正式发布（服务端 `MOCK_AI_RESULT_NOT_PUBLISHABLE`）。

## 路径说明

为何是 `scripts/content_admin/` 而非 `tools/content_admin/`：
仓库根 `tools/` 是 LLM Agent 工具注册表（Python 包，被 agent 导入），
混入 GUI 会破坏该目录语义；`scripts/` 已是仓库运维 / 工具目录，故采用等价路径。

## 安装（依赖隔离）

不要装入 FastAPI 主 runtime。使用独立 venv：

```powershell
python -m venv .venv-content-admin
.venv-content-admin\Scripts\activate
pip install -r requirements-content-admin.txt
```

`requirements-content-admin.txt` 只含 `streamlit` + `httpx`，**不含**
mineru / torch / transformers（MinerU dedicated runtime 独立维护）。

## 启动

```powershell
set ZHIWEI_API_BASE_URL=http://127.0.0.1:8000
streamlit run scripts/content_admin/app.py
```

`ZHIWEI_API_BASE_URL` 也可在登录页手动输入（默认 `http://127.0.0.1:8000`）。
**不得** hardcode 用户机器绝对地址。

先启动正式后端（PostgreSQL 可用、`ADMIN_USERNAME` / `ADMIN_PASSWORD`
已配置或用户已有 admin 角色），再用管理员账号登录本工具。

## 环境变量（后端）

详见仓库根 `.env.example`：当前 `CONTENT_AI_PROVIDER=mock`（免 Key / 网络）。
未来接入真实 Qwen 时，填写 `QWEN_API_KEY` 并将 `CONTENT_AI_PROVIDER=qwen` 即可，
UI / API / DB / workflow 无需改动。

## 文件

- `app.py` — Streamlit 入口（登录门 + 三阶段导航 + AI 分析页）
- `api_client.py` — 轻量 httpx client（含 AI 分析阶段新增端点）
- `validation.py` — 纯逻辑 helpers（标签 / 题型支持 / blocking warnings / checklist / options 文本 / AI 状态徽章）

## 测试

```powershell
python -m pytest scripts/content_admin/tests -q
```

API client / formatting / validation helpers 均有单测；Streamlit 入口做 import smoke。
