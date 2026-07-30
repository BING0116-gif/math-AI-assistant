# Plan: 高等数学课程知识树与知识点依赖图

> Source spec: 当前对话需求；面向现有 Math AI Assistant 仓库的可执行开发方案

## 1. 目标与结果

建设一套可以长期维护的高等数学知识体系，并让它真正参与题库管理、学生掌握度分析和推荐，而不是只生成一张静态思维导图。

完成后系统应提供：

- “课程—章—节—知识点”树状结构；
- 知识点之间的前置、相关、易混淆关系；
- 学生端可交互知识地图；
- 管理员可编辑、校验、发布知识体系；
- 题目与知识点的多对多关联；
- AI 生成知识体系草稿和题目标签，但不能绕过人工发布流程；
- 兼容现有 YAML DAG、推荐系统和已有题库字段；
- 知识体系可版本化、审计和回滚。

## 2. 非目标

首版明确不做：

- 不引入 Neo4j 或其他图数据库；
- 不一次支持所有数学课程；
- 不让 AI 直接修改已发布知识体系；
- 不删除现有 `Question.category`、`sub_categories`、`knowledge_points` 字段；
- 不重写现有推荐、画像、记忆和难度估计系统；
- 不在首版实现多人实时协作编辑；
- 不在首版实现复杂图算法或大规模图计算平台。

## 3. 当前系统基线

当前仓库已经具备：

- PostgreSQL/SQLite + SQLAlchemy + Alembic；
- Vue 3 + Vite + Element Plus；
- Question 题库模型及 CSV/Excel/PDF 导入；
- Qdrant 题目向量检索；
- UserSkill 和学生掌握度数据；
- YAML 形式的 `MathSkillDAG`；
- 根据前置知识计算可学习节点的基础逻辑；
- JWT 用户认证和管理员权限校验。

已知约束：

- 当前 YAML 内容不完整并存在中文编码问题；
- 当前题目知识点以字符串保存，缺少外键和标准 ID；
- 推荐系统直接读取旧 DAG，不能一次性移除；
- 当前前端没有图可视化依赖；
- 知识点数量预计为 100～300，关系数据库足够使用。

## 4. 架构决策

### 4.1 数据存储

- 使用现有关系数据库作为知识体系唯一权威数据源。
- Qdrant只保存题目向量，不保存课程树的权威结构。
- 知识点关系使用普通边表表达，不引入图数据库。
- 所有正式数据必须具有稳定 ID、状态和版本信息。

### 4.2 核心模型

核心模型固定为：

- `Course`：课程；
- `KnowledgeGraphVersion`：知识体系版本；
- `Chapter`：章和节，使用 `parent_id` 形成层级；
- `KnowledgePoint`：知识点；
- `KnowledgePointEdge`：知识点关系；
- `QuestionKnowledgePoint`：题目与知识点关联；
- `KnowledgeGraphChangeLog`：发布与变更审计。

### 4.3 知识点关系方向

所有前置关系统一使用：

```text
source → target
前置知识 → 后续知识
```

首版支持：

- `prerequisite`：前置知识；
- `related`：相关知识；
- `easily_confused`：易混淆知识。

`prerequisite` 必须构成有向无环图；其他关系允许双向，但数据库中仍以两条明确的有向边表达，避免查询歧义。

### 4.4 状态与发布

知识体系版本状态：

- `draft`：编辑中；
- `review`：等待审核；
- `published`：正式使用；
- `archived`：历史版本。

运行时推荐、学生知识地图和题目自动关联默认只读取 `published` 版本。一个课程同一时间只能有一个正式发布版本。

### 4.5 权限

- 已认证学生和教师可以读取已发布知识体系；
- 只有管理员可以创建、修改、删除、导入、审核和发布；
- 草稿默认只对管理员可见；
- 所有管理端写操作必须记录操作者、时间、操作对象和变更摘要；
- AI 服务只能创建草稿或待审核标签，不得直接发布。

### 4.6 API

公共读取路由：

```text
GET /api/knowledge/courses
GET /api/knowledge/courses/{course_id}/tree
GET /api/knowledge/courses/{course_id}/graph
GET /api/knowledge/points/{point_id}
GET /api/knowledge/points/{point_id}/questions
GET /api/knowledge/users/me/map?course_id=...
```

管理员路由：

```text
POST   /api/admin/knowledge/courses
POST   /api/admin/knowledge/courses/{course_id}/versions
POST   /api/admin/knowledge/chapters
PUT    /api/admin/knowledge/chapters/{chapter_id}
DELETE /api/admin/knowledge/chapters/{chapter_id}
POST   /api/admin/knowledge/points
PUT    /api/admin/knowledge/points/{point_id}
DELETE /api/admin/knowledge/points/{point_id}
POST   /api/admin/knowledge/edges
DELETE /api/admin/knowledge/edges/{edge_id}
POST   /api/admin/knowledge/versions/{version_id}/validate
POST   /api/admin/knowledge/versions/{version_id}/publish
POST   /api/admin/knowledge/versions/{version_id}/archive
POST   /api/admin/knowledge/import
POST   /api/admin/knowledge/ai/generate
POST   /api/admin/knowledge/questions/ai-tag
```

### 4.7 前端

- 使用 Vue 3。
- 使用 Vue Flow 显示和编辑节点/连线。
- 使用 Dagre 做从左到右的有向层级布局。
- Element Plus 负责表单、树控件、抽屉、确认框和表格。
- 学生端和管理端复用图数据转换及布局工具，但使用不同交互权限。

### 4.8 兼容策略

- 首版保留现有 YAML DAG；
- 提供 YAML → 数据库的一次性导入工具；
- 提供数据库适配器，保持 `get_prerequisites`、`can_learn`、`get_next_unlockable` 等已有能力；
- 推荐系统迁移到数据库适配器后，才停止运行时读取 YAML；
- 旧题库字符串字段继续写入一段过渡期，关系表成为新的权威关联。

## 5. 数据模型要求

### 5.1 Course

字段至少包含：

- `id`：UUID；
- `code`：稳定、唯一、不可随显示名称变化；
- `name`；
- `description`；
- `subject`；
- `default_version_id`；
- `status`；
- `created_at`、`updated_at`。

### 5.2 KnowledgeGraphVersion

字段至少包含：

- `id`；
- `course_id`；
- `version`；
- `name`；
- `status`；
- `based_on_version_id`；
- `created_by`；
- `published_by`；
- `published_at`；
- `created_at`、`updated_at`。

课程内 `version` 唯一。

### 5.3 Chapter

字段至少包含：

- `id`；
- `course_id`；
- `version_id`；
- `parent_id`；
- `code`；
- `name`；
- `description`；
- `sort_order`；
- `level`；
- `created_at`、`updated_at`。

必须拒绝：

- 章节把自己设为父节点；
- 章节父子关系形成循环；
- 父章节来自其他课程或其他版本。

### 5.4 KnowledgePoint

字段至少包含：

- `id`；
- `course_id`；
- `version_id`；
- `chapter_id`；
- `code`；
- `name`；
- `description`；
- `aliases` JSON；
- `learning_objectives` JSON；
- `common_errors` JSON；
- `difficulty`；
- `importance`；
- `sort_order`；
- `status`；
- `created_at`、`updated_at`。

必须约束：

- 课程和版本内 `code` 唯一；
- `difficulty` 为 1～5；
- `importance` 为 0～1；
- 知识点、章节、版本和课程必须一致。

### 5.5 KnowledgePointEdge

字段至少包含：

- `id`；
- `version_id`；
- `source_id`；
- `target_id`；
- `relation_type`；
- `weight`；
- `description`；
- `created_by`；
- `created_at`。

必须约束：

- source 与 target 不能相同；
- 同版本相同方向、相同类型的边不能重复；
- 两端节点必须属于同一个课程版本；
- 新增 `prerequisite` 前必须执行循环检测。

### 5.6 QuestionKnowledgePoint

字段至少包含：

- `question_id`；
- `knowledge_point_id`；
- `role`：`primary`、`secondary`、`prerequisite`；
- `confidence`；
- `source`：`human`、`ai`、`migration`、`rule`；
- `review_status`：`pending`、`approved`、`rejected`；
- `reviewed_by`；
- `reviewed_at`；
- `created_at`、`updated_at`。

约束：

- 相同题目和知识点只能关联一次；
- 一道题最多有两个 `primary`；
- AI 创建的关联默认 `pending`；
- 正式推荐默认只使用 `approved` 关联。

## 6. 图服务能力

知识图谱服务至少提供：

- 构建课程树；
- 构建指定版本的节点和边；
- 获取一个知识点的直接前置；
- 获取一个知识点的全部祖先前置；
- 获取一个知识点可以解锁的后续节点；
- 判断学生是否满足学习条件；
- 检测 prerequisite 环；
- 检测孤立节点；
- 检测缺少章节的节点；
- 检测重复名称和重复别名；
- 生成版本校验报告；
- 根据 UserSkill 计算学生节点状态。

学生节点状态统一为：

- `mastered`：已掌握；
- `learning`：学习中；
- `weak`：薄弱；
- `available`：前置条件已满足；
- `locked`：前置条件未满足；
- `unseen`：无学习记录但不受前置限制。

掌握度映射阈值必须集中配置，不允许散落在前端和多个服务中。

## 7. API 响应契约

图接口统一返回：

```json
{
  "course": {
    "id": "course-id",
    "code": "advanced-calculus",
    "name": "高等数学"
  },
  "version": {
    "id": "version-id",
    "version": "1.0",
    "status": "published"
  },
  "nodes": [
    {
      "id": "point-id",
      "code": "limit_definition",
      "label": "函数极限定义",
      "chapter_id": "chapter-id",
      "chapter_name": "函数与极限",
      "difficulty": 2,
      "importance": 0.9,
      "status": "available",
      "mastery": 0.65,
      "question_count": 12
    }
  ],
  "edges": [
    {
      "id": "edge-id",
      "source": "source-point-id",
      "target": "target-point-id",
      "relation_type": "prerequisite",
      "weight": 1.0
    }
  ],
  "validation": {
    "is_valid": true,
    "warnings": []
  }
}
```

树接口使用嵌套 `children`，图接口使用扁平 `nodes/edges`，禁止一个接口混合两种结构。

## 8. 阶段计划

### Phase 1：课程树只读纵向切片

#### What to build

建立课程、版本、章节和知识点的最小数据结构，完成迁移、种子数据、课程树读取 API，以及一个只读课程目录页面。

首个演示范围只包含：

- 高等数学课程；
- 函数与极限一章；
- 至少三个小节；
- 至少十个知识点。

这一阶段必须从数据库到 API 再到 Vue 页面完整贯通，不能只建表。

#### Acceptance criteria

- Alembic 可以在空 PostgreSQL 数据库升级到最新版本；
- SQLite 测试显式启用外键；
- 高等数学种子数据可重复执行且不会产生重复记录；
- 课程树接口按 `sort_order` 稳定返回章、节和知识点；
- 未认证请求按现有策略返回 401；
- 学生可读取已发布版本；
- 草稿版本不会出现在学生接口；
- 前端可以展开课程、章、节并点击知识点；
- 知识点详情显示名称、说明、难度和学习目标；
- 后端模型、服务、API 和前端组件均有基础测试。

***

### Phase 2：知识点依赖图纵向切片

#### What to build

增加知识点边、DAG 校验、图读取 API，并在前端以 Vue Flow + Dagre 显示只读依赖图。

第一版只需要可靠支持 `prerequisite`；`related` 和 `easily_confused` 可以读取和显示，但不参与解锁计算。

#### Acceptance criteria

- 可以创建 `A → B → C` 的前置链；
- 拒绝 `C → A` 形成的循环；
- 拒绝自环、重复边和跨版本边；
- 图 API 返回稳定的 `nodes/edges` 契约；
- 前端默认使用从左到右层级布局；
- 支持缩放、平移、适配视图和小地图；
- 点击节点显示直接前置、后续节点和知识点详情；
- 不同关系类型有明确颜色和图例；
- 空图、孤立节点和超长名称均可正常显示；
- 1000 节点、3000 边的校验和序列化设定性能基线，首版目标在普通开发机上 API 响应不超过 1 秒。

***

### Phase 3：学生个性化知识地图

#### What to build

将已发布知识图谱与现有 UserSkill、学习记录、错题和推荐数据连接，让学生看到自己的掌握状态和推荐学习路径。

#### Acceptance criteria

- 学生只能读取自己的掌握状态；
- 管理员读取他人状态必须走明确的管理接口；
- 节点能够显示 mastered、learning、weak、available、locked、unseen；
- locked 节点能够解释“还缺哪些前置知识”；
- 点击知识点可以看到关联题目数量、最近错误和推荐练习入口；
- “推荐下一步”只返回前置条件已满足的节点；
- 一个新用户能够看到基础知识点为可学习状态；
- 用户 A/B 的相同知识图谱具有独立掌握状态；
- 图中状态颜色符合可访问性要求，不能只靠颜色传递状态；
- 掌握度缺失、脏数据和旧 skill code 有明确降级行为。

***

### Phase 4：管理员知识图谱编辑与发布

#### What to build

建立管理员课程树和图谱编辑器，实现增删改、拖动连线、版本校验、审核、发布和归档。

编辑器所有改动写入 draft 版本，不能直接修改 published 版本。编辑已发布版本时必须先复制生成新草稿。

#### Acceptance criteria

- 普通学生访问任何管理写接口返回 403；
- 管理员可以新建章节、知识点和关系；
- 管理员可以在图中通过连线创建 prerequisite；
- 循环边在保存前由前端提示，后端仍必须再次校验；
- 删除章节前必须处理或拒绝其子章节和知识点；
- 删除知识点前展示关联题目和边数量；
- 发布前必须运行完整校验；
- 存在环、跨版本关系或无章节节点时禁止发布；
- 发布操作具有确认步骤和审计日志；
- 发布新版本后旧版本自动归档，但历史题目关联仍可追溯；
- 页面刷新后布局不会丢失；可保存人工位置，未保存时自动布局；
- 管理员可以导出某版本为标准 JSON。

***

### Phase 5：题库关联与旧数据迁移

#### What to build

把题目与知识点改为正式多对多关系，并迁移现有 `category/sub_categories/knowledge_points` 字符串标签。

提供迁移预览、别名匹配、无法匹配报告和人工审核，不允许把无法识别的数据静默归到“其他”。

#### Acceptance criteria

- 题目可以绑定多个知识点并区分 primary/secondary；
- 一道题不能绑定超过两个 primary；
- 题库查询可以按知识点、章节和课程筛选；
- 知识点详情可以分页显示关联题目；
- 推荐和向量元数据使用稳定 knowledge point code；
- 旧字段在过渡期继续同步写入；
- 迁移支持 dry-run；
- 迁移报告包含总数、精确匹配、别名匹配、未匹配和冲突；
- 未匹配记录不会自动发布；
- 迁移重复执行具有幂等性；
- 数据库关联和 Qdrant 元数据更新失败时有补偿或可重试机制；
- 完成对现有 YAML DAG 的数据库导入；
- 推荐系统切换到数据库图适配器后，原有相关测试无回归。

***

### Phase 6：AI 生成、AI 标注与质量治理

#### What to build

让 AI 辅助生成课程知识体系草稿、建议前置关系、给题目打知识点标签，同时建立置信度、审核和评估机制。

AI 输入必须基于确定的课程、版本和候选知识点集合，禁止让模型自由创造后直接写入正式数据。

#### Acceptance criteria

- AI 生成结果必须符合结构化 JSON Schema；
- AI 只能写入 draft 或 pending；
- 每个生成节点包含名称、说明、别名、学习目标、难度和建议关系；
- AI 创建 prerequisite 后仍必须执行 DAG 校验；
- 题目标注结果包含候选知识点、角色、置信度和理由；
- 高置信度标签可以批量审核，但不能绕过管理员确认；
- 支持单题重试和批量任务；
- AI 失败不会留下半完成正式记录；
- 记录模型、提示词版本、输入摘要、输出和耗时；
- 建立不少于 100 道人工金标题目的评估集；
- 主要知识点 Top-1 准确率和 Top-3 召回率必须形成报告；
- 低于验收阈值时不得开启自动批量审批；
- 管理员可以查看、修改、批准和拒绝 AI 建议。

## 9. 高等数学首版内容范围

首版知识体系建议覆盖：

1. 函数与极限；
2. 导数与微分；
3. 微分中值定理与导数应用；
4. 不定积分；
5. 定积分；
6. 定积分应用；
7. 微分方程；
8. 向量代数与空间解析几何；
9. 多元函数微分；
10. 重积分；
11. 曲线积分与曲面积分；
12. 无穷级数。

首版不要求一次把全部内容发布。推荐按章节逐批审核，每批形成可发布版本或同一草稿版本中的审核批次。

## 10. AI 生成数据规范

AI 生成单个知识点至少返回：

```json
{
  "code": "limit_equivalent_infinitesimal",
  "name": "等价无穷小替换",
  "chapter_code": "calculus.limit",
  "description": "利用等价无穷小关系简化极限计算。",
  "aliases": ["等价无穷小", "无穷小替换"],
  "learning_objectives": [
    "识别常用等价无穷小",
    "判断替换条件",
    "完成基本极限计算"
  ],
  "common_errors": [
    "在加减结构中直接替换",
    "忽略自变量趋近条件"
  ],
  "difficulty": 3,
  "importance": 0.9,
  "prerequisite_codes": [
    "limit_definition",
    "infinitesimal"
  ],
  "confidence": 0.86
}
```

后端必须：

- 验证 code 格式和唯一性；
- 将 prerequisite code 解析为当前版本节点；
- 报告不存在或歧义的 code；
- 执行环检测；
- 保存原始 AI 输出用于审计；
- 不把无效节点部分写入正式版本。

## 11. 可视化交互规范

### 11.1 学生端

- 默认只读；
- 支持章节筛选、状态筛选和关键词搜索；
- 点击搜索结果时自动定位节点；
- 节点显示名称、状态和掌握度；
- 边箭头明确表达学习方向；
- 可突出显示“到目标知识点的学习路径”；
- 可隐藏 related/easily_confused，避免图过度拥挤；
- 移动端提供章节树和简化路径视图，不强求完整大图。

### 11.2 管理端

- 支持节点拖动、框选、连线和删除；
- 修改操作进入右侧抽屉；
- 连线前选择关系类型；
- 发布版本默认禁用自由拖动；
- 自动布局不能覆盖已保存人工布局，除非用户明确确认；
- 批量操作必须展示受影响数量；
- 危险删除必须二次确认；
- 校验错误可点击并定位到节点或边。

### 11.3 布局

- prerequisite 图默认使用 Dagre `LR`；
- 按章节分组或着色；
- 保存节点位置时按 `version_id + point_id` 存储；
- 自动布局结果不作为领域数据；
- 图数据和用户掌握数据分开缓存。

## 12. 测试策略

### 12.1 单元测试

覆盖：

- 树构建；
- 父节点循环检测；
- prerequisite 环检测；
- 跨课程/版本校验；
- 状态计算；
- 可学习节点计算；
- 版本发布规则；
- AI JSON Schema；
- 题目关联上限；
- 别名匹配与迁移冲突。

### 12.2 API 测试

覆盖：

- 401、403、404、409、422；
- 学生读取 published；
- 学生不可读取 draft；
- 学生不可写；
- 管理员创建和发布；
- 图响应契约；
- 分页和筛选；
- 跨用户掌握度隔离；
- 并发发布冲突。

### 12.3 数据库测试

覆盖：

- Alembic 空库升级；
- 外键和唯一约束；
- 删除限制；
- 版本唯一性；
- 边重复约束；
- 迁移 dry-run 和幂等；
- PostgreSQL 与 SQLite 的行为差异。

### 12.4 前端测试

覆盖：

- 树加载；
- 图加载；
- 空状态；
- API 失败状态；
- 节点点击和详情；
- 搜索定位；
- 状态图例；
- 管理员建边；
- 循环错误提示；
- 发布确认。

### 12.5 端到端验收

最少验证以下流程：

1. 管理员创建课程草稿；
2. 创建章、节和知识点；
3. 添加前置关系；
4. 尝试添加循环边并被拒绝；
5. 校验并发布；
6. 学生看到知识地图；
7. 学生完成题目后掌握状态变化；
8. 推荐系统给出下一可学知识点；
9. 导入题目并由 AI 生成待审核标签；
10. 管理员批准后题目出现在知识点详情中。

## 13. 性能与缓存

- 课程树和公开图按 `course_id + version_id` 缓存；
- 发布、归档或编辑当前草稿时失效相应缓存；
- 用户图由“公共图 + 用户状态”组合，避免为每个用户复制整张图；
- 图接口支持按章节过滤；
- 数据库为 version、chapter、source、target、knowledge point code 建索引；
- 列表接口必须分页；
- AI 批量任务异步执行并返回 job id；
- 首版不提前引入复杂分布式任务系统，复用现有任务能力或使用数据库任务状态。

## 14. 安全要求

- 所有管理写接口调用 `require_admin_role`；
- 公共 API 不返回草稿、AI 原始提示词或内部审计信息；
- 对名称、说明、别名和 AI 输出做长度限制；
- 防止通过导入构造跨课程外键；
- 批量导入限制文件大小和记录数；
- 禁止客户端指定 `created_by`、`published_by`；
- 发布和删除使用服务端当前用户；
- AI 生成文本展示前按现有前端安全策略进行转义；
- 不执行 AI 生成的 LaTeX、HTML 或脚本。

## 15. 迁移与回滚

迁移顺序：

1. 只新增表，不修改旧 Question 字段；
2. 导入清洗后的 YAML 数据为草稿；
3. 管理员审核并发布数据库版本；
4. 双读验证 YAML 与数据库结果；
5. 推荐系统切换到数据库适配器；
6. 题库字符串标签迁移到关联表；
7. 运行一段兼容期；
8. 停止运行时读取 YAML，但保留文件作为历史输入。

回滚要求：

- 数据库迁移有明确 downgrade；
- 发布新版本不覆盖旧版本；
- 可把课程默认版本切回旧 published/archived 版本；
- Qdrant 元数据更新可重新生成；
- 迁移脚本默认 dry-run；
- 不在迁移脚本中自动删除未匹配标签。

## 16. 可观测性

记录至少包括：

- 图接口响应时间；
- 节点和边数量；
- 校验错误数量；
- 发布次数和发布人；
- AI 生成成功率、耗时和失败类型；
- AI 标签置信度分布；
- 待审核标签数量；
- 迁移匹配率；
- 推荐路径为空的次数；
- 因环或无效关系被拒绝的写操作数量。

日志不得包含完整题库文档、用户 Token 或敏感个人信息。

## 17. Definition of Done

整个功能完成必须同时满足：

- 六个阶段的验收标准全部通过；
- 高等数学至少一个完整、人工审核的 published 版本；
- 至少 100 个知识点和有效 prerequisite 关系；
- 不存在 prerequisite 环；
- 至少 100 道题完成人工确认的知识点关联；
- 学生端可以查看自己的知识地图；
- 管理员可以编辑、校验和发布；
- 推荐系统能够使用数据库图计算下一可学节点；
- 旧功能测试无新增失败；
- PostgreSQL 冷启动迁移通过；
- 前端生产构建通过；
- 提供管理员使用说明、数据字典和迁移报告；
- 不依赖手工修改数据库完成任何正常流程。

## 18. AI 执行约束

后续编码 AI 必须遵守：

1. 开始每个 Phase 前先检查工作树，保留现有用户改动。
2. 一次只实施一个 Phase，不跨阶段大规模重构。
3. 每个 Phase 都必须交付数据库、服务、API、UI 和测试的完整纵向路径。
4. 先写失败测试，再实现核心领域规则。
5. 所有表结构变化必须通过 Alembic。
6. 不使用 `Base.metadata.create_all()` 代替生产迁移。
7. 不删除旧 YAML 或旧 Question 字段，直到兼容阶段完成。
8. 不让 AI 输出直接进入 published 数据。
9. 不跳过权限、跨用户隔离、环检测和迁移测试。
10. 每个 Phase 完成后更新计划状态、记录测试命令和结果。
11. 遇到需要改变本计划中架构决策的情况，先写 ADR 或请求人工确认。
12. 不以“测试难写”为理由 mock 掉被验证的权限、事务、图校验或数据库核心逻辑。

## 19. 推荐执行顺序

交给编码 AI 时使用以下顺序：

```text
Phase 1 → 验收
Phase 2 → 验收
Phase 3 → 验收
Phase 4 → 验收
Phase 5 → 验收
Phase 6 → 验收
全量回归 → PostgreSQL 冷启动 → 前端生产构建 → 发布
```

禁止同时展开所有阶段。优先用第一、第二阶段验证数据库结构、API 契约和前端图技术选择，再继续题库与 AI 集成。
