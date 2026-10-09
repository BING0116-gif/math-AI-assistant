"""Original layered practice for the 39 non-golden Phase 5 points.

The underlying teaching statements are the project-authored Phase 5 standard
lessons.  Each point receives the same five-item shape as ``phase5_practice``:
two basic, two standard, and one advanced deterministic choice question.
Distractors come from neighbouring points in the curated catalogue, keeping the
set maintainable while ensuring every option is meaningful mathematics.
"""

from __future__ import annotations

from app.services.calculus_phase5 import POINTS
from app.services.phase5_content import GOLDEN
from app.services.phase5_standard_content import DESCRIPTIONS, STANDARD


_POINT_NAMES = {code: name for code, name, *_ in POINTS}
_CODES = [code for code, *_ in POINTS if code not in GOLDEN]
_LETTERS = "ABCD"


def _first_sentence(text: str) -> str:
    """Keep generated options readable without cutting through LaTeX."""
    head, separator, _ = text.partition("。")
    return f"{head}。" if separator else text


def _choice_item(
    code: str,
    item_index: int,
    level: str,
    difficulty: int,
    prompt: str,
    field: str,
) -> tuple[str, int, str, list[tuple[str, str]], str, str]:
    code_index = _CODES.index(code)
    candidate_codes = [code, *(_CODES[(code_index + offset) % len(_CODES)] for offset in range(1, 4))]
    answer_index = (code_index + item_index) % 4
    candidate_codes[0], candidate_codes[answer_index] = candidate_codes[answer_index], candidate_codes[0]

    def value(candidate: str) -> str:
        if field == "description":
            return DESCRIPTIONS[candidate]
        return _first_sentence(STANDARD[candidate][field])

    options = [(_LETTERS[index], value(candidate)) for index, candidate in enumerate(candidate_codes)]
    answer = _LETTERS[answer_index]
    correct = value(code)
    return level, difficulty, prompt, options, answer, correct


def _items_for(code: str) -> list[tuple[str, int, str, list[tuple[str, str]], str, str]]:
    name = _POINT_NAMES[code]
    return [
        _choice_item(code, 0, "基础", 2, f"下列哪一项准确概括“{name}”？", "description"),
        _choice_item(code, 1, "基础", 2, f"关于“{name}”的核心公式或规则，哪一项正确？", "formula"),
        _choice_item(code, 2, "常规", 3, f"学习“{name}”时，下列哪一个典型例题的处理是匹配的？", "example"),
        _choice_item(code, 3, "常规", 3, f"关于“{name}”，下列哪一项是本节需要特别避免的典型错误？", "error"),
        _choice_item(code, 4, "进阶", 4, f"把“{name}”迁移到综合问题时，哪一种直觉最能指导建模与检查？", "intuition"),
    ]


PRACTICE = {code: _items_for(code) for code in _CODES}
