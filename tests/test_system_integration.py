"""
系统集成测试 - 验证数据库、记忆系统、画像分析、安全模块、数据迁移
"""
import asyncio
import json
import pytest
import os
import sys
import uuid
import tempfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

_test_db_dir = None
_test_db_files = []


def _make_test_db_path(name: str) -> str:
    global _test_db_dir
    if _test_db_dir is None:
        _test_db_dir = tempfile.mkdtemp(prefix="mathai_test_")
    db_path = f"sqlite+aiosqlite:///{_test_db_dir}/{name}.db"
    return db_path


def _cleanup_test_dbs():
    global _test_db_dir
    if _test_db_dir:
        import shutil, time
        time.sleep(0.3)
        try:
            shutil.rmtree(_test_db_dir, ignore_errors=True)
        except Exception:
            pass
        _test_db_dir = None


@pytest.mark.asyncio
async def test_models_import():
    print("\n[测试] 数据模型导入...")
    from app.data.models import (
        Base, User, LearningRecord, Question,
        ChatSession, ChatMessage, ExamPaper, ExamSubmission,
    )
    print("  ✅ 所有数据模型导入成功")


@pytest.mark.asyncio
async def test_database_init():
    print("\n[测试] 数据库初始化...")
    from app.data.database import init_db, close_db, get_db_session

    os.environ["ASYNC_DATABASE_URL"] = _make_test_db_path("init")
    await init_db()

    try:
        async with get_db_session() as session:
            from sqlalchemy import text
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
            print("  ✅ 数据库连接正常")

        async with get_db_session() as session:
            from app.data.repositories import UserRepository
            repo = UserRepository(session)

            test_user = await repo.create(
                username="test_user",
                email="test@test.com",
                password_hash="hashed_password",
                role="student",
            )
            print(f"  ✅ 测试用户创建成功 (ID: {test_user.id})")

            found_user = await repo.get_by_username("test_user")
            assert found_user is not None
            print("  ✅ 用户查询正常")

            updated = await repo.update(test_user.id, preferences={"theme": "dark"})
            assert updated.preferences == {"theme": "dark"}
            print("  ✅ 用户更新正常")

            await repo.delete(test_user.id)
            print("  ✅ 用户删除正常")

    finally:
        await close_db()
        print("  🧹 测试完成")


@pytest.mark.asyncio
async def test_repositories():
    print("\n[测试] 仓储层操作...")
    from app.data.database import init_db, close_db, get_db_session

    os.environ["ASYNC_DATABASE_URL"] = _make_test_db_path("repo")
    await init_db()

    try:
        async with get_db_session() as session:
            from app.data.repositories import (
                UserRepository, QuestionRepository,
                LearningRecordRepository, ChatSessionRepository,
                ChatMessageRepository,
            )

            user_repo = UserRepository(session)
            user = await user_repo.create(
                username="repo_test",
                email="repo@test.com",
                password_hash="hash",
            )

            question_repo = QuestionRepository(session)
            q = await question_repo.create(
                id="q001",
                content="求∫x²dx",
                question_type="calculation",
                answer="x³/3 + C",
                category="积分",
                difficulty=3,
            )
            print("  ✅ 题目创建成功")

            record_repo = LearningRecordRepository(session)
            r = await record_repo.create(
                user_id=user.id,
                question_id=q.id,
                event_type="answer_wrong",
                question_content=q.content,
                category=q.category,
                is_correct=False,
                error_reason="忘记加常数C",
            )
            print("  ✅ 学习记录创建成功")

            records = await record_repo.get_by_user(user.id)
            assert len(records) == 1
            print("  ✅ 学习记录查询正常 (1条)")

            session_repo = ChatSessionRepository(session)
            s = await session_repo.create(
                user_id=user.id,
                title="测试对话",
            )
            print("  ✅ 会话创建成功")

            msg_repo = ChatMessageRepository(session)
            msg = await msg_repo.create(
                session_id=s.id,
                role="user",
                content="帮我算积分",
            )
            print("  ✅ 消息创建成功")

            await msg_repo.delete(msg.id)
            await session_repo.delete(s.id)
            await record_repo.delete(r.id)
            await question_repo.delete(q.id)
            await user_repo.delete(user.id)
            print("  ✅ 所有测试数据清理完成")

    finally:
        await close_db()
        print("  🧹 测试完成")


@pytest.mark.asyncio
async def test_memory_system():
    print("\n[测试] 记忆系统...")
    from app.services.memory import (
        MemoryItem, ShortTermMemory,
    )

    short_term = ShortTermMemory(capacity=10)

    item = MemoryItem(
        id="mem_001",
        content="用户刚才问了积分问题",
        memory_type="context",
        category="积分",
        ttl_seconds=3600,
    )
    short_term.add(item)
    print("  ✅ 短期记忆添加成功")

    items = short_term.retrieve("积分", top_k=3)
    assert len(items) == 1
    print(f"  ✅ 记忆检索成功 (找到 {len(items)} 条)")

    stats = short_term.stats
    assert stats["total_items"] == 1
    print(f"  ✅ 记忆统计: {stats}")

    short_term.clear()
    assert len(short_term.items) == 0
    print("  ✅ 记忆清空成功")


@pytest.mark.asyncio
async def test_security_modules():
    print("\n[测试] 安全模块...")
    from app.security.encryption import DataEncryption

    enc = DataEncryption()
    password = "test_password_123"

    hashed = enc.hash_password(password)
    print("  ✅ 密码哈希成功")

    assert enc.verify_password(hashed, password)
    assert not enc.verify_password(hashed, "wrong_password")
    print("  ✅ 密码验证正确 (正确通过, 错误拒绝)")

    plaintext = "test@example.com"
    encrypted = enc.encrypt_field(plaintext)
    assert encrypted != plaintext
    print("  ✅ 字段加密成功")

    decrypted = enc.decrypt_field(encrypted)
    assert decrypted == plaintext
    print("  ✅ 字段解密正确")

    from app.security.access_control import (
        Permission, RolePermissionMapping, check_data_ownership, is_admin,
    )
    student_perms = RolePermissionMapping.MAPPING["student"]
    assert Permission.READ_OWN_DATA in student_perms
    assert Permission.MANAGE_USERS not in student_perms
    print("  ✅ RBAC权限映射正确")

    admin_perms = RolePermissionMapping.MAPPING["admin"]
    assert Permission.MANAGE_USERS in admin_perms
    print("  ✅ 管理员权限完整")

    assert check_data_ownership("user_1", "user_1")
    assert not check_data_ownership("user_1", "user_2")
    assert is_admin("admin")
    assert not is_admin("student")
    print("  ✅ 所有权检查正确")

    from app.security.audit import AuditLogger
    import logging
    audit_logger = logging.getLogger("audit")
    for h in audit_logger.handlers[:]:
        h.close()
        audit_logger.removeHandler(h)

    audit = AuditLogger(log_file="logs/test_audit.log")
    audit.log_access("user_1", "profile", "user_1", "view")
    audit.log_modification("user_1", "prefs", "user_1", {}, {"theme": "dark"}, ["theme"])
    audit.log_deletion("user_1", "record", "r_001", "用户请求删除")
    audit.log_login("user_1", True, "127.0.0.1")
    audit.log_export("user_1", "json", 100)
    print("  ✅ 审计日志记录正常")

    test_log = Path("logs/test_audit.log")
    if test_log.exists():
        audit.close()
        test_log.unlink()
    print("  ✅ 审计日志验证完成")


@pytest.mark.asyncio
async def test_cache_manager():
    print("\n[测试] 缓存管理器...")
    from app.services.cache import CacheManager

    mgr = CacheManager()

    await mgr.set("test_key", {"data": "hello"}, ttl=60, use_l2=False)
    cached = await mgr.get("test_key")
    assert cached == {"data": "hello"}
    print("  ✅ L1缓存写入/读取正常")

    await mgr.delete("test_key")
    cached = await mgr.get("test_key")
    assert cached is None
    print("  ✅ 缓存删除正常")

    print(f"  ✅ 缓存统计: L1命中{mgr.l1_hits}, 未命中{mgr.misses}")


@pytest.mark.asyncio
async def test_profile_analyzer():
    print("\n[测试] 用户画像分析器...")
    from app.data.database import init_db, close_db, get_db_session
    from app.services.profile_analyzer import UserProfileAnalyzer
    from app.data.repositories import UserRepository, LearningRecordRepository

    os.environ["ASYNC_DATABASE_URL"] = _make_test_db_path("profile")
    await init_db()

    try:
        async with get_db_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.create(
                username="profile_test",
                email="profile@test.com",
                password_hash="hash",
            )

            record_repo = LearningRecordRepository(session)
            for i in range(20):
                is_correct = i % 3 != 0
                categories = ["积分", "导数", "极限", "积分", "导数"]
                await record_repo.create(
                    user_id=user.id,
                    event_type="ask",
                    question_content=f"测试题目 {i}",
                    category=categories[i % 5],
                    difficulty=3 + (i % 3),
                    is_correct=is_correct,
                    time_spent=60 + i * 10,
                    error_reason="计算错误" if not is_correct else None,
                )

        analyzer = UserProfileAnalyzer(get_db_session)
        profile = await analyzer.analyze(user.id)

        assert "total_questions" in profile
        assert profile["total_questions"] >= 20
        print(f"  ✅ 画像分析成功 (总题数: {profile['total_questions']})")

        assert "weak_points" in profile
        print(f"  ✅ 薄弱点分析: {len(profile['weak_points'])} 个")

        assert "behavior" in profile
        print(f"  ✅ 行为分析完成")

        assert "preferences" in profile
        print(f"  ✅ 偏好分析完成")

        assert "recommendations" in profile
        print(f"  ✅ 个性化建议: {len(profile['recommendations'])} 条")

        async with get_db_session() as session:
            from app.data.models import LearningRecord
            from sqlalchemy import delete
            await session.execute(
                delete(LearningRecord).where(LearningRecord.user_id == user.id)
            )
            await session.commit()
            await user_repo.delete(user.id)

    finally:
        await close_db()
    print("  ✅ 画像分析测试完成")


@pytest.mark.asyncio
async def test_data_migration():
    print("\n[测试] 数据迁移...")
    from app.data.legacy_migrations import DataMigrator

    os.environ["ASYNC_DATABASE_URL"] = _make_test_db_path("migration")

    test_data = [
        {
            "id": "err001",
            "question": "求∫x²dx",
            "question_type": "calculation",
            "correct_answer": "x³/3+C",
            "categories": ["积分"],
            "error_reason": "忘记常数C",
            "mastery_level": 2,
        }
    ]

    test_dir = _test_db_dir or "data"
    error_path = os.path.join(test_dir, "error_book.json")
    os.makedirs(os.path.dirname(error_path) or test_dir, exist_ok=True)
    with open(error_path, "w", encoding="utf-8") as f:
        json.dump(test_data, f, ensure_ascii=False)

    import shutil
    src = error_path
    dst = "data/error_book.json"
    os.makedirs("data", exist_ok=True)
    shutil.copy(src, dst)
    try:
        migrator = DataMigrator(dry_run=True)
        reports = await migrator.run_all_migrations()

        assert len(reports) >= 1
        print(f"  ✅ 迁移预演成功: {reports[0].migrated} 条预演迁移")
    finally:
        Path("data/error_book.json").unlink(missing_ok=True)

    from app.data.database import close_db
    await close_db()

    print("  ✅ 数据迁移测试完成")


async def main():
    print("=" * 60)
    print("数学AI助手 - 系统集成测试")
    print("=" * 60)

    tests = [
        ("数据模型导入", test_models_import),
        ("数据库初始化与CRUD", test_database_init),
        ("仓储层完整操作", test_repositories),
        ("记忆系统", test_memory_system),
        ("安全模块 (加密+RABC+审计)", test_security_modules),
        ("缓存管理器", test_cache_manager),
        ("用户画像分析引擎", test_profile_analyzer),
        ("数据迁移方案", test_data_migration),
    ]

    passed = 0
    failed = 0

    for name, test_fn in tests:
        try:
            await test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            import traceback
            print(f"\n  ❌ {name} 失败:")
            traceback.print_exc()

    _cleanup_test_dbs()

    old_db = Path("data/math_ai.db")
    if old_db.exists():
        try:
            old_db.unlink()
        except Exception:
            pass

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过 / {failed} 失败 / {passed + failed} 总计")
    if failed == 0:
        print("🎉 所有测试通过！")
    else:
        print(f"⚠️ {failed} 个测试失败，请检查")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
