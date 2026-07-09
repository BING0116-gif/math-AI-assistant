# A03 记忆持久化运维手册

## 数据库表
- user_skills: 用户技能熟练度（派生表，可从 learning_records 重建）
- learning_records: 原始学习记录（不可删除）

## 备份策略
- learning_records 每天全量备份
- user_skills 可选择性备份（可从主表重建）

## 关键指标
- memory_events_total{status="error"} > 5/min → 检查数据库连接
- memory_buffer_size > 150 → 强制刷新或扩容
- memory_classification_latency P99 > 2s → 切换关键词降级

## 降级开关
- 环境变量 A03_DISABLE_LLM_CLASSIFY=1 → 关闭 LLM 分类
- 环境变量 A03_DISABLE_BUFFER=1 → 关闭事件缓冲