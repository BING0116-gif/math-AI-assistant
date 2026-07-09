# 数学AI助手 - 项目文档

## 文档目录

### 架构设计 (`architecture/`)
系统架构设计、技术选型、架构优化方案等文档。

| 文档 | 说明 |
|------|------|
| [AI_Agent 实现方案](architecture/AI_Agent%20实现方案.md) | AI Agent 核心实现方案 |
| [AI_Agent_技术优化方案_v2](architecture/AI_Agent_技术优化方案_v2.md) | Agent 技术优化方案 v2 |
| [Agent_架构统一重构方案](architecture/Agent_架构统一重构方案.md) | Agent 架构统一重构设计 |
| [Agent系统优化改进方案_v3](architecture/Agent系统优化改进方案_v3.md) | Agent 系统优化改进 v3 |
| [技术架构全面评估与优化方案](architecture/技术架构全面评估与优化方案.md) | 整体技术架构评估 |
| [系统架构优化与LangChain能力增强](architecture/系统架构优化与LangChain能力增强开发文档.md) | LangChain 集成架构优化 |
| [项目重构规划与团队推进方案](architecture/项目重构规划与团队推进方案.md) | 项目重构整体规划 |
| [多轮对话上下文记忆容量分析](architecture/多轮对话上下文记忆容量分析与实现难度报告_128K_vs_512K.md) | 128K vs 512K 上下文容量分析 |

### 开发文档 (`development/`)
技术开发文档、功能实现方案、运行手册等。

| 文档 | 说明 |
|------|------|
| [A03-runbook](development/A03-runbook.md) | A03 自动记忆持久化运行手册 |
| [A03-自动记忆持久化机制-开发文档](development/A03-自动记忆持久化机制-开发文档.md) | 记忆持久化开发文档 |
| [A03-自动记忆持久化机制-优化方案v2](development/A03-自动记忆持久化机制-优化方案v2.md) | 记忆持久化优化方案 |
| [DOCKER_GUIDE](development/DOCKER_GUIDE.md) | Docker 开发环境指南 |
| [LangChain核心模块迁移开发方案](development/LangChain核心模块迁移开发方案_v1.md) | LangChain 迁移方案 |
| [ToolRegistry_技术开发文档](development/ToolRegistry_技术开发文档.md) | 工具注册中心开发文档 |
| [VisionTool_技术文档](development/VisionTool_技术文档.md) | 视觉识别工具技术文档 |
| [VisionTool_修复测试报告](development/VisionTool_修复测试报告.md) | 视觉工具修复测试 |
| [Vue前端界面重构技术开发文档](development/Vue前端界面重构技术开发文档.md) | 前端重构技术文档 |
| [LLM复杂度分类路由](development/LLM复杂度分类路由_技术开发文档.md) | LLM 复杂度分类路由 |
| [LaTeX渲染功能技术评估](development/LaTeX渲染功能技术评估与优化报告.md) | LaTeX 渲染评估报告 |
| [任务规划器技术开发文档](development/任务规划器技术开发文档.md) | 任务规划器开发文档 |
| [前端界面开发文档](development/前端界面开发文档.md) | 前端界面开发文档 |
| [回答质量优化方案_v1](development/回答质量优化方案_v1.md) | 回答质量优化方案 |
| [安全加固报告](development/安全加固报告.md) | 安全加固实施报告 |
| [数据库_记忆系统_用户画像](development/数据库_记忆系统_用户画像_技术文档.md) | 数据库与记忆系统文档 |
| [第二阶段_交互功能增强](development/第二阶段_交互功能增强实施方案.md) | 第二阶段功能增强方案 |
| [错题本功能优化方案](development/错题本功能优化方案.md) | 错题本优化方案 |
| [错题本功能优化需求文档](development/错题本功能优化需求文档.md) | 错题本需求文档 |
| [问题分析与修复报告](development/问题分析与修复报告.md) | 问题分析修复报告 |
| [homepage_refactoring_technical_plan](development/homepage_refactoring_technical_plan.md) | 首页重构技术方案 |

### API 文档 (`api/`)
API 接口设计、推荐系统等相关文档。

| 文档 | 说明 |
|------|------|
| [RAG_LLM智能推荐系统开发文档](api/RAG_LLM智能推荐系统开发文档.md) | RAG+LLM 智能推荐系统 |

> 在线 API 文档：启动服务后访问 http://localhost:8000/docs (Swagger UI) 或 http://localhost:8000/redoc (ReDoc)

### PRD 文档 (`prd/`)
产品需求文档、项目规划等。

| 文档 | 说明 |
|------|------|
| [PRD](prd/PRD.md) | 项目产品需求文档 |
| [CLEANUP_GUIDE](prd/CLEANUP_GUIDE.md) | 代码清理指南 |
| [代码清理PRD](prd/代码清理PRD.md) | 代码清理 PRD |
| [项目展示文档](prd/项目展示文档.md) | 项目展示说明 |
| [三人小组开发任务分配方案](prd/三人小组开发任务分配方案.md) | 团队任务分配 |

## 快速导航

- **新手入门**：阅读 [PRD](prd/PRD.md) 了解项目背景，查看 [前端界面开发文档](development/前端界面开发文档.md) 开始开发
- **架构理解**：从 [技术架构全面评估与优化方案](architecture/技术架构全面评估与优化方案.md) 开始
- **部署运维**：参考 [DOCKER_GUIDE](development/DOCKER_GUIDE.md) 和 [A03-runbook](development/A03-runbook.md)
- **API 接口**：启动服务后访问 http://localhost:8000/docs