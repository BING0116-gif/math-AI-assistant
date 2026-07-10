# Qdrant 向量数据库迁移方案 PRD

**文档版本：** v1.0
**创建日期：** 2026-07-10
**文档状态：** Draft
**负责人：** AI Assistant Team
**相关项目：** Math AI Assistant Project

---

## 1. Summary

本次迁移将数学AI助手项目的向量数据库从 ChromaDB 替换为 Qdrant，以获得**10倍+性能提升**、**更高的召回率稳定性**和**显著的内存效率改进**。迁移将影响 RAG 推荐引擎、题目导入系统等核心模块，采用**全量迁移+增量同步**策略，确保数据完整性和系统稳定性。目标是在不影响现有用户使用体验的前提下，完成技术栈升级。

**目标用户：** 数学AI助手项目的所有用户
**主要成果：** 向量搜索性能提升10倍，内存占用降低100-250MB，召回率提升至97.8%

---

## 2. Problem Statement

### 当前痛点

**性能瓶颈：**
- ChromaDB 延迟较高（P99 延迟 12-18ms），在并发场景下吞吐量不足（RPS 仅 96-141）
- 向量搜索成为 RAG 推荐引擎的性能瓶颈，影响用户体验

**召回率不稳定：**
- ChromaDB 在 ANN 搜索**后**应用 payload 过滤，导致召回率不稳定（96.1%）
- 在难度范围查询场景下，需要过度获取数据再过滤，效率低下

**内存占用高：**
- ChromaDB + DuckDB + Embedding 缓存总计占用 200-350MB 内存
- 不支持量化技术，无法在内存受限环境下高效运行

**技术债务：**
- ChromaDB 功能受限，不支持范围查询（$gte/$lte）在 where 子句中
- 需要后置过滤，代码复杂度高，易出错

### 受影响用户

- **所有使用 RAG 推荐功能的用户**（预计 100% 用户）
- **系统管理员**（需要监控和维护向量数据库）
- **开发团队**（需要维护和优化向量存储代码）

### 证据

- 性能测试数据：[Vector Search Benchmarks](https://qdrant.tech/benchmarks/)
- 用户反馈：推荐响应慢，高并发时系统卡顿
- 系统监控：ChromaDB 在高峰期延迟飙升

---

## 3. Goals and Non-Goals

### Goals

1. **性能提升：** 向量搜索延迟降低 75%（从 12-18ms 降至 4ms），吞吐量提升 10 倍（RPS 从 96 提升至 1238+）
2. **召回率提升：** 召回率从 96.1% 提升至 97.8%，且在过滤场景下保持稳定
3. **内存优化：** 内存占用降低 100-250MB（从 200-350MB 降至 60-120MB）
4. **数据完整性：** 确保所有题目向量数据完整迁移，无数据丢失
5. **零停机：** 迁移过程中不影响用户正常使用，实现无缝切换
6. **向后兼容：** API 接口保持兼容，最小化代码变更

### Non-Goals

1. **不改变业务逻辑：** 不修改 RAG 推荐引擎的核心算法和推荐策略
2. **不改变数据模型：** 不修改 Question 表结构或向量存储的数据格式
3. **不优化 embedding 模型：** 继续使用 all-MiniLM-L6-v2 模型（后续独立优化）
4. **不涉及前端变更：** 本次迁移仅涉及后端向量存储，前端无变更
5. **不实施 Hermes 记忆系统：** 本次仅完成 Qdrant 迁移，记忆系统改造作为后续独立项目

---

## 4. User Stories

### 核心用户故事

1. **作为系统管理员，我希望向量数据库性能更高，以便在高并发场景下系统能稳定运行**
   - 验收：P99 延迟 < 5ms，RPS > 1000
   - 验收：系统资源监控显示内存占用降低 50%+

2. **作为 RAG 推荐用户，我希望推荐响应更快，以便获得更流畅的学习体验**
   - 验收：推荐接口响应时间 < 500ms（含所有步骤）
   - 验收：并发 100 用户时，系统不出现卡顿

3. **作为开发人员，我希望向量存储支持范围查询，以便简化代码逻辑**
   - 验收：难度范围查询（3-5）可以直接在 where 子句中表达
   - 验收：代码中去掉后置过滤逻辑

4. **作为运维人员，我希望迁移过程有完善的回滚机制，以便在出现问题时快速恢复**
   - 验收：提供一键回滚脚本，回滚时间 < 10 分钟
   - 验收：回滚后系统能正常运行，数据无丢失

5. **作为数据管理员，我希望迁移过程中数据有完整性校验，以便确保所有题目向量正确迁移**
   - 验收：迁移后题目数量一致
   - 验收：随机抽样验证向量相似度 > 99%

### 边缘场景和异常流程

6. **作为系统管理员，我希望 Qdrant 服务崩溃时系统能自动降级，以便保证服务可用性**
   - 验收：Qdrant 不可用时，系统降级到纯 SQL 查询
   - 验收：降级状态下仍能提供基础推荐功能（仅基于 SQL）

7. **作为开发人员，我希望迁移过程有详细的日志记录，以便排查问题**
   - 验收：所有关键步骤有日志记录（迁移开始、进度、完成、错误）
   - 验收：错误日志包含堆栈跟踪和上下文信息

8. **作为用户，我希望在迁移期间仍能正常使用系统，以便不中断学习进度**
   - 验收：迁移期间，推荐接口响应时间仍 < 1s
   - 验收：迁移期间，系统无 500 错误或超时

9. **作为数据管理员，我希望有数据迁移验证工具，以便确认迁移成功**
   - 验收：提供数据对比脚本，对比 ChromaDB 和 Qdrant 数据
   - 验收：对比脚本能检测数据不一致并生成报告

10. **作为运维人员，我希望有 Qdrant 监控指标，以便及时发现性能问题**
    - 验收：提供 Qdrant dashboard（或接入现有监控系统）
    - 验收：监控指标包括：QPS、延迟、内存占用、索引状态

---

## 5. Functional Requirements

### 5.1 Qdrant 服务部署

**部署方式：**
- **生产环境：** Docker 部署（推荐）
  - 端口：6333（REST）、6334（gRPC）
  - 持久化存储：`./qdrant_storage`
  - 配置：支持环境变量配置（QDRANT_HOST、QDRANT_PORT）

- **开发环境：** Python 嵌入式模式（可选）
  - 内存模式：`QdrantClient(":memory:")`
  - 本地持久化：`QdrantClient(path="./qdrant_data")`

**Collection 配置：**
- Collection 名称：`math_questions`
- 向量维度：384（all-MiniLM-L6-v2）
- 距离度量：Cosine
- 量化配置：可选（INT8 量化，减少内存占用）

**系统状态转换：**
- 初始化状态：检查 Qdrant 服务可用性
- 就绪状态：Collection 创建成功，可接收查询
- 错误状态：Qdrant 不可用，系统降级到纯 SQL 查询
- 状态转换逻辑：错误 → 重试 → 成功（3 次重试，间隔 5s）

### 5.2 数据迁移策略

**全量迁移（第一阶段）：**
1. 从 ChromaDB 导出所有题目数据（ID、内容、metadata）
2. 使用 SentenceTransformer 生成向量（批量，batch_size=100）
3. 批量导入到 Qdrant（batch_size=100）
4. 记录迁移进度（日志+数据库状态表）

**增量同步（第二阶段）：**
1. 启动双写模式：同时写入 ChromaDB 和 Qdrant
2. 定时任务：每小时同步新增题目（对比 ID 列表）
3. 数据校验：随机抽样验证向量一致性

**数据校验机制：**
- 数量校验：题目总数一致（ChromaDB count == Qdrant count）
- 向量校验：随机抽样 100 条，向量相似度 > 99%
- 元数据校验：随机抽样 100 条，metadata 字段完全一致

### 5.3 API 兼容性

**保持兼容的 API：**
- `get_vector_store()` → 返回 QdrantVectorStoreManager 实例
- `semantic_search(query_vector, n_results, where)` → 保持签名不变
- `hybrid_search(query_vector, query_text, category_filter, difficulty_range, n_results)` → 保持签名不变

**新增的 API：**
- `semantic_search(query_vector, ...)` → **变更**：需要提供 query_vector（不再支持 query_texts）
- 新增方法：`get_collection_stats()` → 返回 Qdrant collection 统计信息

**废弃的 API：**
- ChromaDB 特有的 API（如 `peek()`、`get()`）不再支持

### 5.4 错误处理和降级

**错误处理：**
- Qdrant 服务不可用：自动降级到纯 SQL 查询（不使用向量）
- 向量生成失败：记录错误日志，跳过该题目，继续迁移
- 数据不一致：记录到错误表，提供修复脚本

**降级策略：**
- Qdrant 不可用时：
  - 禁用向量搜索，仅使用 SQL 查询（基于 category、difficulty）
  - 提示用户："当前推荐功能受限，已降级到基础推荐模式"
- 降级状态监控：
  - 每 30 秒检查 Qdrant 可用性
  - 恢复后自动切回正常模式

### 5.5 监控和日志

**监控指标：**
- Qdrant QPS、延迟（P50、P95、P99）
- Collection 状态（points_count、status、optimizer_status）
- 内存占用（Qdrant 进程 + embedding 模型）

**日志记录：**
- 迁移开始：`[Migration] Start migrating ChromaDB to Qdrant`
- 迁移进度：`[Migration] Progress: 1000/5000 questions migrated`
- 迁移完成：`[Migration] Completed: 5000 questions migrated in 120s`
- 错误日志：`[Migration] Error: Failed to migrate question q123, error: ...`

---

## 6. Non-Functional Requirements

### 6.1 性能要求

- **延迟：** P99 延迟 < 5ms（单次向量搜索）
- **吞吐量：** QPS > 1000（单实例）
- **并发：** 支持 100+ 并发用户，无明显性能下降
- **批量导入：** 支持批量导入 5000+ 题目，导入时间 < 5 分钟

### 6.2 可靠性要求

- **可用性：** 99.9% 可用性（允许计划内维护停机）
- **数据持久性：** 100% 数据持久化，无数据丢失
- **降级能力：** Qdrant 不可用时，系统能降级到纯 SQL 查询
- **恢复时间：** 故障恢复时间 < 5 分钟（自动重连）

### 6.3 安全要求

- **访问控制：** Qdrant 服务仅允许内网访问（生产环境）
- **数据隔离：** 不同用户的数据逻辑隔离（通过 metadata.user_id）
- **敏感数据：** 不在向量中存储敏感信息（如用户个人信息）

### 6.4 可维护性要求

- **配置管理：** 所有配置通过环境变量管理（QDRANT_HOST、QDRANT_PORT）
- **日志规范：** 结构化日志，包含时间戳、级别、模块、消息
- **监控集成：** 集成到现有监控系统（Prometheus + Grafana）
- **文档完善：** 提供迁移指南、API 文档、故障排查手册

### 6.5 兼容性要求

- **向后兼容：** API 接口保持兼容，旧代码无需修改
- **环境兼容：** 支持 Python 3.11+，Docker 20.10+
- **数据兼容：** 支持从 ChromaDB 导出的标准格式（CSV + JSON）

---

## 7. Implementation Notes and Architecture

### 7.1 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    Math AI Assistant System                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │  API Layer   │───▶│ RAG Engine   │───▶│ Qdrant Client│  │
│  │              │    │              │    │              │  │
│  │ recommend_   │    │ recommend()  │    │ search()     │  │
│  │ api.py       │    │              │    │ upsert()     │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│                              │                    │          │
│                              │                    │          │
│                              ▼                    ▼          │
│                      ┌──────────────┐    ┌──────────────┐  │
│                      │ PostgreSQL   │    │ Qdrant Server│  │
│                      │ (Questions)  │    │ (Vectors)    │  │
│                      └──────────────┘    └──────────────┘  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 模块和组件

**新增模块：**
- `app/services/vector_store.py` → 替换 ChromaDB 版本，基于 Qdrant
  - `QdrantVectorStoreManager` 类：封装 Qdrant 客户端操作
  - `get_vector_store()` 工厂函数：返回单例实例

**修改模块：**
- `app/services/rag_recommender.py`：
  - 调用 `vector_store.semantic_search()` 时提供 `query_vector`
  - 集成 SentenceTransformer 生成向量
- `app/services/question_importer.py`：
  - 导入题目时调用 `vector_store.add_question()`
- `app/lifespan.py`：
  - 应用启动时初始化 Qdrant 连接
- `app/dependencies.py`：
  - 依赖注入 `get_vector_store()`

**新增依赖：**
- `qdrant-client>=1.7.0`
- `sentence-transformers>=2.2.0`

**删除依赖：**
- `chromadb>=0.4.22`

### 7.3 数据模型

**Qdrant Payload 结构：**
```json
{
  "id": "q123",
  "content": "求函数 f(x) = x^2 + 2x + 1 的导数",
  "category": "导数",
  "difficulty": 3,
  "knowledge_points": ["导数", "二次函数"],
  "estimated_time": 5,
  "question_type": "计算题"
}
```

**PostgreSQL 辅助表（新增）：**
```sql
CREATE TABLE migration_status (
    id SERIAL PRIMARY KEY,
    source_system VARCHAR(50),  -- 'chromadb'
    target_system VARCHAR(50),  -- 'qdrant'
    status VARCHAR(20),         -- 'pending', 'running', 'completed', 'failed'
    total_count INT,
    migrated_count INT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);
```

### 7.4 迁移流程

**准备阶段（Phase 0）：**
1. 部署 Qdrant 服务（Docker）
2. 安装新依赖（qdrant-client, sentence-transformers）
3. 更新代码（vector_store.py, rag_recommender.py）
4. 创建 migration_status 表
5. 备份 ChromaDB 数据（导出为 CSV）

**执行阶段（Phase 1-3）：**

**Phase 1：全量迁移**
```
1. 从 ChromaDB 导出数据 → chroma_export.json
2. 初始化 Qdrant collection
3. 批量生成向量（SentenceTransformer）
4. 批量导入到 Qdrant（batch_size=100）
5. 更新 migration_status 表
```

**Phase 2：双写验证**
```
1. 启用双写模式（同时写 ChromaDB + Qdrant）
2. 定时任务对比数据一致性（每小时）
3. 修复不一致数据
```

**Phase 3：切换和清理**
```
1. 灰度切换：10% 流量 → Qdrant
2. 监控指标，逐步提升至 100%
3. 停止 ChromaDB 服务
4. 删除 ChromaDB 依赖和数据目录
```

**回滚机制：**
- 回滚脚本：`scripts/rollback_qdrant_migration.py`
- 回滚步骤：
  1. 停止 Qdrant 服务
  2. 恢复 ChromaDB 依赖
  3. 恢复旧版 vector_store.py
  4. 重启应用服务
  5. 验证功能正常

---

## 8. Out of Scope

### 明确不在本次迁移范围内

1. **Embedding 模型优化：**
   - 继续使用 all-MiniLM-L6-v2，不替换为更好的模型
   - 后续独立项目优化 embedding 质量

2. **Hermes 记忆系统集成：**
   - 本次仅完成向量数据库迁移
   - 记忆系统改造作为后续独立项目

3. **前端变更：**
   - 前端代码无需修改
   - 用户界面无变化

4. **业务逻辑变更：**
   - 不修改推荐算法和策略
   - 不改变数据模型

5. **性能调优：**
   - 不对 Qdrant 进行深度性能调优（如索引优化）
   - 仅使用默认配置

### 可能的未来迭代

- **Phase 2：** 集成 Hermes 记忆系统，实现个性化教学
- **Phase 3：** 优化 embedding 模型（如使用 bge-large-zh）
- **Phase 4：** Qdrant 集群部署，支持更大规模数据

---

## 9. Risks and Open Questions

### 已知风险

| 风险 | 影响 | 概率 | 应对措施 | 负责人 |
|------|------|------|----------|--------|
| **数据迁移失败** | 高 | 中 | 提供回滚脚本，备份原始数据 | DevOps |
| **性能未达标** | 中 | 低 | 性能测试先行，监控指标验证 | Backend |
| **用户中断** | 高 | 低 | 灰度切换，监控用户反馈 | PM |
| **内存不足** | 中 | 中 | 启用量化技术，监控内存 | DevOps |
| **依赖冲突** | 低 | 低 | 在独立环境测试依赖 | Backend |

### 开放问题

1. **Q1: 是否需要支持 Qdrant 集群模式？**
   - 当前决策：单实例足够，集群作为后续优化
   - 需确认：预估数据规模（当前 5000 题目，未来 50000+）

2. **Q2: 是否需要启用 Qdrant 量化技术？**
   - 当前决策：可选，根据内存监控决定
   - 量化效果：内存减少 32 倍，召回率可能略降

3. **Q3: 迁移时间窗口？**
   - 建议：凌晨 2:00-6:00（用户活跃度最低）
   - 需确认：是否有严格的迁移时间要求

4. **Q4: 是否需要通知用户迁移？**
   - 当前决策：不通知，用户无感知
   - 需确认：是否需要在公告中说明技术升级

5. **Q5: 监控系统集成？**
   - 当前决策：接入现有 Prometheus + Grafana
   - 需确认：现有监控系统能力

### 需要假设的内容

- 假设 ChromaDB 中现有数据量 < 10000 题目（迁移时间 < 10 分钟）
- 假设服务器内存 > 4GB（足够运行 Qdrant + embedding 模型）
- 假设用户并发量 < 200（单实例 Qdrant 可承受）

---

## 10. Success Metrics

### 输入指标

- **迁移准备完成率：** 100%（环境、依赖、脚本）
- **代码覆盖率：** > 80%（新增 QdrantVectorStoreManager）
- **性能测试通过率：** 100%（延迟、吞吐量、并发）

### 输出指标

**性能指标：**
- **延迟降低：** P99 延迟 < 5ms（目标：降低 75%）
- **吞吐量提升：** QPS > 1000（目标：提升 10 倍）
- **召回率：** > 97%（目标：97.8%）

**资源指标：**
- **内存占用：** < 120MB（目标：降低 100-250MB）
- **CPU 使用率：** < 30%（目标：无明显提升）

**质量指标：**
- **数据完整性：** 100% 题目迁移成功，无数据丢失
- **API 兼容性：** 100% API 正常工作，无 breaking change
- **用户满意度：** 无负面反馈（目标：用户无感知）

### 成功标准

**必须达成（P0）：**
1. ✅ 所有题目向量完整迁移到 Qdrant
2. ✅ RAG 推荐功能正常工作（API 响应正常）
3. ✅ 系统稳定性达标（无 500 错误，无数据丢失）
4. ✅ 回滚机制验证成功（能在 10 分钟内回滚）

**应该达成（P1）：**
1. ✅ 性能达标（P99 延迟 < 5ms，QPS > 1000）
2. ✅ 内存占用降低（< 150MB）
3. ✅ 监控指标正常（Qdrant + 应用）

**可以达成（P2）：**
1. ✅ 迁移时间 < 10 分钟
2. ✅ 用户无感知（无投诉或咨询）
3. ✅ 文档完善（迁移指南 + API 文档）

---

## 11. Resource Requirements

### 人力资源

| 角色 | 职责 | 工作量 | 时间段 |
|------|------|--------|--------|
| **Backend Developer** | 开发 Qdrant 集成、迁移脚本、测试 | 5 人天 | Week 1 |
| **DevOps Engineer** | 部署 Qdrant、监控系统、回滚演练 | 2 人天 | Week 1 |
| **QA Engineer** | 功能测试、性能测试、验收测试 | 3 人天 | Week 1-2 |
| **Project Manager** | 项目协调、风险管理、用户沟通 | 1 人天 | Week 1-2 |

**总计：** 11 人天（约 2 周，含缓冲）

### 环境需求

**开发环境：**
- Python 3.11+
- Docker 20.10+
- 内存：4GB+
- 存储：10GB+

**测试环境：**
- Qdrant 单实例（Docker）
- PostgreSQL 12+
- Redis 6+

**生产环境：**
- Qdrant 单实例（Docker，持久化存储）
- 负载均衡器配置（可选）
- 监控系统集成（Prometheus + Grafana）

### 时间需求

**总时长：** 2 周（10 工作日）

- **Week 1：** 开发 + 测试（准备阶段 + Phase 1）
- **Week 2：** 迁移 + 验证（Phase 2-3）

---

## 12. Project Timeline

### 详细时间计划

#### Week 1: 开发和测试阶段

**Day 1-2：准备阶段**
- ✅ 部署 Qdrant 服务（Docker）
- ✅ 安装新依赖（qdrant-client, sentence-transformers）
- ✅ 创建 migration_status 表
- ✅ 备份 ChromaDB 数据

**Day 3-4：开发阶段**
- ✅ 开发 QdrantVectorStoreManager
- ✅ 修改 RAG 推荐引擎（集成向量生成）
- ✅ 开发迁移脚本（全量迁移 + 数据校验）
- ✅ 开发回滚脚本

**Day 5：测试阶段**
- ✅ 单元测试（QdrantVectorStoreManager）
- ✅ 集成测试（RAG 推荐引擎）
- ✅ 性能测试（延迟、吞吐量、并发）
- ✅ 回滚演练（验证回滚脚本）

#### Week 2: 迁移和验证阶段

**Day 6：迁移准备**
- ✅ 生产环境部署 Qdrant
- ✅ 配置监控系统（Qdrant dashboard）
- ✅ 通知相关人员（迁移时间窗口）

**Day 7：Phase 1 - 全量迁移**
- ✅ 凌晨 2:00 开始迁移
- ✅ 从 ChromaDB 导出数据
- ✅ 批量生成向量并导入 Qdrant
- ✅ 数据校验（数量、向量、metadata）
- ✅ 更新 migration_status 表

**Day 8：Phase 2 - 双写验证**
- ✅ 启用双写模式（ChromaDB + Qdrant）
- ✅ 定时任务对比数据一致性（每小时）
- ✅ 修复不一致数据
- ✅ 监控系统指标

**Day 9：Phase 3 - 切换和清理**
- ✅ 灰度切换：10% 流量 → Qdrant
- ✅ 监控用户反馈和系统指标
- ✅ 逐步提升流量：10% → 50% → 100%
- ✅ 停止 ChromaDB 服务
- ✅ 删除 ChromaDB 依赖和数据目录

**Day 10：验收和总结**
- ✅ 完整验收测试（功能、性能、稳定性）
- ✅ 文档完善（迁移指南、API 文档）
- ✅ 项目总结会议
- ✅ 关闭 migration_status 表

### 里程碑

- **M1（Day 2）：** 准备阶段完成（环境 + 备份）
- **M2（Day 5）：** 开发和测试完成（代码 + 测试）
- **M3（Day 7）：** 全量迁移完成（数据迁移成功）
- **M4（Day 9）：** 切换完成（Qdrant 上线）
- **M5（Day 10）：** 项目验收完成（成功标准达成）

---

## 13. Appendices

### 附录 A：迁移脚本示例

```python
# scripts/migrate_chromadb_to_qdrant.py

import asyncio
from app.services.vector_store import get_vector_store
from sentence_transformers import SentenceTransformer

async def migrate_all_questions():
    """从 ChromaDB 迁移所有题目到 Qdrant"""

    # 1. 初始化 Qdrant
    qdrant_store = await get_vector_store()

    # 2. 从 ChromaDB 导出数据（假设已有导出函数）
    chroma_data = export_from_chromadb()  # 返回 [(id, content, metadata)]

    # 3. 初始化 embedding 模型
    embedder = SentenceTransformer('all-MiniLM-L6-v2')

    # 4. 批量迁移
    batch_size = 100
    for i in range(0, len(chroma_data), batch_size):
        batch = chroma_data[i:i + batch_size]

        batch_data = []
        for question_id, content, metadata in batch:
            vector = embedder.encode(content).tolist()
            batch_data.append((question_id, content, metadata, vector))

        success = await qdrant_store.add_questions_batch(batch_data)
        print(f"[Migration] Progress: {i + len(batch)}/{len(chroma_data)}")

    print(f"[Migration] Completed: {len(chroma_data)} questions migrated")

if __name__ == "__main__":
    asyncio.run(migrate_all_questions())
```

### 附录 B：回滚脚本示例

```python
# scripts/rollback_qdrant_migration.py

import subprocess
import sys

def rollback_migration():
    """回滚到 ChromaDB"""

    print("[Rollback] Starting rollback to ChromaDB...")

    # 1. 停止 Qdrant 服务
    subprocess.run(["docker", "stop", "qdrant"])
    print("[Rollback] Qdrant stopped")

    # 2. 恢复 ChromaDB 依赖
    subprocess.run([sys.executable, "-m", "pip", "install", "chromadb>=0.4.22"])
    print("[Rollback] ChromaDB installed")

    # 3. 恢复旧版 vector_store.py
    subprocess.run(["git", "checkout", "app/services/vector_store.py"])
    print("[Rollback] vector_store.py restored")

    # 4. 重启应用服务
    subprocess.run(["docker", "restart", "math-ai-assistant"])
    print("[Rollback] Application restarted")

    print("[Rollback] Rollback completed successfully")

if __name__ == "__main__":
    rollback_migration()
```

### 附录 C：监控配置示例

```yaml
# prometheus/qdrant_rules.yml

groups:
  - name: qdrant_alerts
    rules:
      - alert: QdrantHighLatency
        expr: qdrant_search_latency_p99 > 0.01
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Qdrant search latency too high"

      - alert: QdrantDown
        expr: up{job="qdrant"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Qdrant service is down"
```

---

## 14. Approval and Sign-off

| 角色 | 姓名 | 签名 | 日期 |
|------|------|------|------|
| **Product Manager** | | | |
| **Tech Lead** | | | |
| **DevOps Lead** | | | |
| **QA Lead** | | | |

---

**文档结束**