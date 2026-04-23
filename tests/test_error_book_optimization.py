# -*- coding: utf-8 -*-
"""
错题本功能优化 - 单元测试
验证数据校验、格式化和API接口的正确性
"""

import pytest
import sys
import os

# 添加项目根目录到系统路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_processing.validators import ErrorBookValidator
from data_processing.formatters import ErrorBookFormatter


class TestErrorBookValidator:
    """数据校验模块测试"""

    def test_valid_text_error(self):
        """测试有效的文本类型错题数据"""
        data = {
            "question": "求积分 ∫x²dx",
            "question_type": "text",
            "correct_answer": "(x³)/3 + C",
            "error_reason": "忘记加常数C"
        }
        is_valid, errors = ErrorBookValidator.validate(data)
        assert is_valid is True
        assert len(errors) == 0

    def test_valid_image_error(self):
        """测试有效的图片类型错题数据"""
        # 简化的base64图片数据
        base64_data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="

        data = {
            "question": base64_data,
            "question_type": "image",
            "correct_answer": "答案内容",
            "error_reason": "计算错误"
        }
        is_valid, errors = ErrorBookValidator.validate(data)
        assert is_valid is True
        assert len(errors) == 0

    def test_missing_required_fields(self):
        """测试缺少必填字段"""
        data = {
            "question": "",
            "correct_answer": "",
            "error_reason": ""
        }
        is_valid, errors = ErrorBookValidator.validate(data)
        assert is_valid is False
        assert len(errors) >= 3
        assert any("题目" in err for err in errors)
        assert any("答案" in err for err in errors)
        assert any("原因" in err for err in errors)

    def test_invalid_image_format(self):
        """测试无效的图片格式"""
        data = {
            "question": "not_an_image_data",
            "question_type": "image",
            "correct_answer": "answer",
            "error_reason": "reason"
        }
        is_valid, errors = ErrorBookValidator.validate(data)
        assert is_valid is False
        assert any("图片" in err or "无效" in err for err in errors)

    def test_text_question_with_image_data(self):
        """测试文本类型题目包含图片数据（应该报错）"""
        base64_data = "data:image/png;base64,iVBORw0KGgo="

        data = {
            "question": base64_data,
            "question_type": "text",
            "correct_answer": "answer",
            "error_reason": "reason"
        }
        is_valid, errors = ErrorBookValidator.validate(data)
        assert is_valid is False
        assert any("图片" in err or "不应" in err for err in errors)

    def test_mastery_level_validation(self):
        """测试掌握度范围验证"""
        # 测试有效值
        for level in [1, 2, 3, 4, 5]:
            data = {
                "question": "test",
                "correct_answer": "ans",
                "error_reason": "reason",
                "mastery_level": level
            }
            is_valid, _ = ErrorBookValidator.validate(data)
            assert is_valid is True

        # 测试超出范围的值
        data_invalid_high = {
            "question": "test",
            "correct_answer": "ans",
            "error_reason": "reason",
            "mastery_level": 6
        }
        is_valid, errors = ErrorBookValidator.validate(data_invalid_high)
        assert is_valid is False
        assert any("掌握度" in err or "1-5" in err for err in errors)

    def test_field_length_validation(self):
        """测试字段长度限制"""
        long_text = "a" * 10001  # 超过限制

        data = {
            "question": long_text,
            "correct_answer": "answer",
            "error_reason": "reason"
        }
        is_valid, errors = ErrorBookValidator.validate(data)
        assert is_valid is False
        assert any("长度" in err or "超过" in err for err in errors)

    def test_sanitize_string(self):
        """测试字符串清理功能"""
        # 测试空白清理
        result = ErrorBookValidator.sanitize_string("  hello  world  ")
        assert result == "hello world"

        # 测试长度限制
        long_string = "a" * 200
        result = ErrorBookValidator.sanitize_string(long_string, max_length=100)
        assert len(result) == 100

    def test_validate_categories(self):
        """测试分类标签验证"""
        # 有效分类
        is_valid, error = ErrorBookValidator.validate_categories(["极限", "导数"])
        assert is_valid is True
        assert error == ""

        # 分类数量过多
        many_cats = ["cat"] * 11
        is_valid, error = ErrorBookValidator.validate_categories(many_cats)
        assert is_valid is False
        assert "10" in error

        # 非法字符
        is_valid, error = ErrorBookValidator.validate_categories(["正常标签", "<script>"])
        assert is_valid is False
        assert "非法" in error


class TestErrorBookFormatter:
    """数据格式化模块测试"""

    def test_format_text_question(self):
        """测试文本类型题目格式化"""
        data = {
            "question": "<p>求  lim(x→0) sin(x)/x</p>",
            "question_type": "text",
            "correct_answer": "$$\\lim_{x\\to 0}\\frac{\\sin x}{x}=1$$"
        }

        formatted = ErrorBookFormatter.format(data)

        # 验证基本字段存在
        assert 'display_question' in formatted
        assert 'answer_preview' in formatted
        assert 'has_image' in formatted
        assert 'categories' in formatted

        # 验证处理结果
        assert formatted['has_image'] is False
        assert '<p>' not in formatted['display_question']
        assert '[公式]' in formatted['answer_preview']

    def test_format_image_question(self):
        """测试图片类型题目格式化"""
        base64_data = "data:image/png;base64,iVBORw0KGgo="

        data = {
            "question": base64_data,
            "question_type": "image",
            "correct_answer": "【题目】求f(x)=x²的导数\n解答过程..."
        }

        formatted = ErrorBookFormatter.format(data)

        # 验证图片相关字段
        assert formatted['has_image'] is True
        assert formatted.get('raw_image_data') == base64_data
        assert 'recognized_text' in formatted
        assert 'display_question' in formatted

    def test_extract_recognized_text_pattern1(self):
        """测试从AI回答中提取题目文本 - 模式1：【题目】标记"""
        answer = "【题目】求函数 f(x)=x² 在 x=1 处的导数\n\n解答：使用求导公式..."

        data = {
            "question": "data:image/png;base64,test",
            "question_type": "image",
            "correct_answer": answer
        }

        formatted = ErrorBookFormatter.format(data)

        assert "求函数 f(x)=x²" in formatted.get('recognized_text', '')

    def test_extract_recognized_text_pattern2(self):
        """测试从AI回答中提取题目文本 - 模式2：问题确认标记"""
        answer = "问题确认：计算定积分 ∫(0 to 1) x²dx\n\n解题步骤..."

        data = {
            "question": "data:image/png;base64,test",
            "question_type": "image",
            "correct_answer": answer
        }

        formatted = ErrorBookFormatter.format(data)

        assert "计算定积分" in formatted.get('recognized_text', '')

    def test_generate_preview_with_latex(self):
        """测试生成带LaTeX的预览文本"""
        text = "解：$$\\int_0^1 x^2 dx = \\frac{1}{3}$$ 所以答案是1/3"

        preview = ErrorBookFormatter._generate_preview(text, max_length=50)

        # 应该将LaTeX替换为[公式]
        assert '\\int' not in preview or '[公式]' in preview
        assert '\\frac' not in preview or '[公式]' in preview
        assert len(preview) <= 53  # 允许"..."的长度

    def test_auto_classification(self):
        """测试自动分类功能"""
        # 测试积分相关
        data_integral = {
            "question": "求积分 ∫x²dx",
            "correct_answer": "原函数是 x³/3",
            "error_reason": ""
        }

        categories = ErrorBookFormatter._auto_classify(data_integral)
        assert "积分" in categories

        # 测试导数相关
        data_derivative = {
            "question": "求导数 dy/dx",
            "correct_answer": "使用链式法则",
            "error_reason": ""
        }

        categories = ErrorBookFormatter._auto_classify(data_derivative)
        assert "导数" in categories

        # 测试无匹配时的默认分类
        data_unknown = {
            "question": "普通问题",
            "correct_answer": "普通回答",
            "error_reason": ""
        }

        categories = ErrorBookFormatter._auto_classify(data_unknown)
        assert "其他" in categories

    def test_process_timestamp(self):
        """测试时间戳处理"""
        from datetime import datetime

        # 测试空时间戳
        data_empty = {"added_at": ""}
        ErrorBookFormatter._process_timestamp(data_empty)
        assert data_empty['added_at'] != ""

        # 测试有效时间戳应保持不变或标准化
        valid_time = "2026-01-15 14:30"
        data_valid = {"added_at": valid_time}
        ErrorBookFormatter._process_timestamp(data_valid)
        assert "2026" in data_valid['added_at']

    def test_clean_html_tags(self):
        """测试HTML标签清理"""
        html_content = "<p>Hello <b>World</b></p><script>alert('xss')</script>"
        cleaned = ErrorBookFormatter._clean_html_tags(html_content)

        assert '<p>' not in cleaned
        assert '<b>' not in cleaned
        assert '<script>' not in cleaned
        assert "Hello World" in cleaned

    def test_clean_latex(self):
        """测试LaTeX清理"""
        latex_text = "\\frac{x}{y} + \\sqrt{x^2}"

        cleaned = ErrorBookFormatter._clean_latex(latex_text)

        # 应该替换常见的LaTeX命令
        assert '\\frac' not in cleaned or '/' in cleaned
        assert '\\sqrt' not in cleaned or '√' in cleaned

    def test_process_categories_auto_fill(self):
        """测试自动填充分类"""
        data_no_categories = {
            "question": "求极限 lim(x→∞) 1/x",
            "correct_answer": "极限值为0",
            "categories": []
        }

        ErrorBookFormatter._process_categories(data_no_categories)

        assert len(data_no_categories['categories']) > 0
        assert "极限" in data_no_categories['categories']


class TestIntegration:
    """集成测试 - 验证完整的数据流程"""

    def test_full_workflow_text_question(self):
        """完整工作流测试：文本类型题目"""
        raw_data = {
            "id": "",
            "question": "   <p>求不定积分 ∫e^x dx</p>   ",
            "question_type": "text",
            "correct_answer": "$$\\int e^x dx = e^x + C$$",
            "error_reason": "  忘记加常数C  ",
            "categories": [],
            "notes": "",
            "mastery_level": 3,
            "is_mastered": False
        }

        # Step 1: 校验
        is_valid, validation_errors = ErrorBookValidator.validate(raw_data)
        assert is_valid is True, f"校验失败: {validation_errors}"

        # Step 2: 格式化
        formatted = ErrorBookFormatter.format(raw_data)

        # Step 3: 验证格式化后的数据
        assert formatted['question_type'] == 'text'
        assert formatted['has_image'] is False
        assert '<p>' not in formatted['display_question']
        assert formatted['error_reason'].strip() != ""  # 不应为空
        assert len(formatted['categories']) > 0  # 应该有自动分类
        assert '积分' in formatted['categories']  # 应识别出积分类别

    def test_full_workflow_image_question(self):
        """完整工作流测试：图片类型题目"""
        base64_img = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUAAAAFCAYAAACNbyblAAAAHElEQVQI12P4//8/w38GIAXDIBKE0DHxgljNBAAO9TXL0Y4OHwAAAABJRU5ErkJggg=="

        raw_data = {
            "id": "",
            "question": base64_img,
            "question_type": "image",
            "correct_answer": "【题目】求解微分方程 y'' + y = 0\n\n通解为 y = C₁cosx + C₂sinx",
            "error_reason": "忘记特征方程的解法",
            "categories": [],
            "notes": "需要复习微分方程章节",
            "mastery_level": 2,
            "is_mastered": False
        }

        # Step 1: 校验
        is_valid, validation_errors = ErrorBookValidator.validate(raw_data)
        assert is_valid is True, f"校验失败: {validation_errors}"

        # Step 2: 格式化
        formatted = ErrorBookFormatter.format(raw_data)

        # Step 3: 验证
        assert formatted['has_image'] is True
        assert formatted.get('raw_image_data') == base64_img
        assert 'differential' in formatted['recognized_text'].lower() or '微分方程' in formatted['recognized_text']
        assert '微分方程' in formatted['categories']

    def test_edge_cases(self):
        """边界情况测试"""

        # 1. 超长题目（超过10000字符限制）
        long_question = "a" * 10001
        data_long = {
            "question": long_question,
            "correct_answer": "答案",
            "error_reason": "原因"
        }
        is_valid, errors = ErrorBookValidator.validate(data_long)
        assert is_valid is False  # 应该被拒绝

        # 2. 特殊字符
        special_chars = {
            "question": "求∫∑∂∇∞的运算",
            "correct_answer": "结果是αβγ",
            "error_reason": "符号不熟悉"
        }
        is_valid, _ = ErrorBookValidator.validate(special_chars)
        assert is_valid is True  # 数学符号应该允许

        # 3. 空白字符串
        whitespace_only = {
            "question": "   ",
            "correct_answer": "   ",
            "error_reason": "   "
        }
        is_valid, _ = ErrorBookValidator.validate(whitespace_only)
        assert is_valid is False  # 纯空白应该被视为空


def run_tests():
    """运行所有测试并输出报告"""
    print("=" * 70)
    print("🧪 错题本功能优化 - 单元测试")
    print("=" * 70)

    # 运行pytest
    exit_code = pytest.main([
        __file__,
        '-v',
        '--tb=short',
        '--cov=data_processing',
        '--cov-report=term-missing'
    ])

    return exit_code


if __name__ == "__main__":
    run_tests()
