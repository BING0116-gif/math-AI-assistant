# 知微 Math AI 前端重构四阶段总索引

> 版本：1.0  
> 日期：2026-08-04  
> 上位方案：`plans/math-ai-assistant-development-roadmap.md`  
> 设计依据：`docs/UI_UX_MASTER_PLAN.md`

## 1. 总目标

在不推倒现有 Vue 3 前端、不阻塞高等数学 MVP 的前提下，将当前“通用 AI 聊天工具”逐步重构为“大学数学学习工作台”，最终跑通：

> 今日任务 → 知识点学习 → 练习与反馈 → 掌握度变化 → 错题复盘 → 下一步推荐

四个阶段必须顺序执行。每个阶段独立验收，未达到退出条件不得进入下一阶段。

## 2. 四阶段文件

1. [Phase 1：可信基线与设计冻结](./phase-1-baseline-and-design-freeze.md)
2. [Phase 2：设计系统与应用外壳](./phase-2-design-system-and-app-shell.md)
3. [Phase 3：核心学习闭环](./phase-3-core-learning-loop.md)
4. [Phase 4：其余页面与产品化](./phase-4-productization-and-remaining-pages.md)

## 3. 总体时间建议

| 阶段 | 建议周期 | 核心结果 |
|---|---:|---|
| Phase 1 | 3～5 个工作日 | 重构前基线可信、范围冻结、契约明确 |
| Phase 2 | 5～8 个工作日 | 新设计系统和 AppShell 承载现有功能 |
| Phase 3 | 10～15 个工作日 | 一条真实的高数学习闭环端到端可用 |
| Phase 4 | 8～12 个工作日 | 剩余页面统一、移动端与产品质量达标 |

单人开发按 6～9 周估算；2～3 人团队按 4～6 周估算。排期以验收结果为准，不以日历日期强行切换阶段。

## 4. 跨阶段架构决策

- **前端技术栈不更换**：继续使用 Vue 3、Vite、Pinia、Vue Router、Element Plus、SCSS。
- **渐进重构**：新外壳先包裹旧页面，再逐页替换；禁止一次性重写全部页面。
- **路由稳定**：保留 `/`、`/chat/:chatId?`、`/knowledge`、`/knowledge/points/:pointId/learn`、`/error-book/:errorId?`。
- **首页语义改变**：`/` 从功能陈列首页变为“今日学习工作台”，但 URL 不变。
- **业务数据权威源不变**：课程、题目、作答、错题和掌握度均以 PostgreSQL 为权威源；Pinia/localStorage 只保存 UI 状态或允许降级的本地草稿。
- **接口先适配后替换**：前端通过 API/service 层读取后端，页面组件不得自行拼接授权头、解析 SSE 或操作多个存储源。
- **统一学习上下文**：前端共享 `courseId`、`knowledgePointId`、`questionId`、`sessionId`、`learningRecordId` 等稳定标识。
- **设计方向固定**：Editorial Intelligence + Cognitive Canvas；浅色用于阅读与学习，深色用于知识关系画布。
- **可访问性是完成标准**：键盘、焦点、对比度、非颜色状态、44px 点击区和 reduced motion 不是最后补丁。
- **测试跟随切片**：每一阶段同时交付组件测试、API 契约测试或 E2E，不允许最后统一补测试。

## 5. 全局设计基线

### 视觉语义

| 语义 | 建议色 | 使用范围 |
|---|---:|---|
| 页面画布 | `#F4F2EC` | 今日、对话、学习、错题页面背景 |
| 内容表面 | `#FBFAF6` | 卡片、输入区、学习模块 |
| 主文字 | `#20231F` | 标题、正文、主按钮 |
| 次文字 | `#666B63` | 说明、元数据 |
| Agent | `#2D6B5F` | AI 行为、主要进度、主操作 |
| 知识 | `#6E63A6` | 概念、公式、知识关系 |
| 复习 | `#B8743B` | 待复习、提醒、错题 |
| 危险 | `#B94A48` | 删除与不可逆操作 |
| 图谱画布 | `#0B1110` | 2D/3D 知识关系视图 |

颜色必须通过语义令牌使用，不允许页面继续新增零散十六进制颜色。

### 交互基线

- 每个页面最多一个主 CTA；
- 所有异步按钮有 loading、disabled、success/error 状态；
- 超过 300ms 的等待必须显示反馈；
- 图标统一为 SVG 图标库，禁止 emoji 作为结构图标；
- 动效 150～300ms，复杂镜头不超过 420ms；
- 支持 `prefers-reduced-motion`；
- 桌面、平板、手机按 375 / 768 / 1024 / 1440px 验证；
- 正文默认 15～16px、行高 1.6～1.75、单行阅读宽度不超过约 75 个字符。

## 6. 分支与交付建议

每阶段建议单独分支或至少独立 PR：

```text
codex/frontend-phase-1-baseline
codex/frontend-phase-2-shell
codex/frontend-phase-3-learning-loop
codex/frontend-phase-4-productization
```

阶段内部按文档的“推荐切片/PR 顺序”提交。不要把四个阶段放进同一个超大 PR。

## 7. 总 Definition of Done

- 全新用户可在生产构建中完成核心学习闭环；
- 现有聊天、知识目录、学习页和错题本无功能回归；
- 前端不存在两套相互冲突的主题变量；
- 核心页面在 375px 与 1440px 均可操作；
- 不用颜色单独表达掌握/错误/锁定状态；
- 前端构建、组件测试、核心 E2E 和后端关键测试在 CI 通过；
- 关键失败有恢复动作，刷新不会静默丢失当前学习状态；
- 至少完成一次 5 名学生的可用性测试并形成问题清单。

