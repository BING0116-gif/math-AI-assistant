# 前端重构 Phase 2：实施报告

> 范围：`plans/frontend-refactor/phase-2-design-system-and-app-shell.md`
> 记录日期：2026-08-05

## 已完成内容

- 在 `frontend/src/styles/themes.scss` 中用语义化 CSS 令牌替换重复的运行时主题定义。
- 在 `frontend/src/styles/variables.scss` 中只保留布局相关的 SCSS 编译期常量。
- 增加浅色阅读/工作台表面和局部深色认知画布表面。
- 在不改变页面路由和业务 API 的前提下，将现有 `LayoutDefault` 使用方迁移到新的 `AppShell`。
- 增加桌面导航、平板收窄导航轨、移动端底部导航、移动端导航抽屉、Skip Link、路由激活态和主内容焦点管理。
- 确保可见的主题切换入口只由 AppShell 持有。
- 增加可复用的 `AppButton`、`IconButton`、`StatusBadge` 和 `FeedbackState` 基础组件。
- 增加内部 `/__design-system` 状态展示页，覆盖按钮、输入框、状态标签、反馈状态、浅色表面和图谱表面。
- 将原生 prompt/confirm 替换为 Element Plus 对话框 API。
- 清理已触及的导航、聊天和错题本 UI 中的结构性 emoji 标签。
- 增加 Vitest 配置和基础组件测试。

## 验证结果

| 检查项 | 结果 |
|---|---|
| `npm.cmd run build` | 通过；转换 1796 个模块，耗时 7.01 秒 |
| Phase 2 路由编译 | 通过，包含在生产构建中 |
| Phase 2 冒烟脚本 | 等待浏览器运行时；现有路由保持不变 |
| `npm.cmd test` | 通过；3 个测试文件、4 个测试 |

测试可以使用以下命令复现：

```powershell
cd frontend
npm.cmd install
npm.cmd test
```

现有 Sass legacy API 警告和大 chunk 警告仍作为技术债记录。这些问题不阻塞本次外壳迁移，并有意延后处理。

## 明确保留的非目标

- 没有新增学习记录或作答提交 API。
- 没有重写 Chat Agent 或 SSE 协议。
- 没有实现正式知识图谱编辑器。
- 没有迁移到 React、Tailwind 或其他组件库。
- 没有重写页面内部业务内容。
