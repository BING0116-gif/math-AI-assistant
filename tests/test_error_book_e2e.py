# -*- coding: utf-8 -*-
"""
错题本答案解析功能 - 端到端集成测试（简化版）
完整验证从前端提取到后端存储的核心流程
"""

import asyncio
import unittest
import json
import sys
import os
import re
import tempfile
import shutil
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from error_book import ErrorItem, ErrorBookManager


# 模块级数据库初始化
def setUpModule():
    """在所有测试前初始化数据库"""
    import tempfile
    test_dir = tempfile.mkdtemp()
    os.environ["ASYNC_DATABASE_URL"] = f"sqlite+aiosqlite:///{test_dir}/test_error_book_e2e.db"
    from app.data.database import init_db
    asyncio.run(init_db())
    # 创建测试用户，确保外键约束满足
    from app.middleware.auth import register_user
    user = asyncio.run(register_user("test_user", "test_password"))
    # 保存用户 ID 供测试使用（register_user 返回的 user.id 是 UUID）
    global _test_user_id
    _test_user_id = user.id if user else "test_user"


def get_test_user_id():
    """获取测试用户 ID（UUID）。"""
    try:
        return _test_user_id
    except NameError:
        return "test_user"


class TestCoreAnswerExtraction(unittest.TestCase):
    """核心答案提取和存储测试"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.data_file = os.path.join(self.test_dir, "test_error_book.json")
        self.manager = ErrorBookManager()

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_detailed_answer_preservation(self):
        """测试详细答案在存储过程中的完整性"""
        detailed_answer = """## 详细解析

### 解题思路
采用极值问题求解方法

### 基础解法
1. 求导数: y' = 2x
2. 计算面积并求最大值

**结果**: 切点坐标 (4, 16)
"""
        item = ErrorItem(
            id="test001",
            question="求抛物线上一点使面积最大",
            question_type="text",
            correct_answer=detailed_answer,
            error_reason="忘记用导数",
            categories=["导数"],
        )

        error_id = asyncio.run(self.manager.add(get_test_user_id(), item))
        loaded = asyncio.run(self.manager.get(get_test_user_id(), error_id))

        self.assertIsNotNone(loaded)
        self.assertIn("详细解析", loaded.correct_answer)
        self.assertIn("基础解法", loaded.correct_answer)
        self.assertIn("(4, 16)", loaded.correct_answer)

    def test_incomplete_answer_detection(self):
        """测试不完整答案的检测"""
        incomplete_patterns = [
            ("**【最终答案】**", True),
            ("【最终答案】", True),
            ("**答案**：", True),
            ("完整解析内容", False),
            ("这是详细的解题过程...", False),
        ]

        patterns_to_check = [
            r'^\*\*【最终答案】\*\*$',
            r'^【最终答案】$',
            r'^\*\*答案\*\*[：:]\s*$',
        ]

        for answer, should_be_incomplete in incomplete_patterns:
            with self.subTest(answer=answer):
                is_incomplete = any(
                    re.match(pattern, answer.strip(), re.IGNORECASE)
                    for pattern in patterns_to_check
                )
                self.assertEqual(is_incomplete, should_be_incomplete)

    def test_data_persistence_operations(self):
        """测试CRUD操作的数据完整性"""
        original_answer = "### 步骤\n\n1. 求导 f'(x)\n2. 找极值点\n\n**结论**: x=0是极小值点"

        # Create
        item = ErrorItem(
            id="persist_test",
            question="求函数极值",
            question_type="text",
            correct_answer=original_answer,
            error_reason="计算错误",
        )
        item_id = asyncio.run(self.manager.add(get_test_user_id(), item))

        # Read
        loaded = asyncio.run(self.manager.get(get_test_user_id(), item_id))
        self.assertEqual(loaded.correct_answer, original_answer)

        # Update (should not affect correct_answer)
        asyncio.run(self.manager.update(get_test_user_id(), item_id, error_reason="理解错误", mastery_level=4))
        updated = asyncio.run(self.manager.get(get_test_user_id(), item_id))
        self.assertEqual(updated.correct_answer, original_answer)
        self.assertEqual(updated.error_reason, "理解错误")

        # List all
        all_items = asyncio.run(self.manager.get_all(get_test_user_id()))
        self.assertEqual(len(all_items), 1)
        self.assertEqual(all_items[0].correct_answer, original_answer)


class TestBackendProtectionMechanism(unittest.TestCase):
    """后端保护机制测试"""

    def test_detect_title_only_answers(self):
        """测试检测只有标题标记的答案"""
        title_only_answers = [
            "**【最终答案】**",
            "【最终答案】",
            "**答案**：",
            "**正确答案**：",
            "答案：",
            "最终答案：",
        ]

        detection_patterns = [
            r'^\*\*【最终答案】\*\*$',
            r'^【最终答案】$',
            r'^\*\*答案\*\*[：:]\s*$',
            r'^\*\*正确答案\*\*[：:]\s*$',
            r'^答案[：:]\s*$',
            r'^最终答案[：:]\s*$',
        ]

        for answer in title_only_answers:
            with self.subTest(answer=answer):
                is_detected = any(
                    re.match(pattern, answer.strip(), re.IGNORECASE)
                    for pattern in detection_patterns
                )
                self.assertTrue(is_detected, f"应检测到不完整答案: {answer}")

    def test_valid_answers_not_false_positive(self):
        """确保有效答案不会被误判"""
        valid_answers = [
            "**【最终答案】**\n\n正确答案是 (4, 16)",
            "【最终答案】\n\nx = 5 是方程的根",
            "**答案**：根据计算...",
            "这是一段完整的解析内容",
            "### 解析过程\n\n步骤1...\n\n**【最终答案】**\n\n结果",
        ]

        detection_patterns = [
            r'^\*\*【最终答案】\*\*$',
            r'^【最终答案】$',
            r'^\*\*答案\*\*[：:]\s*$',
        ]

        for answer in valid_answers:
            with self.subTest(answer=answer[:50]):
                is_false_positive = any(
                    re.match(pattern, answer.strip(), re.IGNORECASE)
                    for pattern in detection_patterns
                )
                self.assertFalse(is_false_positive, f"不应误判有效答案: {answer[:50]}")


class TestDataIntegrity(unittest.TestCase):
    """数据完整性测试"""

    def test_special_characters_handling(self):
        """测试特殊字符处理"""
        content_with_special_chars = """公式测试:

行内: $E = mc^2$

块级:
$$\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}$$

**加粗** 和 *斜体*

- 列表项
"""

        test_dir = tempfile.mkdtemp()
        try:
            manager = ErrorBookManager()

            item = ErrorItem(
                id="special_test",
                question="特殊字符测试",
                question_type="text",
                correct_answer=content_with_special_chars,
            )
            item_id = asyncio.run(manager.add(get_test_user_id(), item))
            loaded = asyncio.run(manager.get(get_test_user_id(), item_id))

            self.assertIn("$E = mc^2$", loaded.correct_answer)
            self.assertIn("**加粗**", loaded.correct_answer)
            self.assertIn("- 列表项", loaded.correct_answer)
        finally:
            shutil.rmtree(test_dir)

    def test_large_content_handling(self):
        """测试大容量内容"""
        large_content = "详细解析内容。" * 500  # 约4000字符

        test_dir = tempfile.mkdtemp()
        try:
            manager = ErrorBookManager()

            item = ErrorItem(
                id="large_test",
                question="大容量测试",
                question_type="text",
                correct_answer=large_content,
            )
            item_id = asyncio.run(manager.add(get_test_user_id(), item))
            loaded = asyncio.run(manager.get(get_test_user_id(), item_id))

            self.assertGreater(len(loaded.correct_answer), 3000)
            self.assertIn("详细解析内容", loaded.correct_answer)
        finally:
            shutil.rmtree(test_dir)


class TestChatSourceIdempotency(unittest.TestCase):
    """聊天来源稳定 item_id 的幂等去重（防刷新后重复入库）。"""

    def setUp(self):
        # 独立注册用户，与同模块共享 DB 的其他用例隔离
        from app.middleware.auth import register_user
        username = f"dup_{uuid.uuid4().hex[:8]}"
        user = asyncio.run(register_user(username, "test_password"))
        self.user_id = user.id
        self.manager = ErrorBookManager()

    def test_add_with_stable_id_is_idempotent(self):
        stable_id = "chat:" + uuid.uuid4().hex[:12]
        first = asyncio.run(self.manager.add(self.user_id, ErrorItem(
            id=stable_id, question="求极限 lim x->0 sin x / x",
            question_type="text", correct_answer="1", error_reason="概念不清",
        )))
        second = asyncio.run(self.manager.add(self.user_id, ErrorItem(
            id=stable_id, question="同一个问题重新加入",
            question_type="text", correct_answer="1",
        )))
        self.assertEqual(first, second)
        items = [i for i in asyncio.run(self.manager.get_all(self.user_id)) if i.id == stable_id]
        self.assertEqual(len(items), 1)
        # 幂等保留首次入库内容，第二次不覆盖
        self.assertEqual(items[0].question, "求极限 lim x->0 sin x / x")

    def test_empty_id_still_creates_distinct_rows(self):
        # 空 ID（手动/其他来源）仍逐条新增，行为不变
        a = asyncio.run(self.manager.add(self.user_id, ErrorItem(
            id="", question="题 A", question_type="text", correct_answer="x")))
        b = asyncio.run(self.manager.add(self.user_id, ErrorItem(
            id="", question="题 B", question_type="text", correct_answer="y")))
        self.assertNotEqual(a, b)
        self.assertEqual(len(asyncio.run(self.manager.get_all(self.user_id))), 2)

    def test_unique_index_rejects_duplicate_user_item_id(self):
        # 并发防护边界：绕过应用层预检查，DB 唯一索引 (user_id, item_id)
        # 必须拒绝第二条，否则“刷新后并发双发”会重复入库。
        from app.data.database import async_session_factory
        from app.data.models import ErrorItem as ErrorItemModel
        from sqlalchemy.exc import IntegrityError

        stable = "chat:" + uuid.uuid4().hex[:12]

        async def _run():
            async with async_session_factory() as s:
                s.add(ErrorItemModel(user_id=self.user_id, item_id=stable, question="q1"))
                await s.commit()
            async with async_session_factory() as s:
                s.add(ErrorItemModel(user_id=self.user_id, item_id=stable, question="q2"))
                with self.assertRaises(IntegrityError):
                    await s.commit()

        asyncio.run(_run())

    def test_concurrent_same_source_id_yields_single_row(self):
        # 端到端并发证据：同一瞬间并发发起 N 个相同 chat:<hash> 的 add()。
        # 无论各请求走“SELECT 预检查命中”还是“越过预检查撞唯一索引后
        # IntegrityError 优雅回退”，最终结果都必须一致：库里仅 1 行、
        # 无异常冒泡（不会 500）、全部返回同一稳定 id。
        stable = "chat:" + uuid.uuid4().hex[:12]

        async def _one(idx: int):
            return await self.manager.add(self.user_id, ErrorItem(
                id=stable, question=f"并发双发 #{idx}",
                question_type="text", correct_answer="1",
            ))

        async def _run():
            return await asyncio.gather(*(_one(i) for i in range(8)))

        results = asyncio.run(_run())
        # 无异常冒泡，且全部返回同一稳定 id
        self.assertEqual(set(results), {stable})
        # 库里该来源键只有 1 行（幂等 + 唯一索引双保险）
        items = [i for i in asyncio.run(self.manager.get_all(self.user_id))
                 if i.id == stable]
        self.assertEqual(len(items), 1)


if __name__ == '__main__':
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    unittest.main(verbosity=2)
