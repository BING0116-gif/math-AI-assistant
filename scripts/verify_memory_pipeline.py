"""
记忆系统全链路验证脚本。

在 Mock 模式下验证以下全链路流程：
1. 模拟做题事件 → 错题记忆写入
2. 记忆检索
3. 用户画像加载
4. 记忆强度更新
5. 记忆归档

用法：
    python scripts/verify_memory_pipeline.py
"""

import asyncio
import json
import logging
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 设置环境变量为 Mock 模式
os.environ["QUESTION_SYSTEM_MODE"] = "mock"
os.environ["MEMORY_ENABLED"] = "true"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-6s | %(name)-30s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
logger = logging.getLogger("verify_memory_pipeline")

# 测试用户
TEST_USER_ID = "verify_test_user"


async def step1_test_error_memory_write():
    """步骤 1：测试错题记忆写入。"""
    logger.info("=" * 60)
    logger.info("步骤 1/6：测试错题记忆写入")
    logger.info("=" * 60)

    from app.services.memory_store import get_memory_store

    store = get_memory_store()
    memory_id = await store.create_error_memory(
        user_id=TEST_USER_ID,
        question_id="verify_q_001",
        question_content="判断级数 ∑(1/n^2) 的收敛性",
        high_category="高等数学",
        category="无穷级数",
        knowledge_points=["比值审敛法", "p级数"],
        difficulty=3,
        user_answer="发散",
        correct_answer="收敛，因为 p=2>1",
        error_type="概念混淆",
    )

    assert memory_id is not None, "❌ 错题记忆写入失败"
    logger.info(f"✅ 错题记忆写入成功: memory_id={memory_id}")

    # 验证 MySQL 写入
    memory = await store.get_memory_by_id(memory_id)
    assert memory is not None, "❌ 无法查询到刚写入的记忆"
    assert memory["memory_type"] == "error", f"❌ 记忆类型错误: {memory['memory_type']}"
    assert memory["status"] == "active", f"❌ 状态错误: {memory['status']}"
    logger.info(f"✅ MySQL 写入验证通过: type={memory['memory_type']}, status={memory['status']}")

    return memory_id


async def step2_test_conversation_memory_write():
    """步骤 2：测试对话记忆写入。"""
    logger.info("=" * 60)
    logger.info("步骤 2/6：测试对话记忆写入")
    logger.info("=" * 60)

    from app.services.memory_store import get_memory_store

    store = get_memory_store()
    memory_id = await store.create_conversation_memory(
        user_id=TEST_USER_ID,
        content="学生提问：比值审敛法和根值审敛法有什么区别？AI回答：比值审敛法适用于通项包含阶乘的情况，根值审敛法适用于通项包含n次幂的情况。",
        high_category="高等数学",
        category="无穷级数",
        importance=0.7,
        tags=["比值审敛法", "根值审敛法"],
    )

    assert memory_id is not None, "❌ 对话记忆写入失败"
    logger.info(f"✅ 对话记忆写入成功: memory_id={memory_id}")
    return memory_id


async def step3_test_milestone_memory_write():
    """步骤 3：测试里程碑记忆写入。"""
    logger.info("=" * 60)
    logger.info("步骤 3/6：测试里程碑记忆写入")
    logger.info("=" * 60)

    from app.services.memory_store import get_memory_store

    store = get_memory_store()
    memory_id = await store.create_milestone_memory(
        user_id=TEST_USER_ID,
        milestone_type="chapter_complete",
        description="完成「无穷级数」章节学习，正确率从 35% 提升至 78%",
        high_category="高等数学",
        category="无穷级数",
    )

    assert memory_id is not None, "❌ 里程碑记忆写入失败"
    logger.info(f"✅ 里程碑记忆写入成功: memory_id={memory_id}")
    return memory_id


async def step4_test_memory_retrieval():
    """步骤 4：测试记忆检索。"""
    logger.info("=" * 60)
    logger.info("步骤 4/6：测试记忆检索")
    logger.info("=" * 60)

    from app.services.memory_retrieval import get_retrieval_engine

    engine = get_retrieval_engine()
    result = await engine.retrieve(
        user_id=TEST_USER_ID,
        query_text="级数收敛怎么判断",
        top_k=7,
    )

    assert result.total > 0, "❌ 记忆检索未返回结果"
    logger.info(f"✅ 记忆检索成功: 返回 {result.total} 条记忆")
    logger.info(f"   统计: {result.stats}")

    for i, mem in enumerate(result.memories):
        logger.info(f"   [{i+1}] type={mem.memory_type}, score={mem.score:.3f}, source={mem.source}")

    return result


async def step5_test_profile_service():
    """步骤 5：测试用户画像服务。"""
    logger.info("=" * 60)
    logger.info("步骤 5/6：测试用户画像服务")
    logger.info("=" * 60)

    from app.services.profile_service import get_profile_service

    service = get_profile_service()

    # 冷启动画像
    profile = await service.get_profile(TEST_USER_ID)
    assert profile is not None, "❌ 画像加载失败"
    logger.info(f"✅ 用户画像加载成功: version={profile.get('version')}")
    logger.info(f"   摘要: {profile.get('summary_text', '')[:80]}")

    # 增量更新
    success = await service.incremental_update(
        user_id=TEST_USER_ID,
        high_category="高等数学",
        category="无穷级数",
        mastery_score=0.65,
        correct_rate=0.62,
    )
    assert success, "❌ 画像增量更新失败"
    logger.info(f"✅ 画像增量更新成功")

    # 全量刷新
    success = await service.full_refresh(TEST_USER_ID)
    assert success, "❌ 画像全量刷新失败"
    logger.info(f"✅ 画像全量刷新成功")

    return profile


async def step6_test_memory_strength_and_archive():
    """步骤 6：测试记忆强度更新和归档。"""
    logger.info("=" * 60)
    logger.info("步骤 6/6：测试记忆强度更新和归档")
    logger.info("=" * 60)

    from app.services.memory_store import get_memory_store

    store = get_memory_store()

    # 获取一条记忆
    memories, total = await store.get_user_memories(
        user_id=TEST_USER_ID,
        memory_type="error",
        limit=1,
    )
    if total > 0:
        memory_id = memories[0]["id"]

        # 更新强度
        success = await store.update_memory_access(memory_id)
        assert success, "❌ 记忆强度更新失败"
        logger.info(f"✅ 记忆强度更新成功: memory_id={memory_id}")

        # 归档
        success = await store.archive_memory(memory_id)
        assert success, "❌ 记忆归档失败"
        logger.info(f"✅ 记忆归档成功: memory_id={memory_id}")

        # 恢复为 active 用于后续测试
        from app.data.database import get_db_session
        from sqlalchemy import text as sa_text
        async with get_db_session() as db:
            await db.execute(
                sa_text("UPDATE memories SET status = 'active' WHERE id = :id"),
                {"id": memory_id},
            )
        logger.info(f"✅ 记忆已恢复为 active")
    else:
        logger.warning("⚠️ 无错题记忆可测试强度更新")

    # 测试批量过期归档
    archived = await store.batch_archive_expired()
    logger.info(f"✅ 过期归档完成: {archived} 条")

    # 测试低强度归档
    low_count = await store.batch_archive_low_strength(threshold=0.01)
    logger.info(f"✅ 低强度归档完成: {low_count} 条")


async def main():
    """全链路验证主流程。"""
    logger.info("")
    logger.info("🚀 记忆系统全链路验证开始")
    logger.info("=" * 60)

    passed = 0
    failed = 0

    steps = [
        ("错题记忆写入", step1_test_error_memory_write),
        ("对话记忆写入", step2_test_conversation_memory_write),
        ("里程碑记忆写入", step3_test_milestone_memory_write),
        ("记忆检索", step4_test_memory_retrieval),
        ("用户画像", step5_test_profile_service),
        ("强度更新与归档", step6_test_memory_strength_and_archive),
    ]

    for name, step_func in steps:
        try:
            await step_func()
            passed += 1
        except Exception as e:
            logger.error(f"❌ 步骤 [{name}] 失败: {e}", exc_info=True)
            failed += 1

    logger.info("")
    logger.info("=" * 60)
    logger.info(f"📊 全链路验证结果")
    logger.info(f"   通过: {passed}/{len(steps)}")
    logger.info(f"   失败: {failed}/{len(steps)}")
    logger.info("=" * 60)

    if failed > 0:
        logger.error("❌ 部分验证未通过，请检查错误日志")
        sys.exit(1)
    else:
        logger.info("✅ 所有验证通过！")


if __name__ == "__main__":
    asyncio.run(main())