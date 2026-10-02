# Agent 可观测性运行手册

本文对应 `ops/prometheus.yml` 与 `ops/prometheus-agent-alerts.yml`，用于生产部署、值班排障和指标解释。

## 指标语义

应用的 `/metrics` 是 Prometheus 抓取端点，指标为进程内累计值。窗口速率、错误率和 P95 必须使用 PromQL 计算，不能直接把累计值当作时间窗口数据。

管理员页面 `/admin/agent-metrics` 只用于快速查看当前进程累计快照，不替代 Prometheus/Grafana 的趋势分析。

关键指标：

| 指标 | 含义 | 推荐用途 |
| --- | --- | --- |
| `mathai_agent_runs_total` | Agent 运行次数，按完成/失败区分 | 失败率、吞吐量 |
| `mathai_agent_run_duration_seconds` | Agent 完整运行耗时直方图 | 平均耗时、P95/P99 |
| `mathai_agent_time_to_first_token_seconds` | 首个可见内容到达前的耗时 | 用户感知延迟 |
| `mathai_agent_tool_calls_total` | 工具开始、成功、失败次数 | 工具可靠性 |
| `mathai_agent_tool_duration_seconds` | 工具调用耗时直方图 | 工具超时和慢调用 |
| `mathai_agent_context_trims_total` | 历史上下文触发预算裁剪次数 | 上下文容量是否不足 |

## 告警处理顺序

### Agent 失败率过高

1. 查看 `mathai_agent_runs_total` 的 `failed` 与总运行速率。
2. 对照应用日志中的 `session_id`、`request_id` 和异常类型；日志不得回填题目正文或模型输出。
3. 如果工具失败率同步升高，优先检查 Redis、Qdrant、数据库和外部模型服务。
4. 如果只有模型调用失败，检查模型供应商状态、凭据有效性、限流和超时。
5. 确认恢复后观察至少两个告警评估周期，再关闭事件。

### 工具失败率过高

1. 按工具名称查看 `/metrics`，确认是否为单一工具集中失败。
2. 检查 `on_tool_error` 事件是否持续出现，以及工具耗时是否接近超时上限。
3. 检查工具依赖的权限、数据隔离和服务可用性。
4. 不要通过关闭权限校验或放宽用户隔离来临时止血。

### 首 Token P95 过高

1. 对照 Agent 总耗时和上下文字符数。
2. 检查上下文裁剪比例、长期记忆检索耗时和模型供应商延迟。
3. 优先降低无效上下文和重复请求，不直接删除用户画像或安全约束。
4. 只有在确认供应商延迟异常后，才考虑临时切换模型或降级策略。

### 上下文裁剪比例过高

1. 确认是否为单个会话异常增长，还是全局配置过小。
2. 检查 Token 预算、历史摘要注入和当前问题重复注入情况。
3. 保留当前问题、系统安全约束、用户画像和近期对话；不能无条件扩大上下文窗口。
4. 调整预算后必须重新运行上下文隔离和 Agent 质量回归测试。

## 隐私与合规边界

- Prometheus 标签不得包含用户 ID、会话 ID、题目内容、原始查询、答案或工具参数。
- 管理员接口只返回聚合值，不提供按用户钻取能力。
- 日志中的异常堆栈必须经过脱敏；不得把模型完整输出写入指标标签。
- 过程可视化展示安全阶段摘要和工具状态，不展示模型隐藏思维链。
- 新增指标前必须确认标签集合是有限且稳定的，避免高基数导致 Prometheus 内存增长。

## 发布前检查

```bash
docker compose config --quiet
promtool check rules ops/prometheus-agent-alerts.yml
promtool check config /etc/prometheus/prometheus.yml
python -m pytest tests/test_prometheus_alert_rules.py tests/test_admin_agent_metrics.py -q
```

如果环境没有 `promtool`，必须使用 CI 中的 `prom/prometheus:v3.5.0` 容器执行同等校验，不得跳过规则验证。
