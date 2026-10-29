# 数学质量评测下一阶段实施方案

日期：2026-10-20。用途：在新任务窗口执行的交接方案。本文件是开发计划，不是模型质量通过或上线批准。

## 1. 当前基线与边界

- 已有 `evaluations/model_quality/v1` 60 条案例，`scripts/model_quality_eval.py run --mode live` 可运行真实模型；数据集校验已通过。
- 已有 `evaluations/model_quality/v2` 95 条案例，含 11 条多轮案例、版本化门槛和 `run-v2`；当前 `run-v2` 仅支持 mocked，不能把它的结果当成真实模型基线。V2 数据集及门槛校验已通过。
- `evaluations/model_quality/baselines/` 尚无获批准的真实模型 baseline。现有三条上下文压缩长对话对照只测受控追问，见 `CONTEXT_COMPRESSION_EVAL.md`。
- 上下文检查点生成、注入开关默认关闭。先在隔离环境取得质量证据，再讨论启用。
- 当前工作区有用户既有改动及未提交的上下文压缩开发改动；新窗口先运行 `git status --short`，不要覆盖、清理或提交无关文件。

## 2. 目标与验收

目标是比较完整 Agent 在同一模型、同一数据集下的三种配置：A 当前裁剪，B 仅后台生成检查点，C 检查点注入。回答正确性、条件保真、工具行为、安全、延迟、token 和估算费用都要有报告与原始证据。

验收前提：所有案例均为合成或正式授权且脱敏的数据；每例有参考答案、允许变体、关键步骤、严重错误和预期副作用。开放式证明、图片空间关系、中文讲解必须人工复核。安全和用户隔离零容忍；候选相对 A 不得降低数学答案质量。沿用 `evaluations/model_quality/v2/gates.yaml` 的版本化门槛，不临时放宽。

## 3. 实施顺序

### P0：锁定并取得现状基线

1. 记录代码修订、模型/Prompt 版本、参数、数据集哈希及成本单价；先运行 V1、V2 的 validate/audit、mocked 与相关 pytest。
2. 在**一次性 PostgreSQL 评测库**运行 V1 live 全集。严格按 `evaluations/model_quality/README.md` 配置 `EVAL_DATABASE_URL`、预算、超时和单价；不得指向正式业务库。
3. 生成待复核文件，由数学内容负责人逐例复核开放式结果；只有真实评测完整、成本遥测齐全且人工复核完成，才使用现有 `promote` 命令批准 baseline。没有复核人时停在 `needs_human_review`，不可伪造批准。

交付：V1 真实基线报告或明确记录阻塞条件。运行输出放 `artifacts/model-quality/`，不提交密钥、学生数据或原始敏感对话。

### P1：补齐长会话金标

在 V2 `multi_turn` 类别增加约 12 条合成案例，至少覆盖：早期定义域/极限方向、条件更正、两道相似题切换、未验证猜测、长公式、图片引用、压缩失败回退、旧会话无轮次 ID、并发或中断轮次、两个用户同名外部会话、用户要求找回原题、压缩摘要中的提示注入。每例固定预期答案和关键条件，记录是否允许澄清；禁止仅以摘要关键词命中作为最终正确性。

按照现有金标流程改案例版本、manifest/hash，并让另一位复核人审阅案例。不要直接改写旧案例的答案或覆盖已有 baseline。

交付：可校验的新版本数据集、案例审阅记录、确定性 mocked 测试。

### P2：让 V2 可以做真实完整 Agent 对照

现有 V2 `run-v2` 只做 mocked。复用 V1 live runner 的隔离数据库、预算、checkpoint、遥测和失败即停逻辑，为 V2 增加 live 路径；避免另写一套供应商客户端。确保同一 case 在 A/B/C 下运行真实 Agent、Tutor/工具边界，并记录配置指纹和完整回答。不得在评测中读写正式学生数据、Memory 或 Qdrant 生产集合。

先用 2–3 条代表案例做受控小跑，确认完整调用链与报告契约，再运行全集。A/B/C 使用同一模型和参数，执行顺序及重试次数固定；每组都要有独立临时库或显式重置，以免学习状态串扰。

交付：V2 live runner、隔离与预算回归测试、三组可比报告。若完整 Agent 路径暂不能安全隔离，保留 mocked 和受控代理评测，报告标为 incomplete，不声称上线通过。

### P3：质量判断与后续工具决策

运行现有 compare/gates，按题类列出 A/B/C 差异和失败案例。人工复核数学正确性、遗漏条件、错误的工具调用及教学表达。若 C 通过门槛，再只在隔离测试用户开启注入；若失败，按视觉解析、检索、规划、数学推导、上下文组装等边界定位并修复。

仅当失败证据集中在“学生提交一步推导后无法准确判断等价或首个错误步骤”时，才设计逐步解题检查 Tool；它应复用 `math_verify`、`math_solver` 和安全表达式解析，不新增泛用解题 Tool。暂不新增开发 Skill。

## 4. 新窗口第一步

1. 检查 `git status --short` 和本文件，确认保留现有未提交工作。
2. 运行：

   ```powershell
   python -m scripts.model_quality_eval validate --dataset evaluations/model_quality/v1
   python -m scripts.model_quality_eval validate-v2 --dataset evaluations/model_quality/v2
   python -m scripts.model_quality_eval audit-v2 --dataset evaluations/model_quality/v2
   python -m scripts.model_quality_eval validate-gates --gates evaluations/model_quality/v2/gates.yaml
   ```

3. 先实施 P0 的离线与环境预检；只有隔离库、预算和模型配置都满足 runner 要求，才做 live。完成 P0 后再改 V2 案例与 runner。

## 5. 需要用户提供的唯一外部准备

真实模型基线需要一个可销毁的 PostgreSQL 评测库、有效模型配置和明确的评测费用上限。人工批准 baseline 需要能负责数学内容复核的人及其标识。若这些暂缺，先完成所有离线工作，不阻塞 P1 的合成案例设计。
