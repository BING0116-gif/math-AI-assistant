"""
PlannedStrategy — 按计划执行策略。

继承 AgentStrategy 基类，按 TaskPlanner 生成的 ExecutionPlan
逐层调度执行子任务，支持并行执行和流式输出。

Attributes:
    PlannedStrategy: 计划执行策略类

Dependencies:
    agent_core.strategies.base.AgentStrategy: 策略抽象基类
    agent_core.task_planner.TaskPlanner: 规划器（用于replan）
    tools.registry.ToolRegistry: 工具注册表
    tools.tool_invoker.ToolInvoker: 工具调用器
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Set

from agent_core.strategies.base import AgentStrategy
from agent_core.thought import ThoughtRecorder, ThoughtProcess
from tools.base_tool import ToolInput
from tools.hybrid_registry import HybridToolRegistry as ToolRegistry
from tools.tool_invoker import ToolInvoker
from agent_core.task_planner import (
    Task,
    ExecutionPlan,
    TaskStatus,
    TaskPlanner,
    PlannerConfig,
)

logger = logging.getLogger(__name__)


class PlannedStrategy(AgentStrategy):
    """
    按计划执行策略 — 继承 AgentStrategy 基类。

    负责：
    1. 接收 ExecutionPlan
    2. 按 DAG 拓扑序逐层调度执行
    3. 支持并行执行无依赖的任务
    4. 流式输出执行进度和最终答案
    5. 失败时触发 replan
    """

    def __init__(
        self,
        llm_chain: Any,
        registry: ToolRegistry,
        task_planner: TaskPlanner,
        thought_recorder: Optional[ThoughtRecorder] = None,
        config: Optional[PlannerConfig] = None,
    ) -> None:
        self._llm_chain = llm_chain
        self._registry = registry
        self._task_planner = task_planner
        self._invoker = ToolInvoker(registry)
        self._recorder = thought_recorder or ThoughtRecorder()
        self._config = config or PlannerConfig()

    async def execute(
        self,
        user_input: str,
        session_id: str,
        context: Dict[str, Any],
        execution_plan: Optional[ExecutionPlan] = None,
    ) -> str:
        chunks: List[str] = []
        async for chunk in self.stream(user_input, session_id, context, execution_plan):
            chunks.append(chunk)
        return "".join(chunks)

    async def stream(
        self,
        user_input: str,
        session_id: str,
        context: Dict[str, Any],
        execution_plan: Optional[ExecutionPlan] = None,
    ) -> AsyncGenerator[str, None]:
        # 保存上下文，供子任务使用（包含 chat_history）
        self._context = context

        if execution_plan is None:
            logger.info(f"PlannedStrategy: 未提供执行计划，自动调用 TaskPlanner 生成...")
            try:
                execution_plan = await self._task_planner.plan(user_input)
                logger.info(
                    f"PlannedStrategy: 执行计划生成成功 "
                    f"(plan_id={execution_plan.plan_id}, "
                    f"tasks={execution_plan.total_tasks})"
                )
            except Exception as e:
                logger.error(f"PlannedStrategy: 执行计划生成失败: {e}，降级到错误提示")
                yield f"**【错误】执行计划生成失败: {e}**\n\n"
                yield "**建议: 请尝试简化问题描述或使用普通模式解题**\n"
                return

        process = self._recorder.start_process(session_id, user_input)
        self._recorder.add_thought(process, f"开始按计划执行: {execution_plan.total_tasks}个任务")

        yield "**📋 解题计划**\n"
        yield execution_plan.summary()
        yield "\n\n---\n\n"

        execution_plan.status = TaskStatus.RUNNING  # PlanStatus
        layers = execution_plan.parallel_groups
        replan_count = 0

        for layer_index, layer_ids in enumerate(layers):
            layer_tasks: List[Task] = []
            for tid in layer_ids:
                task = execution_plan.get_task(tid)
                if task.status in (TaskStatus.COMPLETED, TaskStatus.SKIPPED):
                    continue
                layer_tasks.append(task)

            if not layer_tasks:
                continue

            yield f"**第 {layer_index + 1} 步:** "
            task_names = [t.name for t in layer_tasks]
            yield ", ".join(task_names)
            yield "\n\n"

            if len(layer_tasks) == 1:
                task = layer_tasks[0]
                async for chunk in self._execute_single_task(task, session_id, process, execution_plan):
                    yield chunk
            else:
                if self._config.enable_parallelism:
                    async for chunk in self._execute_parallel_tasks(
                        layer_tasks, session_id, process, execution_plan
                    ):
                        yield chunk
                else:
                    for task in layer_tasks:
                        async for chunk in self._execute_single_task(task, session_id, process, execution_plan):
                            yield chunk

            yield "\n"

            failed_tasks = [t for t in layer_tasks if t.status == TaskStatus.FAILED and not t.can_retry]
            if failed_tasks:
                for failed_task in failed_tasks:
                    if replan_count >= self._config.max_retries_per_task:
                        yield f"\n**【重规划次数已达上限，任务'** {failed_task.name}**' 已跳过】**\n"
                        failed_task.status = TaskStatus.SKIPPED
                        continue

                    yield f"\n**【检测到任务失败，正在重规划...】**\n"
                    try:
                        new_plan = await self._task_planner.replan(
                            failed_task,
                            failed_task.error or "未知错误",
                            execution_plan,
                        )
                        execution_plan = new_plan
                        replan_count += 1
                        yield f"**【重规划完成，继续执行】**\n\n"
                    except Exception as e:
                        logger.error("replan失败: %s", e)
                        yield f"\n**【重规划失败: {e}】**\n"
                        failed_task.status = TaskStatus.SKIPPED

            if self._should_short_circuit(execution_plan):
                yield "\n**【中间结果已足够，跳过剩余步骤】**\n"
                self._skip_remaining(execution_plan)
                break

        yield "\n\n---\n\n**✅ 最终答案**\n\n"
        final_answer = self._aggregate_results(execution_plan)
        yield final_answer

        self._recorder.finish(process, final_answer)

    async def _execute_parallel_tasks(
        self,
        tasks: List[Task],
        session_id: str,
        process: ThoughtProcess,
        plan: ExecutionPlan,
    ) -> AsyncGenerator[str, None]:
        results = await asyncio.gather(*[
            self._run_single_task(t, session_id, process, plan)
            for t in tasks
        ], return_exceptions=True)

        for task, result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.error("并行任务'%s'执行异常: %s", task.id, result)
                task.status = TaskStatus.FAILED
                task.error = str(result)
                yield f"  ❌ {task.name}: {result}\n"
            else:
                yield f"  ✅ {task.name}\n"
                if result:
                    yield f"  > {str(result)[:300]}\n"

    async def _run_single_task(
        self,
        task: Task,
        session_id: str,
        process: ThoughtProcess,
        plan: ExecutionPlan,
    ) -> Optional[str]:
        """执行单个任务（非生成器版本，用于并行）。"""
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()

        self._recorder.add_thought(process, f"执行任务: {task.name}", metadata={"task_id": task.id})

        try:
            if task.tool_name is not None:
                input_data = ToolInput(
                    query=task.parameters.get("query", ""),
                    parameters=task.parameters.get("parameters", {}),
                    context={"session_id": session_id, "task_id": task.id},
                )
                result = await self._invoker.invoke(task.tool_name, input_data)
                if result.success:
                    task.result = result.result
                    task.status = TaskStatus.COMPLETED
                    plan.mark_completed(task.id, result.result)
                    return str(result.result)[:500] if result.result else None
                else:
                    task.error = result.error
                    await self._handle_task_failure(task, result.error or "未知错误", plan, session_id, process)
                    return None
            else:
                prompt = self._build_llm_prompt(task, plan)
                # 从上下文中获取对话历史，确保子任务能访问完整上下文
                chat_history = self._context.get("chat_history", []) if hasattr(self, '_context') and self._context else []
                response = await self._llm_chain.ainvoke({
                    "input": prompt,
                    "chat_history": chat_history,
                })
                llm_result = response.content if hasattr(response, 'content') else str(response)
                task.result = llm_result
                task.status = TaskStatus.COMPLETED
                plan.mark_completed(task.id, llm_result)
                return str(llm_result)[:500]
        except Exception as e:
            logger.error("并行任务'%s'异常: %s", task.id, e)
            task.error = str(e)
            raise
        finally:
            task.completed_at = time.time()

    async def _execute_single_task(
        self,
        task: Task,
        session_id: str,
        process: ThoughtProcess,
        plan: ExecutionPlan,
    ) -> AsyncGenerator[str, None]:
        task.status = TaskStatus.RUNNING
        task.started_at = time.time()

        self._recorder.add_thought(
            process,
            f"执行任务: {task.name}",
            metadata={"task_id": task.id},
        )

        yield ""
        yield f"  ⏳ {task.name}..."

        try:
            if task.tool_name is not None:
                input_data = ToolInput(
                    query=task.parameters.get("query", ""),
                    parameters=task.parameters.get("parameters", {}),
                    context={"session_id": session_id, "task_id": task.id},
                )

                result = await self._invoker.invoke(task.tool_name, input_data)

                if result.success:
                    task.result = result.result
                    task.status = TaskStatus.COMPLETED
                    plan.mark_completed(task.id, result.result)

                    self._recorder.add_action(
                        process, task.tool_name,
                        task.parameters.get("query", ""),
                        metadata={"task_id": task.id},
                    )
                    self._recorder.add_observation(
                        process,
                        str(result.result)[:200] if result.result else "执行成功",
                        elapsed_ms=result.execution_time_ms,
                        metadata={"tool": task.tool_name, "success": True},
                    )

                    yield f" ✅\n"
                    result_preview = str(result.result)[:500] if result.result else ""
                    if result_preview:
                        yield f"  > {result_preview}\n\n"
                else:
                    task.error = result.error
                    await self._handle_task_failure(task, result.error or "未知错误", plan, session_id, process)
                    if task.status == TaskStatus.FAILED:
                        yield f" ❌\n"
                        yield f"  > 错误: {result.error}\n\n"
            else:
                prompt = self._build_llm_prompt(task, plan)
                try:
                    # 从上下文中获取对话历史，确保子任务能访问完整上下文
                    chat_history = self._context.get("chat_history", []) if hasattr(self, '_context') and self._context else []
                    response = await self._llm_chain.ainvoke({
                        "input": prompt,
                        "chat_history": chat_history,
                    })
                    llm_result = response.content if hasattr(response, 'content') else str(response)
                except Exception as llm_error:
                    logger.error("LLM推理任务'%s'失败: %s", task.id, llm_error)
                    llm_result = f"推理过程出现异常: {llm_error}"

                task.result = llm_result
                task.status = TaskStatus.COMPLETED
                plan.mark_completed(task.id, llm_result)
                yield f" ✅\n"
                preview = str(llm_result)[:500] if llm_result else ""
                if preview:
                    yield f"  > {preview}\n\n"

        except Exception as e:
            logger.error("任务'%s'执行异常: %s", task.id, e)
            task.error = str(e)
            await self._handle_task_failure(task, str(e), plan, session_id, process)
            yield f" ❌\n"
            yield f"  > 错误: {e}\n\n"

        finally:
            task.completed_at = time.time()

    async def _handle_task_failure(
        self,
        task: Task,
        error: str,
        plan: ExecutionPlan,
        session_id: str,
        process: ThoughtProcess,
    ) -> None:
        task.retry_count += 1

        if task.can_retry:
            logger.info("任务'%s'重试 %d/%d", task.id, task.retry_count, task.max_retries)
            task.status = TaskStatus.PENDING
            task.error = None
            return

        if task.fallback_tool and self._registry.has_tool(task.fallback_tool):
            logger.info("任务'%s'使用备选工具: %s", task.id, task.fallback_tool)
            task.tool_name = task.fallback_tool
            task.retry_count = 0
            task.status = TaskStatus.PENDING
            task.error = None
            self._recorder.add_thought(
                process,
                f"切换到备选工具: {task.fallback_tool}",
                metadata={"task_id": task.id},
            )
            return

        if task.fallback_to_llm:
            logger.info("任务'%s'降级为LLM推理", task.id)
            task.tool_name = None
            task.retry_count = 0
            task.status = TaskStatus.PENDING
            task.error = None
            self._recorder.add_thought(
                process,
                "降级为LLM直接推理",
                metadata={"task_id": task.id},
            )
            return

        task.status = TaskStatus.FAILED
        plan.mark_failed(task.id, error)
        self._recorder.add_error(
            process,
            f"任务'{task.name}'失败: {error}",
            metadata={"task_id": task.id},
        )

    def _build_llm_prompt(self, task: Task, plan: ExecutionPlan) -> str:
        previous_results = []
        for dep_id in task.dependencies:
            if dep_id in plan.tasks:
                dep_task = plan.tasks[dep_id]
                if dep_task.result:
                    previous_results.append(
                        f"[{dep_task.name}] 结果: {str(dep_task.result)[:1000]}"
                    )

        parts = [
            f"请完成以下解题子任务:",
            f"任务: {task.description}",
        ]
        if previous_results:
            parts.append("\n前置结果:")
            parts.extend(previous_results)
        return "\n".join(parts)

    def _should_short_circuit(self, plan: ExecutionPlan) -> bool:
        completed = sum(
            1 for t in plan.tasks.values()
            if t.status == TaskStatus.COMPLETED
        )
        remaining = sum(
            1 for t in plan.tasks.values()
            if t.status in (TaskStatus.PENDING, TaskStatus.BLOCKED)
        )
        if remaining == 0:
            return False
        return completed >= (remaining + completed) * 0.8

    def _skip_remaining(self, plan: ExecutionPlan) -> None:
        for task in plan.tasks.values():
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.SKIPPED

    def _aggregate_results(self, plan: ExecutionPlan) -> str:
        completed_tasks = [
            t for t in plan.tasks.values()
            if t.status == TaskStatus.COMPLETED and t.result
        ]
        if not completed_tasks:
            return "未能获取有效结果。"

        final_task = None
        for task in plan.tasks.values():
            if task.tool_name is None and task.status == TaskStatus.COMPLETED:
                final_task = task
                break

        if final_task and final_task.result:
            return str(final_task.result)

        lines = ["计算结果汇总:\n"]
        for task in completed_tasks:
            result_str = str(task.result)[:800]
            lines.append(f"**{task.name}**: {result_str}")
        return "\n".join(lines)

    @property
    def thought_recorder(self) -> ThoughtRecorder:
        return self._recorder