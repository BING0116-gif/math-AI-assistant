"""
复杂度分级标准 — 定义五级复杂度及其含义。

每一级都包含明确的定义、典型示例以及对应的执行策略。
这个模块不依赖任何外部库，可以被任何其他模块安全引用。
"""

from __future__ import annotations

from enum import IntEnum
from dataclasses import dataclass
from typing import Dict


class ComplexityLevel(IntEnum):
    """
    五级复杂度枚举。

    数值越大，问题越复杂，越需要结构化规划。
    """

    TRIVIAL = 1
    BASIC = 2
    MODERATE = 3
    ADVANCED = 4
    COMPLEX = 5


class ComplexityCategory:
    """
    复杂度等级的描述信息。

    为每一级提供中文标签、详细定义、典型示例和推荐策略。
    """

    _METADATA: Dict[int, dict] = {
        1: {
            "label": "极简",
            "definition": "不需要思考的基础问题：查表、背诵、一步口算",
            "examples": [
                "1+1=?",
                "sin(π/6)=?",
                "梯形的面积公式是什么？",
                "什么是对数？",
                "√4等于多少？",
                "e的零次方是多少？",
            ],
            "strategy": "react",
            "max_steps": 1,
        },
        2: {
            "label": "基础",
            "definition": "套用单一公式、1-2步计算即可完成",
            "examples": [
                "求 f(x)=x³ 的导数",
                "计算 ∫₀¹ 2x dx",
                "解方程 x² - 4 = 0",
                "求 lim(x→0) sinx/x",
                "求f(x)=2x-1在x=3处的函数值",
                "计算3×4+5÷2",
            ],
            "strategy": "react",
            "max_steps": 2,
        },
        3: {
            "label": "中等",
            "definition": "标准解题流程：需要选择适当方法、2-3个步骤",
            "examples": [
                "用分部积分求 ∫x·eˣ dx",
                "判定级数 Σ(1/n²) 的收敛性",
                "求函数 f(x)=x³-3x 的极值",
                "计算矩阵 [[1,2],[3,4]] 的行列式",
                "求f(x)=x²-4x+3在区间[0,5]上的最大值和最小值",
                "求过点(1,2)且与直线y=3x+1平行的直线方程",
                "计算∫₀¹ x·sinx dx",
            ],
            "strategy": "react",
            "max_steps": 4,
        },
        4: {
            "label": "较难",
            "definition": "多步骤组合、需要方法选择策略、容易出错",
            "examples": [
                "证明: eˣ > x+1 对所有 x≠0 成立",
                "求解微分方程 y'' - 3y' + 2y = 0",
                "计算二重积分 ∬_D xy dxdy, D由 y=x² 和 y=x 围成",
                "用拉格朗日乘数法求条件极值",
                "讨论参数a，使方程x²+ax+1=0有两个不等实根的条件",
                "求f(x,y)=x²+y²在约束x+y=1和x≥0,y≥0下的极值",
                "利用泰勒展开证明: sinx < x 对所有 x>0 成立",
                "求函数f(x)=x³-3ax在a>0时的单调区间与极值（含参数讨论）",
                "某工厂生产A、B两种产品，A每件利润2元B每件利润3元，原料限制A不超过10件B不超过8件且总工时不超过60小时，求最大利润",
            ],
            "strategy": "planned",
            "max_steps": 7,
        },
        5: {
            "label": "困难",
            "definition": "综合性强、需要创新思路、竞赛级难度",
            "examples": [
                "证明: π是无理数",
                "计算曲面积分 ∬_S (x+y+z) dS, S为球面",
                "求解偏微分方程 u_t = u_xx 的分离变量解",
                "证明闭区间上连续函数必一致连续 (Heine定理)",
                "构造函数f(x)，使其在[0,1]上处处连续但处处不可导",
                "证明: 对任意正整数n，方程xⁿ+yⁿ=zⁿ在n≥3时无非零整数解(Fermat大定理的特殊情形说明)",
                "设f在[0,1]上连续且f(0)=f(1)，证明: 对任意正整数n，存在c∈[0,1-1/n]使f(c)=f(c+1/n)",
                "利用留数定理计算实积分∫₀^∞ dx/(1+x³)",
            ],
            "strategy": "planned",
            "max_steps": 15,
        },
    }

    @classmethod
    def get_label(cls, level: int | ComplexityLevel) -> str:
        """获取中文标签，如"极简"、"中等"等。"""
        lv = int(level)
        return cls._METADATA.get(lv, {}).get("label", "未知")

    @classmethod
    def get_definition(cls, level: int | ComplexityLevel) -> str:
        """获取该等级的详细定义。"""
        lv = int(level)
        return cls._METADATA.get(lv, {}).get("definition", "")

    @classmethod
    def get_examples(cls, level: int | ComplexityLevel) -> list[str]:
        """获取该等级的典型示例列表。"""
        lv = int(level)
        return cls._METADATA.get(lv, {}).get("examples", [])

    @classmethod
    def get_recommended_strategy(cls, level: int | ComplexityLevel) -> str:
        """
        获取推荐的执行策略。

        Returns:
            "react" 或 "planned"
        """
        lv = int(level)
        return cls._METADATA.get(lv, {}).get("strategy", "react")


def level_to_strategy(score: int) -> str:
    """
    将复杂度分数 (1-5) 映射到 "react" 或 "planned" 策略。

    Args:
        score: 1-5的复杂度分数

    Returns:
        "react" 或 "planned"

    Raises:
        ValueError: 分数不在1-5范围内
    """
    if not 1 <= score <= 5:
        raise ValueError(f"复杂度分数必须在1-5之间，收到: {score}")

    if score <= 3:
        return "react"
    else:
        return "planned"


def is_simple(score: int) -> bool:
    """判断是否为简单问题（分数1-3）。"""
    return 1 <= score <= 3


def is_complex(score: int) -> bool:
    """判断是否为复杂问题（分数4-5）。"""
    return 4 <= score <= 5
