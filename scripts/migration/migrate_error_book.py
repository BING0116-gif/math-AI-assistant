"""
错题本数据迁移脚本 - 将 JSON 文件存储的错题数据迁移到数据库。

用法:
    python scripts/migration/migrate_error_book.py [--user-id <用户ID>] [--json-path <JSON文件路径>]

如果未指定 --user-id，将使用默认用户 "default"。
如果未指定 --json-path，默认读取 data/error_book.json。
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-6s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def migrate_error_book(
    user_id: str = "default",
    json_path: str = "data/error_book.json",
) -> Dict[str, Any]:
    """
    将 JSON 文件中的错题数据迁移到数据库。

    Args:
        user_id: 分配给迁移数据的用户 ID（因为原 JSON 数据没有 user_id 字段）
        json_path: JSON 文件路径

    Returns:
        迁移结果统计
    """
    # 确认 JSON 文件存在
    json_file = Path(json_path)
    if not json_file.exists():
        logger.error(f"JSON 文件不存在: {json_path}")
        return {"status": "error", "message": f"文件不存在: {json_path}"}

    # 读取 JSON 数据
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"读取 JSON 文件失败: {e}")
        return {"status": "error", "message": str(e)}

    if not isinstance(data, list):
        logger.error("JSON 文件格式错误：期望一个数组")
        return {"status": "error", "message": "JSON 格式错误：期望数组"}

    total = len(data)
    if total == 0:
        logger.info("JSON 文件中没有数据，无需迁移")
        return {"status": "success", "total": 0, "migrated": 0, "failed": 0}

    logger.info(f"找到 {total} 条错题记录，准备迁移到用户 '{user_id}'...")

    # 导入数据库相关模块
    from app.data.database import get_db_session, init_db
    from app.data.models import ErrorItem as ErrorItemModel

    # 确保数据库已初始化
    await init_db()

    migrated = 0
    failed = 0
    errors: List[str] = []

    async with get_db_session() as db:
        for idx, item in enumerate(data):
            try:
                item_id = item.get("id", "")
                if not item_id:
                    # 生成一个随机 ID
                    import uuid
                    item_id = str(uuid.uuid4())[:8]

                db_item = ErrorItemModel(
                    user_id=user_id,
                    item_id=item_id,
                    question=item.get("question", ""),
                    question_type=item.get("question_type", "text"),
                    image_path=item.get("image_path"),
                    error_reason=item.get("error_reason", ""),
                    categories=item.get("categories", []),
                    original_answer=item.get("original_answer", ""),
                    correct_answer=item.get("correct_answer", ""),
                    notes=item.get("notes", ""),
                    added_at=item.get("added_at", ""),
                    mastery_level=item.get("mastery_level", 3),
                    is_mastered=item.get("is_mastered", False),
                )
                db.add(db_item)
                migrated += 1

                if (idx + 1) % 10 == 0 or idx == total - 1:
                    logger.info(f"  迁移进度: {idx + 1}/{total}")

            except Exception as e:
                failed += 1
                error_msg = f"第 {idx + 1} 条记录迁移失败: {e}"
                logger.warning(error_msg)
                errors.append(error_msg)

    logger.info(f"迁移完成: 总计 {total}, 成功 {migrated}, 失败 {failed}")

    result = {
        "status": "success",
        "total": total,
        "migrated": migrated,
        "failed": failed,
        "user_id": user_id,
        "source_file": json_path,
    }

    if errors:
        result["errors"] = errors[:5]  # 只返回前 5 个错误

    return result


def main():
    parser = argparse.ArgumentParser(description="将错题本 JSON 数据迁移到数据库")
    parser.add_argument(
        "--user-id",
        default="default",
        help="分配给迁移数据的用户 ID（默认: default）",
    )
    parser.add_argument(
        "--json-path",
        default="data/error_book.json",
        help="JSON 文件路径（默认: data/error_book.json）",
    )
    args = parser.parse_args()

    result = asyncio.run(migrate_error_book(
        user_id=args.user_id,
        json_path=args.json_path,
    ))

    if result["status"] == "success":
        logger.info(
            f"✅ 迁移成功: {result['migrated']}/{result['total']} 条记录已迁移"
        )
        if result["failed"] > 0:
            logger.warning(f"⚠️  {result['failed']} 条记录迁移失败")
    else:
        logger.error(f"❌ 迁移失败: {result.get('message', '未知错误')}")
        sys.exit(1)


if __name__ == "__main__":
    main()