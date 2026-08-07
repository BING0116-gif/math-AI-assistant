"""
题目数据迁移脚本：从 PostgreSQL 数据库迁移题目向量到 Qdrant。

功能：
1. 从 Question 表读取所有题目
2. 使用 SentenceTransformer 生成向量
3. 批量导入到 Qdrant
4. 记录迁移状态到 migration_status 表
5. 数据完整性校验

用法：
    python scripts/migrate_questions_to_qdrant.py
    python scripts/migrate_questions_to_qdrant.py --batch-size 200
    python scripts/migrate_questions_to_qdrant.py --validate-only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

sys.path.insert(0, ".")

from sqlalchemy import select

from app.data.database import get_db_session, init_db
from app.data.models import Question
from app.services.vector_store import QdrantVectorStoreManager, get_vector_store

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def fetch_all_questions() -> List[Question]:
    async with get_db_session() as db:
        result = await db.execute(select(Question))
        questions = result.scalars().all()
        return questions


async def record_migration_start(total_count: int) -> int:
    async with get_db_session() as db:
        from sqlalchemy import text

        result = await db.execute(
            text(
                """
                INSERT INTO migration_status
                (source_system, target_system, status, total_count, started_at)
                VALUES ('chromadb', 'qdrant', 'running', :total_count, :started_at)
                RETURNING id
                """
            ),
            {"total_count": total_count, "started_at": datetime.now(timezone.utc)},
        )
        await db.commit()
        return result.scalar()


async def record_migration_progress(
    migration_id: int, migrated_count: int, failed_count: int
) -> None:
    async with get_db_session() as db:
        from sqlalchemy import text

        await db.execute(
            text(
                """
                UPDATE migration_status
                SET migrated_count = :migrated_count,
                    failed_count = :failed_count,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :migration_id
                """
            ),
            {
                "migration_id": migration_id,
                "migrated_count": migrated_count,
                "failed_count": failed_count,
            },
        )
        await db.commit()


async def record_migration_complete(
    migration_id: int, success: bool, error_message: str = ""
) -> None:
    async with get_db_session() as db:
        from sqlalchemy import text

        status = "completed" if success else "failed"
        await db.execute(
            text(
                f"""
                UPDATE migration_status
                SET status = '{status}',
                    completed_at = CURRENT_TIMESTAMP,
                    error_message = :error_message,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :migration_id
                """
            ),
            {"migration_id": migration_id, "error_message": error_message},
        )
        await db.commit()


async def record_migration_error(
    migration_id: int, question_id: str, error_type: str, error_detail: str
) -> None:
    async with get_db_session() as db:
        from sqlalchemy import text

        await db.execute(
            text(
                """
                INSERT INTO migration_errors
                (migration_id, question_id, error_type, error_detail)
                VALUES (:migration_id, :question_id, :error_type, :error_detail)
                """
            ),
            {
                "migration_id": migration_id,
                "question_id": question_id,
                "error_type": error_type,
                "error_detail": error_detail,
            },
        )
        await db.commit()


async def validate_migration(
    qdrant_store: QdrantVectorStoreManager, expected_count: int
) -> Tuple[bool, Dict[str, Any]]:
    logger.info("[迁移验证] 开始数据验证...")

    stats = await qdrant_store.get_collection_stats()
    actual_count = stats.get("total_documents", 0)

    count_match = actual_count == expected_count

    qdrant_ids = set(await qdrant_store.get_all_ids())

    db_ids = set()
    async with get_db_session() as db:
        from sqlalchemy import select

        result = await db.execute(select(Question.id))
        db_ids = {str(row[0]) for row in result.all()}

    missing_in_qdrant = db_ids - qdrant_ids
    extra_in_qdrant = qdrant_ids - db_ids
    id_match = len(missing_in_qdrant) == 0 and len(extra_in_qdrant) == 0

    result = {
        "expected_count": expected_count,
        "actual_count": actual_count,
        "count_match": count_match,
        "id_match": id_match,
        "missing_in_qdrant": list(missing_in_qdrant)[:10],
        "extra_in_qdrant": list(extra_in_qdrant)[:10],
        "categories": stats.get("categories", []),
        "difficulty_range": stats.get("difficulty_range", None),
        "mode": stats.get("mode", "unknown"),
    }

    all_passed = count_match and id_match

    if all_passed:
        logger.info("[迁移验证] 验证通过！")
    else:
        logger.error(f"[迁移验证] 验证失败: {result}")

    return all_passed, result


async def migrate_questions(batch_size: int = 100) -> Dict[str, Any]:
    logger.info("=" * 60)
    logger.info("开始题目向量迁移：PostgreSQL -> Qdrant")
    logger.info("=" * 60)

    start_time = time.time()

    try:
        questions = await fetch_all_questions()
        total_count = len(questions)
        logger.info(f"共找到 {total_count} 道题目")

        if total_count == 0:
            logger.warning("没有找到题目，迁移结束")
            return {"success": True, "total_count": 0, "migrated_count": 0}

        migration_id = await record_migration_start(total_count)
        logger.info(f"迁移任务 ID: {migration_id}")

        qdrant_store = await get_vector_store()

        migrated_count = 0
        failed_count = 0

        for i in range(0, total_count, batch_size):
            batch = questions[i : i + batch_size]
            batch_data = []

            for q in batch:
                try:
                    metadata = {
                        "content": q.content,
                        "category": q.category or "",
                        "difficulty": q.difficulty or 3,
                        "knowledge_points": (
                            json.loads(q.knowledge_points)
                            if q.knowledge_points
                            else []
                        ),
                        "question_type": q.question_type or "",
                        "estimated_time": q.estimated_time or 3,
                        "source": q.source or "",
                    }
                    batch_data.append((str(q.id), q.content, metadata, None))
                except Exception as e:
                    failed_count += 1
                    await record_migration_error(
                        migration_id, str(q.id), "prepare_error", str(e)
                    )
                    logger.error(f"准备题目失败: id={q.id}, error={e}")

            if batch_data:
                try:
                    success = await qdrant_store.add_questions_batch(
                        batch_data, batch_size=batch_size
                    )
                    migrated_count += success
                    failed_count += len(batch_data) - success

                    if len(batch_data) - success > 0:
                        logger.warning(
                            f"批量导入部分失败: {len(batch_data) - success}/{len(batch_data)}"
                        )
                except Exception as e:
                    failed_count += len(batch_data)
                    logger.error(f"批量导入失败: batch={i}, error={e}")

            await record_migration_progress(migration_id, migrated_count, failed_count)

            progress = (i + len(batch)) / total_count * 100
            logger.info(
                f"进度: {migrated_count}/{total_count} "
                f"({progress:.1f}%) | 失败: {failed_count}"
            )

        elapsed = time.time() - start_time
        logger.info("-" * 60)
        logger.info(
            f"迁移完成: 成功 {migrated_count}, "
            f"失败 {failed_count}, 耗时 {elapsed:.2f}s"
        )
        logger.info("-" * 60)

        validation_passed, validation_result = await validate_migration(
            qdrant_store, total_count
        )

        await record_migration_complete(
            migration_id,
            success=validation_passed,
            error_message="" if validation_passed else "数据验证失败",
        )

        return {
            "success": validation_passed,
            "migration_id": migration_id,
            "total_count": total_count,
            "migrated_count": migrated_count,
            "failed_count": failed_count,
            "elapsed_seconds": elapsed,
            "validation": validation_result,
        }

    except Exception as e:
        logger.error(f"迁移失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}


async def validate_only() -> Dict[str, Any]:
    logger.info("=" * 60)
    logger.info("仅验证模式：检查 Qdrant 数据完整性")
    logger.info("=" * 60)

    questions = await fetch_all_questions()
    total_count = len(questions)

    qdrant_store = await get_vector_store()
    passed, result = await validate_migration(qdrant_store, total_count)

    return {"success": passed, "validation": result}


async def _ensure_migration_tables() -> None:
    """确保迁移状态表存在（兼容 SQLite 和 PostgreSQL）。"""
    from sqlalchemy import text

    async with get_db_session() as db:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS migration_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_system VARCHAR(50) NOT NULL DEFAULT 'chromadb',
                target_system VARCHAR(50) NOT NULL DEFAULT 'qdrant',
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                total_count INTEGER DEFAULT 0,
                migrated_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS migration_errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_id INTEGER,
                question_id VARCHAR(100),
                error_type VARCHAR(50),
                error_detail TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (migration_id) REFERENCES migration_status(id) ON DELETE CASCADE
            )
        """))

        try:
            await db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_migration_status_status
                ON migration_status(status)
            """))
            await db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_migration_errors_migration_id
                ON migration_errors(migration_id)
            """))
            await db.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_migration_errors_question_id
                ON migration_errors(question_id)
            """))
        except Exception:
            pass

        await db.commit()
        logger.info("迁移状态表已就绪")


async def _run_task(batch_size: int, validate_only: bool) -> Dict[str, Any]:
    import os
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

    logger.info("正在初始化数据库...")
    await init_db()
    logger.info("数据库初始化完成")

    await _ensure_migration_tables()

    if validate_only:
        return await validate_only()
    else:
        return await migrate_questions(batch_size=batch_size)


def main():
    parser = argparse.ArgumentParser(description="题目向量迁移脚本")
    parser.add_argument(
        "--batch-size", type=int, default=100, help="批量导入大小 (默认: 100)"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="仅验证数据完整性，不执行迁移",
    )

    args = parser.parse_args()

    result = asyncio.run(_run_task(args.batch_size, args.validate_only))

    print("\n" + "=" * 60)
    print("迁移结果:")
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print("=" * 60)

    sys.exit(0 if result.get("success") else 1)


if __name__ == "__main__":
    main()
