"""
ask_student 工具 — 苏格拉底式结构化反问（T03）。

借鉴 DeepTutor 的 ask_user 机制：Agent 遇到题目信息不足时不猜测、不硬答，
而是发出结构化澄清问题。第一版采用**语义续接**协议（回答作为新一轮用户
消息 + 系统提示注入），不等价于同轮 checkpoint/resume，待 T11 恢复流完成后升级。

行为：
- 交互模式：创建 pending 澄清记录（clarification_id / pending_turn_id /
  session_id / question_summary），由 SSE 流以 `ask_student` 事件下发给前端
  渲染结构化问题卡片；
- headless 安全等价物（对齐 DeepTutor no-TTY 行为）：CONTENT_AI_PROVIDER=mock
  或上下文标记 headless/batch_mode 时，自动返回空回复并附 auto_resolved: true，
  不创建 pending 记录，保证批处理不挂起；
- 每轮最多 1 次：同一 (user_id, session_id) 已有 pending 澄清时拒绝再次创建。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from tools.base_tool import BaseTool, ToolInput, ToolOutput

# kind 只有这 3 种，对应不同 UI 呈现
ALLOWED_KINDS = ("missing_condition", "ambiguous_term", "confirm_approach")

KIND_LABELS = {
    "missing_condition": "缺条件",
    "ambiguous_term": "概念歧义",
    "confirm_approach": "确认思路",
}

MAX_QUESTION_CHARS = 500
MAX_OPTIONS = 6
MAX_OPTION_TEXT_CHARS = 200


class AskStudentTool(BaseTool):
    """结构化反问工具：向学生发起澄清提问，而不是硬答。"""

    name = "ask_student"
    description = (
        "向学生发起结构化澄清提问（苏格拉底式反问）。仅在两种情况使用："
        "①题目缺失必要条件、无法求解（如几何题缺角度/直角信息）；"
        "②存在多种解法路径、需要学生选择。调用后请停止推理等待学生回答。"
        "禁止用它向学生索要答案。"
    )
    version = "1.0.0"
    capabilities = []

    def get_info(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [c.value for c in self.capabilities],
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "向学生提出的澄清问题"},
                    "options": {
                        "type": "array",
                        "description": "可选的选项列表，每项 {label, text}",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "text": {"type": "string"},
                            },
                        },
                    },
                    "kind": {
                        "type": "string",
                        "enum": list(ALLOWED_KINDS),
                        "description": "澄清类型：missing_condition(缺条件) / ambiguous_term(概念歧义) / confirm_approach(确认思路)",
                    },
                },
                "required": ["question"],
            },
        }

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        params: Dict[str, Any] = input_data.parameters or {}
        question = str(params.get("question") or input_data.query or "").strip()
        kind = str(params.get("kind") or "missing_condition").strip()
        options = self._normalize_options(params.get("options"))

        if not question:
            return ToolOutput(success=False, error="question 不能为空", tool_name=self.name)
        if len(question) > MAX_QUESTION_CHARS:
            question = question[:MAX_QUESTION_CHARS].rstrip() + "…"
        if kind not in ALLOWED_KINDS:
            return ToolOutput(
                success=False,
                error=f"kind 必须是 {' / '.join(ALLOWED_KINDS)} 之一，收到: {kind}",
                tool_name=self.name,
            )

        context = input_data.context or {}

        # ── headless 安全等价物：mock / 批处理场景不挂起 ──
        if self._is_headless(context):
            return ToolOutput(
                success=True,
                result=(
                    "（批处理/无界面模式）当前无法等待学生输入，澄清已自动跳过"
                    "（auto_resolved）。请基于现有信息直接作答，并说明哪些条件缺失。"
                ),
                data={"auto_resolved": True, "kind": kind},
                tool_name=self.name,
            )

        # ── 数据按真实 user_id 隔离：缺身份直接拒绝 ──
        user_id = str(context.get("user_id") or "").strip()
        session_id = str(context.get("session_id") or "").strip()
        if not user_id or not session_id:
            return ToolOutput(
                success=False,
                error="缺少 user_id / session_id 上下文，无法发起澄清提问",
                tool_name=self.name,
            )

        from app.services.clarification_store import (
            DuplicatePendingClarificationError,
            get_clarification_store,
        )

        store = get_clarification_store()
        try:
            record = await store.create(
                user_id=user_id,
                session_id=session_id,
                question=question,
                options=options,
                kind=kind,
            )
        except DuplicatePendingClarificationError:
            # 每轮最多 1 次：已有 pending 澄清时拒绝再次提问
            return ToolOutput(
                success=True,
                result=(
                    "本轮已经向学生提问过一次（ask_student 每轮最多 1 次），"
                    "不得重复调用。请基于已有信息作答，或明确说明还缺什么条件。"
                ),
                data={"duplicate": True, "kind": kind},
                tool_name=self.name,
            )

        return ToolOutput(
            success=True,
            result=(
                "已向学生发出结构化澄清问题，请立即停止进一步推理，"
                "等待学生回答（学生回答后会作为新消息送达）。"
            ),
            data=record.to_payload(),
            tool_name=self.name,
        )

    @staticmethod
    def _is_headless(context: Dict[str, Any]) -> bool:
        """判断当前是否为 headless / 批处理场景。"""
        from app.config.settings import settings

        try:
            if str(getattr(settings, "CONTENT_AI_PROVIDER", "") or "").lower() == "mock":
                return True
        except Exception:
            pass
        return bool(context.get("headless") or context.get("batch_mode"))

    @staticmethod
    def _normalize_options(raw: Any) -> List[Dict[str, Any]]:
        """规范化选项为 [{label, text}]，最多 MAX_OPTIONS 个。"""
        if not isinstance(raw, (list, tuple)):
            return []
        options: List[Dict[str, Any]] = []
        for item in raw[:MAX_OPTIONS]:
            if isinstance(item, dict):
                label = str(item.get("label") or "").strip()
                text = str(item.get("text") or item.get("description") or "").strip()
            else:
                label = ""
                text = str(item or "").strip()
            if not text:
                continue
            if not label:
                label = chr(ord("A") + len(options))
            if len(text) > MAX_OPTION_TEXT_CHARS:
                text = text[:MAX_OPTION_TEXT_CHARS].rstrip() + "…"
            options.append({"label": label, "text": text})
        return options
