"""题目语义去重服务。

只复用题目主集合的 embedding 与 Qdrant 检索能力，不写入向量库。任何运行时
故障都按 fail-open 处理，避免查重依赖阻塞可验证的变式生成链路。
"""

from __future__ import annotations

import logging
from typing import Any

from app.config.settings import settings

logger = logging.getLogger(__name__)


def _result_value(result: Any, name: str, default: Any = None) -> Any:
    if isinstance(result, dict):
        return result.get(name, default)
    return getattr(result, name, default)


async def find_similar_questions(
    embedding_service,
    vector_store,
    text: str,
    threshold: float | None = None,
    top_k: int = 5,
) -> list[dict]:
    """返回题目主向量集合中达到阈值的候选。

    结果固定为 ``[{"question_id": str, "score": float}]``，按相似度降序。
    embedding 或 Qdrant 不可用时返回空列表并记录 warning，不阻塞调用方。
    """
    effective_threshold = (
        settings.QUESTION_DEDUP_THRESHOLD if threshold is None else float(threshold)
    )
    if not 0 < effective_threshold <= 1:
        raise ValueError("question dedup threshold must be within (0, 1]")
    if top_k < 1:
        raise ValueError("top_k must be positive")
    if not str(text or "").strip():
        return []

    try:
        vector = await embedding_service.encode_async(text)
        results = await vector_store.semantic_search(
            vector, n_results=min(int(top_k), 50)
        )
    except Exception as exc:
        logger.warning(
            "[题目去重] embedding/Qdrant 不可用，跳过向量查重: %s",
            exc,
        )
        return []

    matches: list[dict] = []
    for result in results or []:
        score = float(_result_value(result, "score", 0.0) or 0.0)
        if score < effective_threshold:
            continue
        question_id = _result_value(result, "id") or _result_value(
            result, "question_id"
        )
        if question_id is None:
            metadata = _result_value(result, "metadata", {}) or {}
            question_id = metadata.get("question_id")
        if question_id is None:
            continue
        matches.append({"question_id": str(question_id), "score": score})

    matches.sort(key=lambda row: row["score"], reverse=True)
    if matches:
        logger.info(
            "[题目去重] 拦截高相似候选: threshold=%.4f matches=%s",
            effective_threshold,
            [
                {"question_id": row["question_id"], "score": round(row["score"], 6)}
                for row in matches
            ],
        )
    return matches
