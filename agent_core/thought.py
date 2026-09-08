"""
ThoughtRecorder — 思维过程记录器。

记录 Agent 的 ReAct 思维链过程中的每一步思考、行动、观察，
支持会话级别的历史管理和统计分析。

（原 agents/thought_process.py，迁移到 agent_core/）
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional
from enum import Enum
from dataclasses import dataclass, field, asdict


class ThoughtStepType(str, Enum):
    """思维步骤类型枚举。"""

    THOUGHT = "thought"
    ACTION = "action"
    ACTION_INPUT = "action_input"
    OBSERVATION = "observation"
    FINAL_ANSWER = "final_answer"
    ERROR = "error"
    SYSTEM = "system"


@dataclass
class ThoughtStep:
    """单个思维步骤。"""

    step_id: str
    step_type: ThoughtStepType
    content: str
    tool_name: Optional[str] = None
    tool_result: Optional[str] = None
    elapsed_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["step_type"] = self.step_type.value
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThoughtStep":
        data = dict(data)
        if isinstance(data.get("step_type"), str):
            data["step_type"] = ThoughtStepType(data["step_type"])
        return cls(**data)


@dataclass
class ThoughtProcess:
    """
    完整思维过程记录。

    记录一次完整 ReAct 循环的所有步骤。
    """

    process_id: str
    session_id: str
    user_input: str
    steps: List[ThoughtStep] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    final_answer: Optional[str] = None
    iteration_count: int = 0
    tool_calls: int = 0
    success: bool = True
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_step(self, step: ThoughtStep) -> None:
        """添加思维步骤。"""
        self.steps.append(step)
        if step.step_type == ThoughtStepType.ACTION:
            self.tool_calls += 1
        self.iteration_count = len(
            [s for s in self.steps if s.step_type == ThoughtStepType.THOUGHT]
        )

    def set_final_answer(self, answer: str) -> None:
        """设置最终答案。"""
        self.final_answer = answer
        self.end_time = time.time()

    def set_error(self, error: str) -> None:
        """设置错误信息。"""
        self.error_message = error
        self.success = False
        self.end_time = time.time()

    @property
    def total_elapsed_ms(self) -> float:
        """总耗时（毫秒）。"""
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        result = asdict(self)
        result["steps"] = [s.to_dict() for s in self.steps]
        result["total_elapsed_ms"] = self.total_elapsed_ms
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThoughtProcess":
        """从字典恢复。"""
        steps = [ThoughtStep.from_dict(s) for s in data.get("steps", [])]
        data = dict(data)
        data["steps"] = steps
        if "step_type" in data:
            del data["step_type"]
        return cls(**data)


class ThoughtRecorder:
    """
    思维过程记录器（会话级别）。

    管理会话中的所有思维过程记录，支持：
    1. 创建和管理思维过程
    2. 按会话 ID 查询历史
    3. 统计分析
    4. 自动清理过期记录

    Example:
        recorder = ThoughtRecorder(max_history=100)
        process = recorder.start_process("session_1", "求∫x²dx")
        recorder.add_thought(process, "这是一个积分问题")
        recorder.add_action(process, "math_solver", '{"query": "∫x²dx"}')
        recorder.add_observation(process, "结果是 x³/3 + C")
        recorder.finish(process, "x³/3 + C")
    """

    def __init__(self, max_history: int = 500):
        self._processes: Dict[str, List[ThoughtProcess]] = {}
        self._active_processes: Dict[str, ThoughtProcess] = {}
        self._max_history: int = max_history

    def start_process(
        self, session_id: str, user_input: str, metadata: Optional[Dict[str, Any]] = None
    ) -> ThoughtProcess:
        """
        开始一个新的思维过程。

        Args:
            session_id: 会话 ID。
            user_input: 用户输入。
            metadata: 附加元数据。

        Returns:
            新的 ThoughtProcess 实例。
        """
        process = ThoughtProcess(
            process_id=str(uuid.uuid4())[:8],
            session_id=session_id,
            user_input=user_input,
            metadata=metadata or {},
        )
        self._active_processes[process.process_id] = process
        return process

    def add_thought(
        self,
        process: ThoughtProcess,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录一个思考步骤。"""
        step = ThoughtStep(
            step_id=str(uuid.uuid4())[:8],
            step_type=ThoughtStepType.THOUGHT,
            content=content,
            metadata=metadata or {},
        )
        process.add_step(step)

    def add_action(
        self,
        process: ThoughtProcess,
        tool_name: str,
        action_input: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录一个行动步骤（工具调用）。"""
        step = ThoughtStep(
            step_id=str(uuid.uuid4())[:8],
            step_type=ThoughtStepType.ACTION,
            content=action_input,
            tool_name=tool_name,
            metadata=metadata or {},
        )
        process.add_step(step)

    def add_observation(
        self,
        process: ThoughtProcess,
        content: str,
        elapsed_ms: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录一个观察步骤（工具返回结果）。"""
        step = ThoughtStep(
            step_id=str(uuid.uuid4())[:8],
            step_type=ThoughtStepType.OBSERVATION,
            content=content,
            elapsed_ms=elapsed_ms,
            metadata=metadata or {},
        )
        process.add_step(step)

    def add_error(
        self,
        process: ThoughtProcess,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录一个错误步骤。"""
        step = ThoughtStep(
            step_id=str(uuid.uuid4())[:8],
            step_type=ThoughtStepType.ERROR,
            content=content,
            metadata=metadata or {},
        )
        process.add_step(step)
        process.set_error(content)

    def finish(
        self,
        process: ThoughtProcess,
        final_answer: str,
        success: bool = True,
    ) -> None:
        """
        结束思维过程。

        Args:
            process: 思维过程实例。
            final_answer: 最终答案。
            success: 是否成功。
        """
        process.set_final_answer(final_answer)
        if not success:
            process.success = False

        if process.process_id in self._active_processes:
            del self._active_processes[process.process_id]

        if process.session_id not in self._processes:
            self._processes[process.session_id] = []
        self._processes[process.session_id].append(process)

        if len(self._processes[process.session_id]) > self._max_history:
            self._processes[process.session_id] = self._processes[process.session_id][
                -self._max_history:
            ]

    def get_session_processes(
        self, session_id: str, limit: Optional[int] = None
    ) -> List[ThoughtProcess]:
        """
        获取指定会话的思维过程历史。

        Args:
            session_id: 会话 ID。
            limit: 最多返回条数（最新优先）。

        Returns:
            思维过程列表。
        """
        processes = self._processes.get(session_id, [])
        if limit:
            return processes[-limit:]
        return processes

    def get_stats(self) -> Dict[str, Any]:
        """
        获取全局统计信息。

        Returns:
            统计数据字典。
        """
        all_processes = []
        for procs in self._processes.values():
            all_processes.extend(procs)
        all_processes.extend(self._active_processes.values())

        if not all_processes:
            return {
                "total_processes": 0,
                "total_steps": 0,
                "total_tool_calls": 0,
                "success_rate": 0.0,
                "avg_elapsed_ms": 0.0,
            }

        total = len(all_processes)
        successful = sum(1 for p in all_processes if p.success)
        total_steps = sum(len(p.steps) for p in all_processes)
        total_tool_calls = sum(p.tool_calls for p in all_processes)
        total_elapsed = sum(p.total_elapsed_ms for p in all_processes)

        return {
            "total_processes": total,
            "total_steps": total_steps,
            "total_tool_calls": total_tool_calls,
            "success_rate": successful / total if total > 0 else 0.0,
            "avg_elapsed_ms": total_elapsed / total if total > 0 else 0.0,
            "active_processes": len(self._active_processes),
        }

    def clear_session(self, session_id: str) -> None:
        """清空指定会话的思维过程记录。"""
        if session_id in self._processes:
            del self._processes[session_id]

    def clear_user_sessions(self, user_id: str) -> None:
        """Clear completed and active processes for user-scoped session keys."""
        prefix = f"{user_id}:"
        for session_id in [
            key for key in self._processes if key.startswith(prefix)
        ]:
            del self._processes[session_id]
        for process_id, process in list(self._active_processes.items()):
            if process.session_id.startswith(prefix):
                del self._active_processes[process_id]

    def clear_all(self) -> None:
        """清空所有记录。"""
        self._processes.clear()
        self._active_processes.clear()
