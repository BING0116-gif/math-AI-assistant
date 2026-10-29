# Phase 4 模型质量评测集

本目录只用于开发、CI 和人工质量复核，不是学生题库，也不会由 FastAPI 或前端公开。

## 事实来源与隔离

- `v1/manifest.yaml`、`v1/cases/` 和 `v1/assets/` 是 V1 金标事实来源。
- 所有案例均为合成内容，不得加入真实学生图片、聊天、账号或生产日志。
- 图片必须使用相对路径并记录 SHA-256；数据集整体通过 `dataset_hash` 防止静默变更。
- 运行原始结果只写入 `artifacts/model-quality/`；批准后的紧凑 baseline 才能进入 `baselines/`。
- 评测目录会被 `.dockerignore` 排除，不进入生产镜像。

## 金标流程

V2.1.1 包含 13 条长会话合成草案，每例 21 个完整问答轮次；版本与数据集哈希已锁定。审阅清单见
`v2/LONG_SESSION_REVIEW.md`。这些案例仍为 `draft`，mocked 满分仅证明管线可运行。
在独立数学复核完成前，不得将其作为获批准的真实模型金标。

`python -m scripts.model_quality_eval preflight-v2 --dataset evaluations/model_quality/v2`
只读取环境配置和案例审阅状态，不连接数据库或调用模型。它检查评测库目标、模型密钥、
显式费用单价及预算，并报告未审阅案例。通过预检也不代表 V2 live runner 已实现。

V2 的 `v2_live.run_v2_with_executor` 是可注入执行器的编排契约：检查独立状态标识、
草案审阅、配置指纹、预算、超时、遥测、用户隔离证据、学生数据副作用和断点续跑。
隔离失败或意外副作用会立即停止并标为 `rejected`；缺少证据会标为 `incomplete`。
终止原因写入检查点；同一运行恢复时不会重试已终止的案例，以免重复产生副作用。
配置 A 要求后台生成和注入都关闭，B 仅开启后台生成，C 两者均开启；三组必须保持
相同模型参数并使用不同隔离状态。
目前尚无完整 Agent 适配器，
因此这个契约不能产出 A/B/C 真实模型报告。
纯数据的 `v2_replay.build_v2_replay_plan` 会为每例生成确定性的用户与会话 ID、
有序历史、图片引用、检索证据需求及工具故障计划；执行器收到该计划后仍需在一次性
数据库和隔离向量集合中真实建立夹具，并证明归属和副作用。
`compare-v2` 对 mocked 报告只返回 `pipeline_pass`，并标记
`model_quality_claim=false`；真实比较必须有获批准的 live baseline 和完成复核的候选报告。
真实比较按版本化门槛检查数学质量、条件覆盖、安全、P95 延迟和平均费用；
缺少基线遥测会返回 `incomplete`，超过门槛会返回 `rejected`。

案例状态依次为 `draft → reviewed → approved`。`gold.author` 与 `gold.reviewer` 必须不同；修改输入、答案、
关键步骤、允许工具或副作用时必须提升 `case_version`，并提升数据集版本、重新计算整体哈希。

当前 V1 中的 author/reviewer 是评测编制过程角色。正式把某次真实模型结果提升为 approved baseline 前，负责人仍需逐例确认
开放式推理、图片关系、Tutor 模式约束和所有自动失败项，并在 promotion 记录中使用可追责的人工 reviewer 标识。

## 执行

```powershell
python -m scripts.model_quality_eval validate --dataset evaluations/model_quality/v1
python -m scripts.model_quality_eval run --dataset evaluations/model_quality/v1 --mode mocked --output artifacts/model-quality/offline
python -m scripts.model_quality_eval run --dataset evaluations/model_quality/v1 --mode mocked --case-id mq-text-001 --output artifacts/model-quality/dry-run
python -m scripts.model_quality_eval run --dataset evaluations/model_quality/v1 --mode live --label candidate --output artifacts/model-quality/live
python -m scripts.model_quality_eval review-template --report artifacts/model-quality/live/results.json --output artifacts/model-quality/live/review.yaml
python -m scripts.model_quality_eval review --report artifacts/model-quality/live/results.json --review-file artifacts/model-quality/live/review.yaml --output artifacts/model-quality/live-reviewed
python -m scripts.model_quality_eval compare --baseline <baseline.json> --candidate <candidate.json> --output artifacts/model-quality/comparison
python -m scripts.model_quality_eval promote --report artifacts/model-quality/live-reviewed/results.json --destination evaluations/model_quality/baselines/<baseline>.json --reviewer <approver> --note "<approval reason>"
```

`validate` 和 `mocked` 不调用模型。`live` 必须显式提供：

- `AI_ENABLED=true`
- `LLM_API_KEY`（应用主模型 DeepSeek 的密钥，评测复用同一模型，不再需要千问 DASHSCOPE_API_KEY）
- `EVAL_DATABASE_URL`，且目标为名称含 `_eval` 或 `_test` 的 PostgreSQL 数据库
- 与评测目标不同的常规 `DATABASE_URL`，或不设置该变量
- 两个显式成本变量 `EVAL_INPUT_COST_PER_MILLION`、`EVAL_OUTPUT_COST_PER_MILLION`
- 正数预算变量 `EVAL_MAX_COST_USD`；Phase 4 封版受控运行使用 `2.00`
- 正整数 token 预算 `EVAL_MAX_TOKENS`
- 每个样例的墙钟超时 `EVAL_TIMEOUT_SECONDS`

Live runner 在任何应用导入、迁移或模型调用前验证数据库目标，然后将现有 Chat/Tutor/Agent 边界指向该一次性数据库。
它不会写正式业务数据库，不创建新的业务表，也不会直接实例化模型供应商客户端。
每个完成的主 attempt 和稳定性重跑会原子写入输出目录的 `checkpoint.json`。每次调用后按显式单价累计成本；
达到预算或成本遥测缺失时立即停止并将报告标为 `incomplete`。进程中断后，使用相同
`--run-id`、数据集和过滤条件重跑即可跳过已完成 attempt；checkpoint 不匹配时命令直接失败，禁止拼接不同运行证据。
token 遥测缺失、token 预算耗尽或单样例超时同样 fail-closed；报告会记录实际 token、成本、P95/平均延迟、超时和预算状态。
自动硬失败或加权分低于 85 的临界案例会固定追加 attempt 2/3；报告给出分数范围、响应变体数和硬失败一致性，
不会从三次结果中挑选最好的一次替换主结果。

GitHub Actions 的定时任务从 repository variable `MODEL_QUALITY_BASELINE` 读取已提交 baseline 路径；成本单价从
同名的两个评测变量读取。缺失时报告保持 `incomplete`，不会以零成本或猜测值通过门禁。

## 评分原则

- 客观答案只由 exact、数值、集合或受限 SymPy 比较器裁决。
- 开放式推理、图片空间关系和中文教学质量保留人工复核。
- 不使用 LLM-as-a-judge。
- 安全、跨用户隔离、客观严重错误和禁止副作用为硬失败。
- token、成本或 Prompt 遥测缺失时，真实报告标记为 `incomplete`，不得猜测填充。
- `schema/case.schema.json` 与 `schema/report.schema.json` 分别锁定案例和版本化报告契约。

### T09 推理缺陷诊断

V1.1 为全部 60 条案例增加 `expected_failure_class`，取值为
`constraint_loss`、`weak_evidence`、`material_contradiction` 或 `none`。三类缺陷分别由
`constraint_coverage`、`evidence_grounding`、`material_consistency` 诊断维度承接，且不改变原有发布加权分。

评分先执行确定性规则。调用方如增加独立 LLM judge 双检，必须把三个布尔结论写入
`CaseExecution.reasoning_judge`，并同时记录 `reasoning_judge_model` 与
`reasoning_judge_prompt_version`；任一 judge 否决都会 fail-closed。LLM judge 不是数学事实来源，
因此开放式推理仍保留人工复核。未提供 judge 的离线或 mocked 运行会明确标记需要人工复核，
不会伪造一次模型复核。

JSON 报告的 `summary.reasoning_defects` 和 Markdown 的“推理缺陷类型 × 模型”章节包含：

- 各缺陷类型的标记数量与全部用例 ID；
- 各缺陷类型的检测失败数量与失败用例 ID；
- 每个模型在各缺陷类型上的用例数、失败数和通过率。

真实报告在所有自动证据齐全后仍会先标记为 `needs_human_review`。人工复核文件只填写报告中
`needs_human_review=true` 的维度，分数采用 0/1/2 Rubric；所有待审项齐全后才转为
`baseline_only`，再由另一条显式 `promote` 命令批准：

```yaml
reviewer: math-reviewer-01
note: 已逐例复核开放式推理、图片关系与中文表达
cases:
  mq-text-001:
    verifiable_reasoning:
      score: 2
      note: 关键步骤完整且不存在实质矛盾
    chinese_latex:
      score: 2
      note: 中文表达清晰，公式可正确渲染
```

复核人与 promotion 批准人均必须使用可追责标识；脚本拒绝内置流程角色占位符。人工分数不会覆盖
确定性数学 oracle、安全、跨用户隔离、工具契约或副作用硬门禁。

`generate_v1.py` 只用于可复现地生成合成 fixture。运行它会重建 V1 案例、图片、Schema 和数据集哈希；修改生成规则时必须先走金标复核。
