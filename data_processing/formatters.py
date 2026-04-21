# -*- coding: utf-8 -*-
"""
数据格式化处理器 - 错题本数据标准化与智能提取
负责将原始数据转换为规范化的存储格式
"""

import re
import os
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone


class ErrorBookFormatter:
    """错题本数据格式化处理器"""

    # 预设分类关键词映射
    CATEGORY_KEYWORDS = {
        '极限': ['极限', 'lim', '收敛', '发散', '无穷'],
        '导数': ['导数', "微分", "f'", 'dy/dx', '斜率', '切线'],
        '积分': ['积分', '∫', '不定积分', '定积分', '原函数', '面积'],
        '微分方程': ['微分方程', '差分方程', 'Δy', 'dy/dx'],
        '级数': ['级数', '∑', 'Σ', '无穷级数', '泰勒', '傅里叶'],
        '多元函数': ['偏导', '∂', '多元', '重积分', '曲面积分'],
        '向量': ['向量', '矢量', '点积', '叉积', '梯度', '散度'],
        '几何': ['曲线', '曲面', '切线', '法线', '极坐标']
    }

    @classmethod
    def format(cls, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化错题数据，确保数据一致性和完整性

        Args:
            raw_data: 原始的错题数据字典

        Returns:
            格式化后的数据字典
        """
        formatted = raw_data.copy()

        # 1. 处理题目字段
        cls._process_question_field(formatted)

        # 2. 处理答案字段
        cls._process_answer_fields(formatted)

        # 3. 处理时间戳
        cls._process_timestamp(formatted)

        # 4. 处理分类标签
        cls._process_categories(formatted)

        # 5. 处理其他字段
        cls._process_other_fields(formatted)

        return formatted

    @classmethod
    def _process_question_field(cls, data: Dict[str, Any]) -> None:
        """处理题目字段：分离图片数据和提取识别文本"""
        question = data.get('question', '')
        question_type = data.get('question_type', 'text')

        if question_type == 'image' and question.startswith('data:image'):
            # 图片类型题目处理
            data['raw_image_data'] = question  # 保存原始图片数据
            data['has_image'] = True

            # 从正确答案中提取识别后的文本
            correct_answer = data.get('correct_answer', '')
            recognized_text = cls._extract_recognized_text(correct_answer)
            data['recognized_text'] = recognized_text

            # 生成用于显示的题目（使用识别文本或截断）
            if recognized_text:
                display = recognized_text[:150] + ('...' if len(recognized_text) > 150 else '')
            else:
                display = '[图片题目]'
            data['display_question'] = display

        else:
            # 文本类型题目处理
            cleaned_question = cls._clean_html_tags(question)
            data['display_question'] = cleaned_question[:200] + (
                '...' if len(cleaned_question) > 200 else ''
            )
            data['has_image'] = False
            data['raw_image_data'] = None
            data['recognized_text'] = ''

    @classmethod
    def _process_answer_fields(cls, data: Dict[str, Any]) -> None:
        """处理答案字段：生成预览文本"""
        correct_answer = data.get('correct_answer', '')

        # 生成答案预览（去除LaTeX标记）
        preview = cls._generate_preview(correct_answer, max_length=200)
        data['answer_preview'] = preview

        # 清理原始答案中的多余空白
        if isinstance(correct_answer, str):
            data['correct_answer'] = ' '.join(correct_answer.split())

    @classmethod
    def _process_timestamp(cls, data: Dict[str, Any]) -> None:
        """处理时间戳字段"""
        added_at = data.get('added_at', '')

        if not added_at or added_at.strip() == '':
            data['added_at'] = datetime.now().strftime("%Y-%m-%d %H:%M")
        else:
            # 尝试标准化时间格式
            try:
                # 如果是ISO格式或其他标准格式，转换为目标格式
                dt = datetime.fromisoformat(added_at.replace('Z', '+00:00')).astimezone(timezone.utc)
                data['added_at'] = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, AttributeError):
                # 保持原样（可能是自定义格式）
                pass

    @classmethod
    def _process_categories(cls, data: Dict[str, Any]) -> None:
        """处理分类标签：自动分类+清理"""
        categories = data.get('categories', [])

        if not categories or (isinstance(categories, list) and len(categories) == 0):
            # 自动分类
            auto_categories = cls._auto_classify(data)
            data['categories'] = auto_categories
        elif isinstance(categories, list):
            # 清理现有分类
            cleaned_categories = []
            for cat in categories:
                cat = str(cat).strip()
                if cat and cat not in cleaned_categories:
                    cleaned_categories.append(cat)

            # 补充自动检测的分类
            auto_cats = cls._auto_classify(data)
            for cat in auto_cats:
                if cat not in cleaned_categories:
                    cleaned_categories.append(cat)

            data['categories'] = cleaned_categories[:10]  # 限制最多10个

    @classmethod
    def _process_other_fields(cls, data: Dict[str, Any]) -> None:
        """处理其他字段的标准化"""
        # 标准化错误原因
        error_reason = data.get('error_reason', '')
        if error_reason == '' or error_reason.lower() in ['', 'none', 'null']:
            data['error_reason'] = '未填写'
        else:
            data['error_reason'] = cls._clean_html_tags(error_reason).strip()

        # 标准化笔记
        notes = data.get('notes')
        if notes is None:
            data['notes'] = ''
        elif notes and isinstance(notes, str):
            data['notes'] = cls._clean_html_tags(notes).strip()
        else:
            data['notes'] = ''

        # 确保掌握度在有效范围
        mastery = data.get('mastery_level', 3)
        try:
            mastery_int = int(mastery)
            if mastery_int < 1:
                data['mastery_level'] = 1
            elif mastery_int > 5:
                data['mastery_level'] = 5
            else:
                data['mastery_level'] = mastery_int
        except (ValueError, TypeError):
            data['mastery_level'] = 3  # 默认值

        # 添加数据源标识
        if 'data_source' not in data:
            data['data_source'] = 'user_input'

    @classmethod
    def _extract_recognized_text(cls, answer: str) -> str:
        """
        从AI回答中提取识别后的题目文本

        规则：
        1. 查找【题目】标记后的内容
        2. 提取"问题确认："后面的句子
        3. 如果都找不到，返回前200字符作为摘要
        """
        if not answer:
            return ''

        # 模式1：【题目】标记
        pattern1 = r'【题目】\s*(.+?)(?:\n|$)'
        match1 = re.search(pattern1, answer)
        if match1:
            text = match1.group(1).strip()
            return cls._clean_latex(text)[:300]

        # 模式2：问题确认标记
        pattern2 = r'问题确认[：:]\s*(.+?)(?:\n|。)'
        match2 = re.search(pattern2, answer)
        if match2:
            text = match2.group(1).strip()
            return cls._clean_latex(text)[:300]

        # 模式3：查找"求"、"计算"等关键词开头的句子
        pattern3 = r'(?:求|计算|求解|证明|判断|确定)[^。\n]{10,100}[。]'
        match3 = re.search(pattern3, answer)
        if match3:
            return match3.group(0).strip()[:300]

        # 默认：返回答案的前200字符作为题目摘要
        clean_text = cls._clean_html_tags(answer)
        return clean_text[:200]

    @classmethod
    def _generate_preview(cls, text: str, max_length: int = 150) -> str:
        """
        生成文本预览（去除LaTeX标记）

        Args:
            text: 原始文本
            max_length: 最大长度

        Returns:
            预览文本
        """
        if not text:
            return ''

        # 移除块级LaTeX公式 ($$...$$)
        preview = re.sub(r'\$\$[\s\S]*?\$\$', '[公式]', text)

        # 移除行内LaTeX公式 ($...$)
        preview = re.sub(r'\$[^$]+\$', '[公式]', preview)

        # 清理HTML标签
        preview = cls._clean_html_tags(preview)

        # 清理换行和多余空白
        preview = ' '.join(preview.split())

        # 截断到指定长度
        if len(preview) > max_length:
            preview = preview[:max_length] + '...'

        return preview

    @classmethod
    def _clean_html_tags(cls, text: str) -> str:
        """移除HTML标签"""
        if not text:
            return ''
        
        # 移除HTML标签
        clean = re.sub(r'<[^>]+>', '', text)
        # 解码常见HTML实体
        clean = clean.replace('&nbsp;', ' ')
        clean = clean.replace('&lt;', '<')
        clean = clean.replace('&gt;', '>')
        clean = clean.replace('&amp;', '&')
        clean = clean.replace('&quot;', '"')
        
        return clean

    @classmethod
    def _clean_latex(cls, text: str) -> str:
        """清理LaTeX标记，保留可读文本"""
        if not text:
            return ''

        # 移除LaTeX环境标记
        text = re.sub(r'\\begin\{[a-z]*\}', '', text)
        text = re.sub(r'\\end\{[a-z]*\}', '', text)

        # 替换常用LaTeX命令为可读形式
        latex_replacements = [
            (r'\\frac\{([^}]+)\}\{([^}]+)\}', r'\1/\2'),
            (r'\\sqrt\{([^}]+)\}', r'√(\1)'),
            (r'\\lim_\{([^\}]+)\}', r'lim_{\1}'),
            (r'\\int', '∫'),
            (r'\\sum', '∑'),
            (r'\\infty', '∞'),
            (r'\\partial', '∂'),
            (r'\\nabla', '∇'),
            (r'\\alpha', 'α'),
            (r'\\beta', 'β'),
            (r'\\gamma', 'γ'),
            (r'\\Delta', 'Δ'),
            (r'\\theta', 'θ'),
            (r'\\pi', 'π'),
            (r'\\sin', 'sin'),
            (r'\\cos', 'cos'),
            (r'\\tan', 'tan'),
            (r'\\log', 'log'),
            (r'\\ln', 'ln'),
            (r'\\text\{([^}]+)\}', r'\1'),
            (r'\\\\', '\n'),
            (r'\\[a-zA-Z]+', ''),  # 移除其他未知命令
        ]

        for pattern, replacement in latex_replacements:
            text = re.sub(pattern, replacement, text)

        # 清理多余的空白
        text = ' '.join(text.split())

        return text

    @classmethod
    def _auto_classify(cls, data: Dict[str, Any]) -> List[str]:
        """
        根据内容自动分类

        Args:
            data: 错题数据字典

        Returns:
            分类标签列表
        """
        # 合并所有文本内容用于分析
        text_parts = []

        question = data.get('question', '')
        if question and not question.startswith('data:image'):
            text_parts.append(question)

        recognized = data.get('recognized_text', '')
        if recognized:
            text_parts.append(recognized)

        correct_answer = data.get('correct_answer', '')
        if correct_answer:
            text_parts.append(correct_answer)

        error_reason = data.get('error_reason', '')
        if error_reason:
            text_parts.append(error_reason)

        combined_text = ' '.join(text_parts).lower()

        # 匹配分类
        matched_categories = []
        for category, keywords in cls.CATEGORY_KEYWORDS.items():
            if any(keyword.lower() in combined_text for keyword in keywords):
                matched_categories.append(category)

        # 如果没有匹配到任何分类，添加默认分类
        if not matched_categories:
            matched_categories.append('其他')

        return matched_categories[:5]  # 限制最多5个自动分类
