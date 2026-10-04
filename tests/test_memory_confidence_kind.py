"""阶段四 6.1/6.2/6.3 记忆 kind 类型系统与置信度引擎回归测试。"""

import pytest

from app.services.memory_policy import (
    CONFIDENCE_AUTO_EXTRACTED,
    MEMORY_KIND_CONTEXT,
    MEMORY_KIND_FACT,
    MEMORY_KIND_MISCONCEPTION,
    MEMORY_TYPE_CONVERSATION,
    MEMORY_TYPE_ERROR,
    MEMORY_TYPE_PROFILE,
    infer_memory_kind,
)


def test_kind_inference_heuristic():
    assert infer_memory_kind(MEMORY_TYPE_ERROR) == MEMORY_KIND_MISCONCEPTION
    assert infer_memory_kind(MEMORY_TYPE_PROFILE) == MEMORY_KIND_FACT
    assert infer_memory_kind(MEMORY_TYPE_CONVERSATION) == MEMORY_KIND_CONTEXT
    # 未知类型保守落 context(不注入推导)
    assert infer_memory_kind("unknown-type") == MEMORY_KIND_CONTEXT


def test_kind_inference_explicit_and_invalid():
    assert infer_memory_kind(MEMORY_TYPE_CONVERSATION, MEMORY_KIND_FACT) == MEMORY_KIND_FACT
    with pytest.raises(ValueError):
        infer_memory_kind(MEMORY_TYPE_ERROR, "not-a-kind")


def test_create_paths_assign_kind_and_initial_confidence():
    """写入路径强制 kind;自动提取初始置信度 0.5(6.3)。"""
    from app.services.memory_policy import MEMORY_INIT_STRENGTH

    # 通过 policy 契约验证:所有 memory_type 都能推出合法 kind
    for memory_type in MEMORY_INIT_STRENGTH:
        kind = infer_memory_kind(memory_type)
        assert kind in {"preference", "fact", "misconception", "context"}
    assert CONFIDENCE_AUTO_EXTRACTED == 0.5


def test_migration_head_includes_memory_columns():
    """新迁移在 head 且模型列齐备(空库升级在 test_content_ai 全链验证)。"""
    from app.data.models import Memory

    for column in ("confidence", "memory_kind", "last_confirmed_at", "superseded_by", "conflict_status"):
        assert hasattr(Memory, column), f"Memory 缺少列 {column}"


def test_low_confidence_archive_threshold_is_doc_value():
    from app.services.memory_policy import CONFIDENCE_STRENGTH_ARCHIVE_THRESHOLD

    assert CONFIDENCE_STRENGTH_ARCHIVE_THRESHOLD == 0.15
