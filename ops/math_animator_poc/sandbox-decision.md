# T15 模板型渲染隔离接口决策

> 状态：`ACCEPTED_FOR_TEMPLATE_TRACER`
>
> 日期：2026-09-13
>
> 范围：固定可信模板的受控 Phase 1 tracer；不包含任意 Python

## 决策

Phase 1 tracer 采用“业务编排层 → 独立 job runner → 一次性 renderer”的边界。业务层只提交
版本化、严格校验的 `MathAnimationSpec`；runner 将其编译为仓库内已评审模板的参数，不接收、
拼接或执行用户/模型提供的 Python 源码。

```text
authenticated API / orchestration
  -> durable AnimationJob (owner user_id)
  -> internal authenticated runner request (spec + job id)
  -> one-shot renderer with trusted templates
  -> validated media + metadata
  -> owner-scoped result endpoint
```

## 接口约束

- `MathAnimationSpec` 必须包含 schema version、枚举型 `template_id` 和有上下界的数值/文本参数；
  未知字段、未知模板、非有限数值和超限长度一律拒绝。
- runner 根据固定映射选择模板；禁止将字符串转为模块名、文件路径、表达式或 Python 代码。
- renderer 只接收只读 spec/input mount 与单任务独占 output mount；每个 job 启动新进程/容器，
  达到超时或资源上限后终止，不复用带可写状态的解释器。
- renderer 不连接 PostgreSQL、Redis、Qdrant 或模型服务，不携带这些系统的凭据；产物回传和
  job 状态更新由 runner 完成。
- runner 使用受控容器/Job API，不向 web 或普通 worker 挂载 Docker socket。
- 每个 `AnimationJob` 必须有非空 `user_id`；查询、取消、下载均按后端对象级 ownership 校验。

## 强制运行控制

- 默认禁网、只读根文件系统、非 root、drop all capabilities、`no-new-privileges`。
- 使用默认拒绝型 seccomp，并在部署环境启用 AppArmor/同等级策略；只为实测所需 syscall 开口。
- 每任务限制 CPU、内存、PID、运行时长、输出大小和临时目录；`/tmp` 使用限额 tmpfs。
- 输入挂载只读，输出路径由 runner 创建且不可由 spec 指定；产物仅允许 mp4/gif/png 与受控元数据。
- 验证退出码、媒体格式、分辨率、帧数、时长和大小后才发布；失败最多重试一次，随后回退 T08。
- 镜像按 digest 固定，依赖按 hash 锁定；每次构建扫描并归档 SBOM。

## 生产落点

仓库当前没有满足上述边界的 production runner，现有 `ContentTask` 也缺少学生 `user_id`。
因此本决策关闭“模板 tracer 的隔离接口选型”门禁，但不授权直接复用现有任务模型或修改生产
Compose。Phase 1 实施时必须先审计任务/资产模型，再以 Alembic、API schema、客户端契约和
ownership 回归测试完成跨层变更。

## 任意 Python 的单独门禁

AST/import 白名单不是沙箱。若未来确需执行生成式 Python，必须另立 ADR，采用更强的一次性
隔离（例如 Kubernetes Job 配合 gVisor，或 Firecracker 类 microVM），并完成文件、网络、
syscall、资源耗尽、反射/dunder、`ctypes` 和容器逃逸回归。该路线未获批准且不属于 Phase 1 tracer。

## 否决项

- FastAPI 进程内 `exec`/`eval`/动态 import；
- web/worker 挂载 `/var/run/docker.sock`；
- 让 spec 控制源文件、输出路径、命令行参数或 import；
- 多用户共享可写工作目录；
- 仅靠随机 job id 代替对象级授权。
