import json
import os
import logging
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

from app.data.database import init_db, get_db_session, engine
from app.data.models import User, LearningRecord, Question, ChatSession, ChatMessage
from app.data.repositories import (
    UserRepository,
    LearningRecordRepository,
    QuestionRepository,
    ChatSessionRepository,
    ChatMessageRepository,
)
from app.security.encryption import DataEncryption

logger = logging.getLogger(__name__)


@dataclass
class MigrationReport:
    source: str
    target: str
    total_source_records: int
    migrated: int
    skipped: int
    errors: int
    details: List[Dict[str, Any]]


class DataMigrator:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.reports: List[MigrationReport] = []
        self.encryption = DataEncryption()

    async def run_all_migrations(self) -> List[MigrationReport]:
        logger.info("=" * 60)
        logger.info("开始数据迁移...")
        logger.info(f"模式: {'预演 (Dry Run)' if self.dry_run else '正式迁移'}")
        logger.info("=" * 60)

        await init_db()

        await self._migrate_error_book()
        await self._migrate_users_from_auth_file()
        await self._migrate_static_backup()

        logger.info("=" * 60)
        logger.info("数据迁移完成！")
        for report in self.reports:
            logger.info(
                f"  {report.source} → {report.target}: "
                f"迁移 {report.migrated}/{report.total_source_records} 条, "
                f"跳过 {report.skipped} 条, 错误 {report.errors} 条"
            )
        logger.info("=" * 60)

        return self.reports

    async def _migrate_error_book(self) -> None:
        source_file = Path("data/error_book.json")
        if not source_file.exists():
            source_file = Path("error_book.json")
        if not source_file.exists():
            logger.info("未找到错题本数据文件，跳过迁移")
            return

        logger.info(f"发现错题本数据: {source_file}")

        try:
            with open(source_file, "r", encoding="utf-8") as f:
                error_items = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"读取错题本数据失败: {e}")
            self.reports.append(
                MigrationReport(
                    source=str(source_file),
                    target="learning_records + questions",
                    total_source_records=0,
                    migrated=0,
                    skipped=0,
                    errors=1,
                    details=[{"error": str(e)}],
                )
            )
            return

        if not isinstance(error_items, list):
            logger.warning("错题本数据格式不正确，期望列表")
            return

        migrated = 0
        skipped = 0
        errors = 0
        details = []

        async with get_db_session() as db:
            question_repo = QuestionRepository(db)
            record_repo = LearningRecordRepository(db)

            for idx, item in enumerate(error_items):
                try:
                    question_id = f"eq_{idx:05d}"
                    question_content = item.get("question", "")
                    correct_answer = item.get("correct_answer", "")
                    categories = item.get("categories", [])
                    category = categories[0] if categories else "未分类"
                    sub_categories = ",".join(categories[1:]) if len(categories) > 1 else None

                    existing = await question_repo.get_by_id(question_id)
                    if existing:
                        skipped += 1
                        continue

                    if not self.dry_run:
                        await question_repo.create(
                            id=question_id,
                            content=question_content[:500],
                            question_type=item.get("question_type", "calculation"),
                            answer=correct_answer or "",
                            analysis=item.get("notes", ""),
                            category=category,
                            sub_categories=sub_categories,
                            difficulty=item.get("mastery_level", 3),
                            source="error_book_migration",
                            is_active=True,
                        )

                    migrated += 1
                    details.append(
                        {
                            "question_id": question_id,
                            "category": category,
                            "status": "success" if not self.dry_run else "dry_run",
                        }
                    )

                except Exception as e:
                    errors += 1
                    details.append({"index": idx, "error": str(e)})
                    logger.error(f"迁移错题数据 [{idx}] 失败: {e}")

        self.reports.append(
            MigrationReport(
                source=str(source_file),
                target="questions",
                total_source_records=len(error_items),
                migrated=migrated,
                skipped=skipped,
                errors=errors,
                details=details,
            )
        )

    async def _migrate_users_from_auth_file(self) -> None:
        auth_file = Path("data/users.json")
        if not auth_file.exists():
            logger.info("未找到用户数据文件，跳过迁移")
            return

        logger.info(f"发现用户数据: {auth_file}")

        try:
            with open(auth_file, "r", encoding="utf-8") as f:
                users_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"读取用户数据失败: {e}")
            return

        if not isinstance(users_data, list):
            users_data = [users_data] if isinstance(users_data, dict) else []

        migrated = 0
        skipped = 0
        errors = 0
        details = []

        async with get_db_session() as db:
            user_repo = UserRepository(db)

            for user_data in users_data:
                try:
                    username = user_data.get("username", "")
                    if not username:
                        continue

                    existing = await user_repo.get_by_username(username)
                    if existing:
                        skipped += 1
                        continue

                    if not self.dry_run:
                        await user_repo.create(
                            username=username,
                            email=user_data.get("email", f"{username}@localhost"),
                            password_hash=user_data.get("password_hash", ""),
                            role=user_data.get("role", "student"),
                            is_active=True,
                            is_verified=True,
                            preferences=user_data.get("preferences", {}),
                        )

                    migrated += 1
                    details.append(
                        {
                            "username": username,
                            "role": user_data.get("role", "student"),
                            "status": "success" if not self.dry_run else "dry_run",
                        }
                    )

                except Exception as e:
                    errors += 1
                    details.append({"username": user_data.get("username", "unknown"), "error": str(e)})
                    logger.error(f"迁移用户数据失败: {e}")

        self.reports.append(
            MigrationReport(
                source=str(auth_file),
                target="users",
                total_source_records=len(users_data),
                migrated=migrated,
                skipped=skipped,
                errors=errors,
                details=details,
            )
        )

    async def _migrate_static_backup(self) -> None:
        backup_dir = Path("backup/static_backup")
        if not backup_dir.exists():
            return

        logger.info(f"发现静态备份目录: {backup_dir}")
        logger.info("静态备份文件保留在原位置，无需迁移到数据库")


async def verify_migration() -> Dict[str, Any]:
    await init_db()

    verification_results = {}

    async with get_db_session() as db:
        user_repo = UserRepository(db)
        question_repo = QuestionRepository(db)
        record_repo = LearningRecordRepository(db)

        user_count = await user_repo.count()
        question_count = await question_repo.count()
        record_count = await record_repo.count()

        verification_results = {
            "users": user_count,
            "questions": question_count,
            "learning_records": record_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        error_book_file = Path("data/error_book.json")
        if error_book_file.exists():
            try:
                with open(error_book_file, "r", encoding="utf-8") as f:
                    items = json.load(f)
                verification_results["error_book_source_count"] = len(items)
            except Exception:
                pass

        users_file = Path("data/users.json")
        if users_file.exists():
            try:
                with open(users_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                verification_results["users_source_count"] = (
                    len(data) if isinstance(data, list) else 1
                )
            except Exception:
                pass

    logger.info(f"迁移验证结果: {verification_results}")
    return verification_results


async def run_migration_cli():
    import argparse

    parser = argparse.ArgumentParser(description="数学AI助手 - 数据迁移工具")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预演模式，不实际写入数据",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="验证迁移结果",
    )

    args = parser.parse_args()

    if args.verify:
        result = await verify_migration()
        print("\n迁移验证结果:")
        for key, value in result.items():
            print(f"  {key}: {value}")
        return

    migrator = DataMigrator(dry_run=args.dry_run)
    await migrator.run_all_migrations()


if __name__ == "__main__":
    asyncio.run(run_migration_cli())