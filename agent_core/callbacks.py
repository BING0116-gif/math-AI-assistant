"""
自定义CallbackHandler — 用于记录LangChain Agent的思维链过程。

替代原有的ThoughtRecorder，通过LangChain回调机制捕获：
- LLM推理过程 (on_llm_start/end)
- 工具调用详情 (on_tool_start/end)
- 最终输出结果 (on_chain_end)

提供与原有ThoughtRecorder接口兼容的API，便于平滑过渡。
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from agent_core.thought import ThoughtRecorder, ThoughtProcess, ThoughtStep, ThoughtStepType

logger = logging.getLogger(__name__)


@dataclass
class LCThoughtStep:
    """单个思维步骤（LangChain回调版本）。"""

    step_id: str
    step_type: str
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'step_id': self.step_id,
            'step_type': self.step_type,
            'content': self.content,
            'timestamp': self.timestamp,
            'metadata': self.metadata,
        }


@dataclass
class LCThoughtProcess:
    """完整的思维过程记录（LangChain回调版本）。"""

    process_id: str
    session_id: str
    user_input: str
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    steps: List[LCThoughtStep] = field(default_factory=list)
    status: str = "running"

    @property
    def elapsed_ms(self) -> float:
        end = self.end_time or time.time()
        return (end - self.start_time) * 1000

    @property
    def iteration_count(self) -> int:
        return sum(1 for s in self.steps if s.step_type == "action")

    def add_step(self, step_type: str, content: str, **metadata):
        step = LCThoughtStep(
            step_id=f"step_{len(self.steps):03d}",
            step_type=step_type,
            content=content,
            metadata=metadata,
        )
        self.steps.append(step)
        return step

    def finish(self, final_answer: str = ""):
        self.end_time = time.time()
        self.status = "completed"
        if final_answer:
            self.add_step("final_answer", final_answer)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'process_id': self.process_id,
            'session_id': self.session_id,
            'user_input': self.user_input[:100],
            'start_time': self.start_time,
            'end_time': self.end_time,
            'elapsed_ms': round(self.elapsed_ms, 1),
            'status': self.status,
            'iteration_count': self.iteration_count,
            'steps': [s.to_dict() for s in self.steps],
        }


class ThoughtRecordingCallbackHandler(BaseCallbackHandler):
    """
    思维链记录回调处理器。

    监听LangChain Agent的所有关键事件，构建完整的思维链记录。
    同时向后兼容原有的ThoughtRecorder接口，自动同步记录。
    """

    def __init__(
        self,
        session_id: str = "default",
        thought_recorder: Optional[ThoughtRecorder] = None,
    ):
        super().__init__()
        self.session_id = session_id
        self._current_process: Optional[LCThoughtProcess] = None
        self._history: List[LCThoughtProcess] = []
        self._max_history: int = 100

        self._thought_recorder = thought_recorder
        self._legacy_process: Optional[ThoughtProcess] = None

        self.raise_exception = False

    @property
    def current_process(self) -> Optional[LCThoughtProcess]:
        return self._current_process

    def start_process(self, user_input: str) -> LCThoughtProcess:
        self._current_process = LCThoughtProcess(
            process_id=f"proc_{uuid.uuid4().hex[:12]}",
            session_id=self.session_id,
            user_input=user_input,
        )
        logger.debug(f"开始记录思维过程: {self._current_process.process_id}")

        if self._thought_recorder:
            self._legacy_process = self._thought_recorder.start_process(
                self.session_id, user_input
            )

        return self._current_process

    def finish_process(self, final_answer: str = "") -> Optional[LCThoughtProcess]:
        if self._current_process:
            self._current_process.finish(final_answer)
            self._history.append(self._current_process)

            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

            if self._thought_recorder and self._legacy_process:
                self._thought_recorder.finish(self._legacy_process, final_answer)

            finished = self._current_process
            self._current_process = None
            self._legacy_process = None
            return finished
        return None

    def get_session_processes(
        self,
        session_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[LCThoughtProcess]:
        sid = session_id or self.session_id
        processes = [
            p for p in self._history
            if p.session_id == sid
        ]
        return processes[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._history)
        if total == 0:
            return {
                'total_processes': 0,
                'avg_iterations': 0,
                'avg_elapsed_ms': 0,
            }

        avg_iterations = sum(p.iteration_count for p in self._history) / total
        avg_elapsed = sum(p.elapsed_ms for p in self._history) / total

        return {
            'total_processes': total,
            'avg_iterations': round(avg_iterations, 1),
            'avg_elapsed_ms': round(avg_elapsed, 1),
            'session_id': self.session_id,
        }

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        **kwargs: Any,
    ) -> None:
        if self._current_process:
            prompt_preview = prompts[0][:200] if prompts else ""
            self._current_process.add_step(
                "thought",
                f"[LLM开始推理] prompt长度: {len(prompts[0]) if prompts else 0}字符",
                prompt_preview=prompt_preview,
            )
        if self._thought_recorder and self._legacy_process:
            self._thought_recorder.add_thought(
                self._legacy_process,
                f"LLM开始推理 (prompt: {len(prompts[0]) if prompts else 0}字符)",
            )

    def on_llm_end(
        self,
        response: LLMResult,
        **kwargs: Any,
    ) -> None:
        if self._current_process and response.generations:
            for generation_list in response.generations:
                for gen in generation_list:
                    text = getattr(gen, 'text', '') or ''
                    if text:
                        self._current_process.add_step(
                            "thought_output",
                            f"[LLM输出] {text[:150]}...",
                            output_length=len(text),
                        )

    def on_llm_error(
        self,
        error: Exception | BaseException,
        **kwargs: Any,
    ) -> None:
        if self._current_process:
            self._current_process.add_step(
                "error",
                f"[LLM错误] {type(error).__name__}: {str(error)}",
                error_type=type(error).__name__,
            )
        if self._thought_recorder and self._legacy_process:
            self._thought_recorder.add_error(
                self._legacy_process,
                f"LLM错误: {type(error).__name__}: {str(error)}",
            )

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        if self._current_process:
            tool_name = serialized.get('name', 'unknown')
            self._current_process.add_step(
                "action",
                f"调用工具: {tool_name}",
                tool_name=tool_name,
                input=input_str[:200] if input_str else "",
            )
        if self._thought_recorder and self._legacy_process:
            self._thought_recorder.add_action(
                self._legacy_process,
                serialized.get('name', 'unknown'),
                input_str[:200] if input_str else "",
            )

    def on_tool_end(
        self,
        output: str,
        **kwargs: Any,
    ) -> None:
        if self._current_process:
            self._current_process.add_step(
                "observation",
                f"工具结果: {output[:200]}...",
                output_length=len(output),
            )
        if self._thought_recorder and self._legacy_process:
            self._thought_recorder.add_observation(
                self._legacy_process,
                output[:200] if output else "",
            )

    def on_tool_error(
        self,
        error: Exception | BaseException,
        **kwargs: Any,
    ) -> None:
        if self._current_process:
            self._current_process.add_step(
                "tool_error",
                f"[工具错误] {type(error).__name__}: {str(error)}",
                error_type=type(error).__name__,
            )
        if self._thought_recorder and self._legacy_process:
            self._thought_recorder.add_error(
                self._legacy_process,
                f"工具错误: {type(error).__name__}: {str(error)}",
            )

    def on_chain_end(
        self,
        outputs: Optional[Dict[str, Any] | list] = None,
        **kwargs: Any,
    ) -> None:
        if not self._current_process:
            return
        # Handle None, dict, list, or other types safely
        if isinstance(outputs, dict):
            final_output = outputs.get('output', '') or str(outputs)
        elif isinstance(outputs, (list, str)):
            final_output = str(outputs)
        else:
            final_output = ''
        self.finish_process(final_answer=final_output)
        logger.info(
            f"思维过程完成: {self._history[-1].process_id}, "
            f"迭代{self._history[-1].iteration_count}次, "
            f"耗时{self._history[-1].elapsed_ms:.1f}ms"
        )

    def on_chain_error(
        self,
        error: Exception | BaseException,
        **kwargs: Any,
    ) -> None:
        if self._current_process:
            self._current_process.status = "error"
            self._current_process.add_step(
                "fatal_error",
                f"[致命错误] {type(error).__name__}: {str(error)}",
                error_type=type(error).__name__,
            )
            self._history.append(self._current_process)
            self._current_process = None
            self._legacy_process = None