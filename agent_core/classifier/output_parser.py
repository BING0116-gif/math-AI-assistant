"""
鲁棒输出解析器 — 处理 LLM 的各种非标准输出格式。

设计目标: 无论 LLM 返回什么格式的文本，都能从中提取出1-5的复杂度分数。

支持格式:
    - "3"                     → 3 (完美输出)
    - "答案是3"                → 3
    - "难度等级: 3"            → 3
    - "三"                    → 3 (中文数字)
    - "我认为大概是3分左右"     → 3
    - "介于3-4之间"            → 4 (取高值，偏保守)
    - "3或4都可以"             → 4 (取高值)
    - "属于中等难度(3分)"       → 3
"""

from __future__ import annotations

import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class RobustOutputParser:
    """
    鲁棒的 LLM 输出解析器。

    使用多层正则匹配策略，从 LLM 返回的任意文本中提取复杂度分数。

    Example:
        parser = RobustOutputParser()
        score, confidence = parser.parse("难度等级: 3")
        assert score == 3
        assert confidence == 0.85
    """

    _EXACT_PATTERNS = [
        (re.compile(r'^\s*([1-5])\s*$'), 1.00),
        (re.compile(r'^\s*([1-5])[.。,，;；\s]*$'), 0.95),
    ]

    _PHRASE_PATTERNS = [
        (re.compile(r'(?:答案|结果|分数|等级|难度|评级)\s*(?:是|为|：|:)\s*([1-5])'), 0.85),
        (re.compile(r'([1-5])\s*(?:分|级|档|类)'), 0.80),
        (re.compile(r'(?:属于|应该是)\s*(?:第\s*)?([1-5])\s*(?:级|档|类|分)'), 0.80),
    ]

    _CN_MAP = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '壹': 1, '贰': 2, '叁': 3, '肆': 4, '伍': 5,
    }

    _RANGE_PATTERN = re.compile(
        r'(?:介于|在|大约|约)?\s*([1-5])\s*(?:[-~～到和或]|至)\s*([1-5])\s*(?:之间)?'
    )

    _ANY_DIGIT_PATTERN = re.compile(r'([1-5])')

    def parse(self, raw_output: str) -> Tuple[int, float]:
        """
        从 LLM 原始输出中提取复杂度分数。

        采用分层匹配策略，从高精度到低精度依次尝试。

        Args:
            raw_output: LLM 返回的原始文本

        Returns:
            (复杂度分数 1-5, 置信度 0.0-1.0)
        """
        if not raw_output or not raw_output.strip():
            logger.warning("收到空的LLM输出，返回默认值3")
            return 3, 0.0

        text = raw_output.strip()

        for pattern, confidence in self._EXACT_PATTERNS:
            match = pattern.match(text)
            if match:
                return int(match.group(1)), confidence

        for pattern, confidence in self._PHRASE_PATTERNS:
            match = pattern.search(text)
            if match:
                return int(match.group(1)), confidence

        for cn_char, value in self._CN_MAP.items():
            if cn_char in text:
                return value, 0.65

        range_match = self._RANGE_PATTERN.search(text)
        if range_match:
            low = int(range_match.group(1))
            high = int(range_match.group(2))
            score = max(low, high)
            return score, 0.60

        digit_match = self._ANY_DIGIT_PATTERN.search(text)
        if digit_match:
            score = int(digit_match.group(1))
            pos = digit_match.start()
            confidence = 0.50 + (0.20 if pos < len(text) / 2 else 0.0)
            return score, min(confidence, 0.70)

        logger.warning(f"无法从输出中提取分数: '{text[:100]}'，使用默认值3")
        return 3, 0.0

    def parse_with_validation(self, raw_output: str) -> Tuple[int, float]:
        """
        解析并验证结果在合法范围内。

        Args:
            raw_output: LLM 返回的原始文本

        Returns:
            (复杂度分数 1-5, 置信度 0.0-1.0)
        """
        score, confidence = self.parse(raw_output)

        if not 1 <= score <= 5:
            logger.error(f"解析出非法分数 {score}，被裁切到合法范围")
            score = max(1, min(5, score))
            confidence *= 0.5

        return score, confidence
