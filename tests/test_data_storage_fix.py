# -*- coding: utf-8 -*-
"""
数据存储修正 - 单元测试
验证错题本数据的校验和格式化处理是否正确
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
        """测试有效的文本类型错题"""
        data = {
            "question": "求积分 ∫x²dx",
            "question_type": "text",
            "correct_answer": "(x³)/3 + C",
            "error_reason": "忘记加常数C"
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
        assert any("正确答案" in err for err in errors)
        assert any("错误原因" in err for err in errors)

    def test_invalid_image_format(self):
        """测试无效的图片格式"""
        data = {
            "question": "not_an_image_data",
            "question_type": "image",
            "correct_answer": "some answer",
            "error_reason": "reason"
        }
        is_valid, errors = ErrorBookValidator.validate(data)
        
        assert is_valid is False
        assert any("图片" in err for err in errors)

    def test_image_type_with_base64(self):
        """测试有效的base64图片格式"""
        data = {
            "question": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg",
            "question_type": "image",
            "correct_answer": "answer content",
            "error_reason": "reason"
        }
        is_valid, errors = ErrorBookValidator.validate(data)
        
        # 应该通过验证（base64格式有效）
        assert is_valid is True or not any("图片格式无效" in err for err in errors)

    def test_text_with_image_data_mismatch(self):
        """测试文本类型包含图片数据（类型不匹配）"""
        data = {
            "question": "data:image/png;base64,some_data",
            "question_type": "text",  # 声明为文本类型但内容是图片
            "correct_answer": "answer",
            "error_reason": "reason"
        }
        is_valid, errors = ErrorBookValidator.validate(data)
        
        assert is_valid is False
        assert any("不应包含图片数据" in err for err in errors)

    def test_mastery_level_validation(self):
        """测试掌握度值范围验证"""
        # 测试超出范围的掌握度
        data = {
            "question": "test question",
            "correct_answer": "answer",
            "error_reason": "reason",
            "mastery_level": 10  # 超出1-5范围
        }
        is_valid, errors = ErrorBookValidator.validate(data)
        
        assert is_valid is False
        assert any("掌握度" in err and "1-5" in err for err in errors)

    def test_field_length_limit(self):
        """测试字段长度限制"""
        long_question = "x" * 35000  # 超过当前30000字符限制

        data = {
            "question": long_question,
            "correct_answer": "answer",
            "error_reason": "reason"
        }
        is_valid, errors = ErrorBookValidator.validate(data)

        assert is_valid is False
        assert any("长度超过限制" in err for err in errors)

    def test_sanitize_string(self):
        """测试字符串清理功能"""
        dirty_string = "  hello   world  \r\n  "
        cleaned = ErrorBookValidator.sanitize_string(dirty_string)
        
        assert cleaned == "hello world"

    def test_validate_categories(self):
        """测试分类标签验证"""
        # 有效分类
        valid, error = ErrorBookValidator.validate_categories(['极限', '导数', '积分'])
        assert valid is True
        assert error == ''
        
        # 空列表
        valid, error = ErrorBookValidator.validate_categories([])
        assert valid is True
        
        # 超过数量限制
        many_cats = [f'cat{i}' for i in range(15)]
        valid, error = ErrorBookValidator.validate_categories(many_cats)
        assert valid is False
        assert '10' in error


class TestErrorBookFormatter:
    """数据格式化处理器测试"""

    def test_format_text_question(self):
        """测试文本类型题目格式化"""
        data = {
            "question": "<p>求极限 lim(x→0) sin(x)/x</p>",
            "question_type": "text",
            "correct_answer": "$$\\lim_{x\\to 0}\\frac{\\sin x}{x}=1$$",
            "error_reason": "忘记用洛必达法则",
            "categories": []
        }
        
        formatted = ErrorBookFormatter.format(data)
        
        # 验证基本字段保留
        assert formatted['question'] == data['question']
        assert formatted['has_image'] is False
        assert formatted['raw_image_data'] is None
        
        # 验证新增字段
        assert 'display_question' in formatted
        assert '<p>' not in formatted['display_question']  # HTML标签应被清理
        assert 'answer_preview' in formatted
        assert '[公式]' in formatted['answer_preview']  # LaTeX应被替换

    def test_format_image_question(self):
        """测试图片类型题目格式化"""
        base64_data = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9h"
        answer_with_recognized_text = (
            "正在识别图片...\n\n"
            "【题目】\n"
            "设 f(x) = x²，求 f'(x)\n\n"
            "【解答】\nf'(x) = 2x"
        )
        
        data = {
            "question": base64_data,
            "question_type": "image",
            "correct_answer": answer_with_recognized_text,
            "error_reason": "",
            "categories": []
        }
        
        formatted = ErrorBookFormatter.format(data)
        
        # 验证图片相关字段
        assert formatted['has_image'] is True
        assert formatted['raw_image_data'] == base64_data
        assert 'recognized_text' in formatted
        
        # 验证识别文本提取
        recognized = formatted['recognized_text']
        assert len(recognized) > 0
        assert 'f(x)' in recognized or 'x²' in recognized  # 应该提取到题目文本

    def test_extract_recognized_text_from_markers(self):
        """测试从标记中提取识别文本"""
        answer = """
        【题目】
        求函数 y = ln(x) 的导数
        
        【解答】
        y' = 1/x
        """
        
        extracted = ErrorBookFormatter._extract_recognized_text(answer)
        
        assert "ln(x)" in extracted or "导数" in extracted

    def test_extract_recognized_text_from_confirmation(self):
        """测试从问题确认标记中提取"""
        answer = """
        问题确认：计算定积分 ∫₀¹ x² dx
        
        解题步骤...
        """
        
        extracted = ErrorBookFormatter._extract_recognized_text(answer)
        
        assert "定积分" in extracted or "∫₀¹ x²" in extracted

    def test_generate_preview_removes_latex(self):
        """测试预览生成时移除LaTeX标记"""
        text_with_latex = "答案是 $$\\int_0^1 x^2 dx = \\frac{1}{3}$$，其中 $x$ 是变量"
        
        preview = ErrorBookFormatter._generate_preview(text_with_latex)
        
        # LaTeX块应被替换
        assert '$$' not in preview
        assert '\\frac' not in preview
        assert '[公式]' in preview

    def test_auto_classification(self):
        """测试自动分类功能"""
        # 积分相关题目
        integral_data = {
            "question": "求不定积分 ∫x²dx",
            "correct_answer": "使用积分公式...",
            "error_reason": ""
        }
        formatted = ErrorBookFormatter.format(integral_data)
        
        categories = formatted.get('categories', [])
        assert '积分' in categories  # 应该自动检测到积分分类

        # 导数相关题目
        derivative_data = {
            "question": "求函数的导数",
            "correct_answer": "使用导数的定义...",
            "error_reason": ""
        }
        formatted = ErrorBookFormatter.format(derivative_data)
        
        categories = formatted.get('categories', [])
        assert '导数' in categories  # 应该自动检测到导数分类

    def test_timestamp_standardization(self):
        """测试时间戳标准化"""
        # 空时间戳应生成当前时间
        data = {
            "question": "test",
            "correct_answer": "answer",
            "error_reason": "reason",
            "added_at": ""  # 空
        }
        formatted = ErrorBookFormatter.format(data)
        
        assert formatted['added_at'] != ''
        assert len(formatted['added_at']) > 0  # 应该有值

    def test_default_values_for_empty_fields(self):
        """测试空字段的默认值填充"""
        data = {
            "question": "test question",
            "correct_answer": "test answer",
            "error_reason": "",  # 空
            "notes": None,     # None
            "categories": [],  # 空列表
            "mastery_level": None  # None
        }
        
        formatted = ErrorBookFormatter.format(data)
        
        # 验证默认值
        assert formatted['error_reason'] == '未填写'
        assert formatted['notes'] == ''
        assert isinstance(formatted['categories'], list)
        assert len(formatted['categories']) >= 1  # 至少有自动分类
        assert formatted['mastery_level'] == 3  # 默认值

    def test_clean_html_tags(self):
        """测试HTML标签清理"""
        html_text = "<p>Hello <strong>World</strong></p><br/>"
        cleaned = ErrorBookFormatter._clean_html_tags(html_text)
        
        assert '<p>' not in cleaned
        assert '<strong>' not in cleaned
        assert 'Hello World' in cleaned

    def test_clean_latex_commands(self):
        """测试LaTeX命令清理"""
        latex_text = r"\frac{x}{y} + \sqrt{z} + \lim_{x\to 0}"
        cleaned = ErrorBookFormatter._clean_latex(latex_text)
        
        assert '\\frac' not in cleaned
        assert '\\sqrt' not in cleaned
        assert '/' in cleaned or '√' in cleaned  # 应该有可读形式


class TestDataIntegrity:
    """数据完整性保证测试"""

    def test_no_data_loss_after_formatting(self):
        """测试格式化后不丢失原始数据"""
        original_data = {
            "id": "test123",
            "question": "original question text",
            "question_type": "text",
            "correct_answer": "original answer with $$\\int x dx$$",
            "error_reason": "original reason",
            "categories": ["自定义分类"],
            "original_answer": "user's wrong answer",
            "notes": "some notes",
            "added_at": "2026-04-20 10:30",
            "mastery_level": 2,
            "is_mastered": False
        }
        
        formatted = ErrorBookFormatter.format(original_data)
        
        # 验证所有原始字段都保留
        assert formatted['id'] == original_data['id']
        assert formatted['question'] == original_data['question']
        assert formatted['correct_answer'] != ''  # 可能被清理空白但不应丢失
        assert original_data['error_reason'] in formatted['error_reason'] or \
               formatted['error_reason'].startswith(original_data['error_reason'])
        assert formatted['mastery_level'] == original_data['mastery_level']

    def test_new_fields_added(self):
        """测试新字段正确添加"""
        data = {
            "question": "test",
            "correct_answer": "answer",
            "error_reason": "reason"
        }
        
        formatted = ErrorBookFormatter.format(data)
        
        # 检查所有新字段存在
        new_fields = [
            'display_question',
            'answer_preview',
            'has_image',
            'raw_image_data',
            'recognized_text',
            'data_source'
        ]
        
        for field in new_fields:
            assert field in formatted, f"Missing required field: {field}"

    def test_backward_compatibility_with_old_data_format(self):
        """测试与旧数据格式的向后兼容性"""
        # 模拟旧数据格式（来自现有的error_book.json）
        old_format_data = {
            "id": "old123",
            "question": "data:image/png;base64,iVBORw0KGgo...",  # 旧格式：直接存base64
            "question_type": "image",
            "image_path": None,
            "error_reason": "用户主动添加",  # 旧格式：简单原因
            "categories": [],  # 旧格式：空分类
            "original_answer": "",  # 旧格式：空
            "correct_answer": "【题目】某数学题\n\n【解答】详细解答...",  # 有完整答案
            "notes": "",
            "added_at": "2026-04-20 14:20",
            "mastery_level": 3,
            "is_mastered": False
        }
        
        # 格式化应该成功且不报错
        try:
            formatted = ErrorBookFormatter.format(old_format_data)
            
            # 验证关键字段
            assert formatted['id'] == old_format_data['id']
            assert formatted['has_image'] is True
            assert 'display_question' in formatted
            assert len(formatted['categories']) > 0  # 应该自动添加分类
            
        except Exception as e:
            pytest.fail(f"Failed to format old data format: {e}")


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])
