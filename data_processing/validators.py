# -*- coding: utf-8 -*-
"""
数据校验模块 - 错题本数据完整性验证
用于验证错题数据的完整性和格式正确性
"""

import re
import base64
from typing import Tuple, List, Dict, Any


class ErrorBookValidator:
    """错题本数据验证器"""

    # 必填字段列表
    REQUIRED_FIELDS = ['question', 'correct_answer', 'error_reason']

    # 字段最大长度限制
    MAX_LENGTHS = {
        'question': 10000,
        'correct_answer': 50000,
        'error_reason': 2000,
        'original_answer': 5000,
        'notes': 5000,
        'categories': 10,  # 分类数量限制
    }

    @classmethod
    def validate(cls, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        校验错题数据的完整性

        Args:
            data: 待校验的错题数据字典

        Returns:
            (是否有效, 错误信息列表)
            - is_valid: True表示数据有效，False表示存在错误
            - errors: 错误信息列表，为空时表示无错误
        """
        errors = []

        # 1. 检查必填字段是否存在且非空
        for field in cls.REQUIRED_FIELDS:
            value = data.get(field)
            if value is None or (isinstance(value, str) and value.strip() == ''):
                field_names = {
                    'question': '题目',
                    'correct_answer': '正确答案',
                    'error_reason': '错误原因'
                }
                errors.append(f"{field_names.get(field, field)}不能为空")

        # 2. 检查字段长度限制
        length_errors = cls._validate_field_lengths(data)
        errors.extend(length_errors)

        # 3. 检查题目类型与内容匹配
        type_error = cls._validate_question_type(data)
        if type_error:
            errors.append(type_error)

        # 4. 检查掌握度范围
        mastery_error = cls._validate_mastery_level(data)
        if mastery_error:
            errors.append(mastery_error)

        return len(errors) == 0, errors

    @classmethod
    def _validate_field_lengths(cls, data: Dict[str, Any]) -> List[str]:
        """验证各字段长度是否符合要求"""
        errors = []

        for field, max_len in cls.MAX_LENGTHS.items():
            value = data.get(field)

            if value is None:
                continue

            if isinstance(value, str):
                if len(value) > max_len:
                    errors.append(f"{field}字段长度超过限制（{max_len}字符）")

            elif isinstance(value, list):
                if len(value) > max_len:
                    errors.append(f"{field}数量超过限制（{max_len}个）")

        return errors

    @classmethod
    def _validate_question_type(cls, data: Dict[str, Any]) -> str or None:
        """验证题目类型与内容的匹配性"""
        question_type = data.get('question_type', 'text')
        question = data.get('question', '')

        if question_type == 'image':
            # 图片类型：检查是否是有效的图片数据或路径
            if question.startswith('data:image/'):
                # 验证base64格式
                try:
                    base64_data = question.split(',')[1] if ',' in question else question
                    base64.b64decode(base64_data)
                except:
                    return "无效的base64图片数据"
            elif not (question and '.' in question and 
                    question.split('.')[-1].lower() in ['png', 'jpg', 'jpeg', 'gif']):
                return "图片类型题目的数据格式无效"

        elif question_type == 'text':
            # 文本类型：检查是否有实际文本内容
            if not question or question.strip() == '':
                return "文本类型题目不能为空"
            
            # 检查是否误传了图片数据
            if question.startswith('data:image'):
                return "文本类型题目不应包含图片数据，请检查题目类型设置"

        return None

    @classmethod
    def _validate_mastery_level(cls, data: Dict[str, Any]) -> str or None:
        """验证掌握度值是否在有效范围内"""
        mastery = data.get('mastery_level', 3)

        try:
            mastery_int = int(mastery)
            if mastery_int < 1 or mastery_int > 5:
                return f"掌握度必须在1-5之间，当前值为{mastery}"
        except (ValueError, TypeError):
            return f"掌握度必须是数字，当前值为{mastery}"

        return None

    @classmethod
    def sanitize_string(cls, text: str, max_length: int = None) -> str:
        """
        清理和标准化字符串

        Args:
            text: 原始字符串
            max_length: 最大长度限制

        Returns:
            清理后的字符串
        """
        if not text:
            return ''

        # 移除首尾空白
        cleaned = text.strip()

        # 标准化换行符
        cleaned = cleaned.replace('\r\n', '\n').replace('\r', '\n')

        # 将多个连续空格替换为单个空格
        import re
        cleaned = re.sub(r'\s+', ' ', cleaned)

        # 限制长度
        if max_length and len(cleaned) > max_length:
            cleaned = cleaned[:max_length]

        return cleaned

    @classmethod
    def validate_categories(cls, categories: list) -> Tuple[bool, str]:
        """
        验证分类标签的合法性

        Args:
            categories: 分类标签列表

        Returns:
            (是否有效, 错误信息)
        """
        if not categories:
            return True, ''

        if not isinstance(categories, list):
            return False, 'categories必须是列表'

        if len(categories) > 10:
            return False, '分类标签数量不能超过10个'

        for cat in categories:
            if not isinstance(cat, str):
                return False, f'分类标签必须是字符串，发现{type(cat)}'

            cat = cat.strip()
            if len(cat) > 50:
                return False, f'分类标签"{cat}"过长（超过50字符）'

            if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_\-\s]+$', cat):
                return False, f'分类标签"{cat}"包含非法字符'

        return True, ''
