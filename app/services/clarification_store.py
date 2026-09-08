"""
ClarificationStore — `ask_student` 结构化反问的澄清记录存储（T03）。

职责：
1. 保存每次 `ask_student` 工具调用产生的澄清记录（clarification_id /
   pending_turn_id / session_id / question_summary 等），供 SSE 事件下发与
   学生回答时校验，防止多会话串线；
2. 按 (user_id, session_id) 隔离：同一用户同一会话同时最多存在一条 pending
   澄清（即"每轮最多 1 次"约束的执行点）；
3. 提供语义续接消息构造：把学生回答组装为新一轮用户消息。

注意：第一版为**语义续接**实现——学生回答作为新一轮用户消息 + 系统提示注入
"你刚才问了 X，学生答 Y，请继续"，**不等价于同轮 checkpoint/resume**，
待 T11（恢复流）完成后升级。

存储为进程内内存字典（无 schema 变更，符合 T03 约束）；进程重启即丢失，
丢失的后果仅是"学生提交回答时提示重新提问"，可接受。
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 澄清问题摘要长度上限（用于回传校验与注入续接消息）
QUESTION_SUMMARY_MAX_CHARS = 120
# 单条澄清记录的保留时长（秒）：resolved 之后保留一段时间用于审计/幂等判断
RESOLVED_TTL_SECONDS = 3600
# 全局最大记录条数（防止内存无界增长，淘汰最旧的已解决记录）
MAX_RECORDS = 2000


class ClarificationMismatchError(Exception):
    """学生回答与澄清记录标识不匹配（会话串线 / 重复提交 / 记录不存在）。"""


class DuplicatePendingClarificationError(Exception):
    """同一 (user_id, session_id) 已存在 pending 澄清（每轮最多 1 次）。"""


@dataclass
class ClarificationRecord:
    """一条澄清提问记录。"""

    clarification_id: str
    pending_turn_id: str
    user_id: str
    session_id: str
    question: str
    question_summary: str
    options: List[Dict[str, Any]] = field(default_factory=list)
    kind: str = "missing_condition"
    status: str = "pending"  # pending | resolved
    answer: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None

    def to_payload(self) -> Dict[str, Any]:
        """SSE 下发 / 回传校验使用的载荷。"""
        return {
            "clarification_id": self.clarification_id,
            "pending_turn_id": self.pending_turn_id,
            "session_id": self.session_id,
            "question": self.question,
            "question_summary": self.question_summary,
            "options": self.options,
            "kind": self.kind,
        }


def build_question_summary(question: str) -> str:
    """生成问题摘要（截断），用于回答校验与续接消息注入。"""
    text = (question or "").strip()
    if len(text) > QUESTION_SUMMARY_MAX_CHARS:
        text = text[:QUESTION_SUMMARY_MAX_CHARS].rstrip() + "…"
    return text


def build_continuation_message(question_summary: str, answer: str) -> str:
    """构造语义续接消息（学生回答作为新一轮用户消息注入）。

    注意：这是"语义续接"的近似实现，不等价于同轮 checkpoint/resume，
    待 T11（恢复流）完成后升级。
    """
    summary = (question_summary or "").strip()
    reply = (answer or "").strip()
    return (
        "【澄清回答】你刚才问了学生：「{q}」，学生回答：「{a}」。"
        "请基于该回答继续之前的推理；如信息仍不足以完整求解，"
        "请明确说明还缺什么，但不要原样重复刚才的问题。"
    ).format(q=summary, a=reply)


class ClarificationStore:
    """进程内澄清记录存储。"""

    def __init__(self) -> None:
        self._records: Dict[str, ClarificationRecord] = {}
        # (user_id, session_id) -> pending clarification_id
        self._pending_index: Dict[tuple, str] = {}

    def reset(self) -> None:
        """清空全部记录（仅供测试使用）。"""
        self._records.clear()
        self._pending_index.clear()

    async def create(
        self,
        user_id: str,
        session_id: str,
        question: str,
        options: Optional[List[Dict[str, Any]]] = None,
        kind: str = "missing_condition",
    ) -> ClarificationRecord:
        """创建一条 pending 澄清记录。

        Raises:
            DuplicatePendingClarificationError: 该用户该会话已存在 pending 澄清。
        """
        self._evict_expired()
        key = (user_id, session_id)
        pending_id = self._pending_index.get(key)
        if pending_id and pending_id in self._records:
            raise DuplicatePendingClarificationError(
                f"会话 {session_id} 已存在待回答的澄清提问，每轮最多 1 次"
            )

        record = ClarificationRecord(
            clarification_id=uuid.uuid4().hex,
            pending_turn_id=uuid.uuid4().hex,
            user_id=user_id,
            session_id=session_id,
            question=question,
            question_summary=build_question_summary(question),
            options=options or [],
            kind=kind,
        )
        self._records[record.clarification_id] = record
        self._pending_index[key] = record.clarification_id
        logger.info(
            f"[ask_student] 创建澄清: user={user_id} session={session_id} "
            f"clarification={record.clarification_id[:8]} kind={kind}"
        )
        return record

    async def get_pending(self, user_id: str, session_id: str) -> Optional[ClarificationRecord]:
        """获取该用户该会话当前 pending 的澄清记录（无则 None）。"""
        cid = self._pending_index.get((user_id, session_id))
        if not cid:
            return None
        record = self._records.get(cid)
        if record and record.status == "pending":
            return record
        return None

    async def get_pending_created_after(
        self, user_id: str, session_id: str, since_ts: float
    ) -> Optional[ClarificationRecord]:
        """获取本轮（自 since_ts 起）新产生的 pending 澄清，供 SSE 事件下发。"""
        record = await self.get_pending(user_id, session_id)
        if record and record.created_at >= since_ts:
            return record
        return None

    async def abandon(self, user_id: str, session_id: str) -> None:
        """放弃该会话当前 pending 的澄清（学生忽略卡片直接发新消息时调用），
        释放"每轮最多 1 次"的占用，避免阻塞后续反问。"""
        cid = self._pending_index.pop((user_id, session_id), None)
        if not cid:
            return
        record = self._records.get(cid)
        if record and record.status == "pending":
            record.status = "abandoned"
            record.resolved_at = time.time()
            logger.info(
                f"[ask_student] 澄清已放弃: user={user_id} session={session_id} "
                f"clarification={cid[:8]}"
            )

    async def resolve(
        self,
        user_id: str,
        session_id: str,
        clarification_id: str,
        pending_turn_id: str,
        answer: str,
    ) -> ClarificationRecord:
        """校验标识并解决澄清（学生回答入口）。

        任一标识不匹配（记录不存在 / 用户不符 / 会话不符 / 轮次不符 /
        已解决过）都抛出 ClarificationMismatchError，拒绝续接。
        """
        record = self._records.get(clarification_id)
        if (
            record is None
            or record.user_id != user_id
            or record.session_id != session_id
            or record.pending_turn_id != pending_turn_id
            or record.status != "pending"
        ):
            raise ClarificationMismatchError("澄清信息校验失败，可能已回答或会话不匹配")

        record.status = "resolved"
        record.answer = (answer or "").strip()
        record.resolved_at = time.time()
        self._pending_index.pop((record.user_id, record.session_id), None)
        logger.info(
            f"[ask_student] 澄清已回答: user={user_id} session={session_id} "
            f"clarification={clarification_id[:8]}"
        )
        return record

    def _evict_expired(self) -> None:
        """淘汰过期已解决记录并限制总量（防止内存无界增长）。"""
        now = time.time()
        expired = [
            cid
            for cid, rec in self._records.items()
            if rec.status == "resolved"
            and rec.resolved_at is not None
            and now - rec.resolved_at > RESOLVED_TTL_SECONDS
        ]
        for cid in expired:
            self._records.pop(cid, None)
        if len(self._records) <= MAX_RECORDS:
            return
        resolved_sorted = sorted(
            (cid for cid, rec in self._records.items() if rec.status == "resolved"),
            key=lambda cid: self._records[cid].created_at,
        )
        for cid in resolved_sorted[: len(self._records) - MAX_RECORDS]:
            rec = self._records.pop(cid, None)
            if rec:
                self._pending_index.pop((rec.user_id, rec.session_id), None)


_store: Optional[ClarificationStore] = None


def get_clarification_store() -> ClarificationStore:
    """获取全局 ClarificationStore 单例。"""
    global _store
    if _store is None:
        _store = ClarificationStore()
    return _store
