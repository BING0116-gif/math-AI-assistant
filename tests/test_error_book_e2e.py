# -*- coding: utf-8 -*-
"""
错题本答案解析功能 - 端到端集成测试（简化版）
完整验证从前端提取到后端存储的核心流程
"""

import unittest
import json
import sys
import os
import re
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from error_book import ErrorItem, ErrorBookManager


class TestCoreAnswerExtraction(unittest.TestCase):
    """核心答案提取和存储测试"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.data_file = os.path.join(self.test_dir, "test_error_book.json")
        self.manager = ErrorBookManager(data_file=self.data_file)

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

        error_id = self.manager.add(item)
        loaded = self.manager.get(error_id)

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
        item_id = self.manager.add(item)

        # Read
        loaded = self.manager.get(item_id)
        self.assertEqual(loaded.correct_answer, original_answer)

        # Update (should not affect correct_answer)
        self.manager.update(item_id, error_reason="理解错误", mastery_level=4)
        updated = self.manager.get(item_id)
        self.assertEqual(updated.correct_answer, original_answer)
        self.assertEqual(updated.error_reason, "理解错误")

        # List all
        all_items = self.manager.get_all()
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
            data_file = os.path.join(test_dir, "special.json")
            manager = ErrorBookManager(data_file=data_file)

            item = ErrorItem(
                id="special_test",
                question="特殊字符测试",
                question_type="text",
                correct_answer=content_with_special_chars,
            )
            item_id = manager.add(item)
            loaded = manager.get(item_id)

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
            data_file = os.path.join(test_dir, "large.json")
            manager = ErrorBookManager(data_file=data_file)

            item = ErrorItem(
                id="large_test",
                question="大容量测试",
                question_type="text",
                correct_answer=large_content,
            )
            item_id = manager.add(item)
            loaded = manager.get(item_id)

            self.assertGreater(len(loaded.correct_answer), 3000)
            self.assertIn("详细解析内容", loaded.correct_answer)
        finally:
            shutil.rmtree(test_dir)


if __name__ == '__main__':
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

    unittest.main(verbosity=2)
