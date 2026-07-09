"""
问答后跟进推荐服务 — 自动为用户推荐2道难度递增的练习题。

工作流：
1. 意图检测：判断是否为数学解题类问题
2. 知识点提取：LLM 提取 category / knowledge_points / question_type
3. 双难度计算：复用 DifficultyEstimator 生成基础+提升两个难度
4. 相关性检索：多维度匹配从题库检索 2 道题
5. LLM 兜底：RAG 失败时用 LLM 生成原创练习题
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import select, and_, func

from app.config.settings import settings
from app.data.database import get_db_session
from app.data.models import Question, LearningRecord
from app.services.difficulty_estimator import DifficultyEstimator
from app.services.llm_service import LLMService, get_llm_service

logger = logging.getLogger(__name__)


# ── 数据结构 ──

@dataclass
class ProblemFeatures:
    """从用户输入中提取的题目特征。"""
    category: str = ""
    knowledge_points: List[str] = field(default_factory=list)
    question_type: str = ""


@dataclass
class FollowUpResult:
    """跟进推荐结果。"""
    questions: List[Dict[str, Any]] = field(default_factory=list)
    source: str = "rag"  # "rag" | "llm_fallback"
    meta: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


# ── 意图检测 ──

# 解题类关键词（正面信号）
_SOLVE_KEYWORDS = [
    # 核心解题动词
    "求", "计算", "证明", "解", "化简", "求导", "积分",
    # 带前缀的解题动词
    "求极限", "求微分", "求偏导", "求不定积分", "求定积分",
    "求函数", "求方程", "求极值", "求最值", "求拐点",
    "求切线", "求法线", "求面积", "求体积",
    # 其他解题动作
    "展开", "判定", "判断", "验证",
    "求收敛", "求发散", "求级数",
    "求矩阵", "求行列式", "求特征值", "求特征向量",
    "求逆", "求秩", "求解线性方程组",
    # 数学上下文关键词（图片+短文字场景常见）
    "设", "已知", "若", "则", "令",
    "可导", "可微", "连续", "可积",
    "函数", "方程", "不等式", "极限", "导数", "微分", "积分",
    "曲线", "切线", "法线", "极值", "最值", "拐点",
    "单调", "凸凹", "渐近", "收敛", "发散",
    "矩阵", "向量", "特征值", "行列式", "秩",
    "级数", "幂级数", "傅里叶", "泰勒",
]

# 解题类正则模式（关键词后不需要空格，更宽松匹配）
_SOLVE_PATTERNS = [
    # 动词类（后面可紧跟任意字符）
    r'求', r'计算', r'证明', r'化简', r'验证',
    # 数学概念类
    r'求导', r'积分', r'极限', r'微分', r'偏导',
    # 数学表达式类
    r'f\s*\(', r'g\s*\(', r'h\s*\(',
    r'\$.*\$',
    r'\d+\s*[\+\-\*/\^]\s*\d+',  # 含算术运算
    r'lim\s*\(', r'sin\s*\(', r'cos\s*\(', r'ln\s*\(', r'log\s*\(',
    r'e\^', r'x\^', r'n\^',
    r'=\s*\d', r'=\s*-\d',  # 含等号和数字
    r'矩阵', r'行列式', r'向量',
    r'→', r'→',  # 箭头符号（常见于极限）
]

# 非解题类关键词（负面信号）— 更精确，避免误杀
_NON_SOLVE_KEYWORDS = [
    "什么是", "是什么", "为什么", "有什么用", "如何理解",
    "概念", "意义", "区别", "联系",
    "介绍", "解释", "说明",
    "你好", "谢谢", "帮忙", "能否",
]

# 非解题类模式（更精确的负面信号）
_NON_SOLVE_PATTERNS = [
    r'什么是', r'是什么', r'为什么', r'有什么用',
    r'如何理解', r'帮我解释', r'请解释',
]


def is_math_problem(input_text: str) -> bool:
    """
    判断用户输入是否为数学解题类问题。

    策略：规则匹配（关键词+正则），保守策略——有歧义时不触发。
    """
    if not input_text or len(input_text.strip()) < 4:
        return False

    text = input_text.strip()

    # 负面信号检测：如果明显是概念解释/闲聊，需要更强的正面信号才能触发
    non_solve_hits = sum(1 for kw in _NON_SOLVE_KEYWORDS if kw in text)
    non_solve_pattern_hits = sum(1 for p in _NON_SOLVE_PATTERNS if re.search(p, text))
    has_negative = (non_solve_hits + non_solve_pattern_hits) >= 1

    # 正面信号：关键词匹配
    keyword_hits = sum(1 for kw in _SOLVE_KEYWORDS if kw in text)

    # 正面信号：正则匹配
    pattern_hits = sum(1 for p in _SOLVE_PATTERNS if re.search(p, text))

    total_positive = keyword_hits + pattern_hits

    # 有负面信号时，需要更强的正面信号（≥3）才能触发
    if has_negative:
        return total_positive >= 3

    # 无负面信号时（数学AI助手上下文）：
    # - 1+ 关键词 → 触发（用户主动使用数学AI助手，默认数学相关）
    # - 1+ 正则 → 触发（含数学表达式即为数学问题）
    if keyword_hits >= 1:
        return True
    if pattern_hits >= 1:
        return True

    return False


# ── 知识点提取 ──

# 关键词到 category 的兜底映射表
_CATEGORY_KEYWORD_MAP = {
    "导数": "导数", "求导": "导数", "微分": "导数", "切线": "导数",
    "极值": "导数", "最值": "导数", "拐点": "导数", "单调": "导数",
    "凸": "导数", "凹": "导数", "泰勒": "导数", "中值定理": "导数",
    "极限": "极限", "收敛": "极限", "发散": "极限", "无穷": "极限",
    "连续": "极限", "epsilon": "极限",
    "积分": "积分", "定积分": "积分", "不定积分": "积分",
    "面积": "积分", "体积": "积分", "换元": "积分", "分部": "积分",
    "级数": "级数", "幂级数": "级数", "傅里叶": "级数",
    "函数": "函数", "定义域": "函数", "值域": "函数", "复合": "函数",
    "反函数": "函数", "初等": "函数",
    "代数": "代数", "方程": "代数", "不等式": "代数",
    "矩阵": "线性代数", "行列式": "线性代数", "向量": "线性代数",
    "特征值": "线性代数", "线性方程": "线性代数",
}

# 关键词到 question_type 的映射
_TYPE_KEYWORD_MAP = {
    "选择": "选择题", "填空": "填空题", "证明": "证明题",
    "计算": "计算题", "求解": "解答题", "求": "解答题",
    "判断": "判断题",
}

_EXTRACT_SYSTEM_PROMPT = """你是一个数学题分析专家。请从用户输入的数学问题中提取以下信息，严格按JSON格式返回（不要用markdown代码块）：
{"category": "知识点分类", "knowledge_points": ["知识点1", "知识点2"], "question_type": "题型"}

category 必须是以下之一：导数、极限、积分、级数、函数、代数、线性代数、未知
question_type 必须是以下之一：选择题、填空题、解答题、计算题、证明题、判断题、未知

只返回JSON，不要其他内容。"""

_EXTRACT_TIMEOUT = 5.0


async def extract_problem_features(input_text: str, llm_service: Optional[LLMService] = None) -> ProblemFeatures:
    """
    从用户输入中提取结构化的知识点信息。

    优先使用 LLM 提取，超时或失败时回退到关键词映射。
    """
    # 先尝试关键词兜底（快速路径）
    fallback = _extract_by_keywords(input_text)

    # 尝试 LLM 提取
    if llm_service is None:
        try:
            llm_service = get_llm_service()
        except Exception:
            return fallback

    try:
        response = await asyncio.wait_for(
            llm_service.generate(
                prompt=f"请分析以下数学问题：\n{input_text[:500]}",
                system_prompt=_EXTRACT_SYSTEM_PROMPT,
                model=settings.LLM_MATH_MODEL or "qwen-turbo",
                temperature=0.1,
                max_tokens=256,
                use_cache=False,
            ),
            timeout=_EXTRACT_TIMEOUT,
        )
        content = response.content.strip()
        # 清理可能的 markdown 代码块包裹
        content = re.sub(r'^```json\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

        data = json.loads(content)
        category = data.get("category", "").strip()
        knowledge_points = data.get("knowledge_points", [])
        question_type = data.get("question_type", "").strip()

        # 验证 category 是否在合法范围内
        valid_categories = {"导数", "极限", "积分", "级数", "函数", "代数", "线性代数", "未知"}
        if category not in valid_categories:
            category = fallback.category

        # 验证 question_type
        valid_types = {"选择题", "填空题", "解答题", "计算题", "证明题", "判断题", "未知"}
        if question_type not in valid_types:
            question_type = fallback.question_type

        if not knowledge_points:
            knowledge_points = fallback.knowledge_points

        logger.info(
            f"[FOLLOW_UP] extract LLM成功: category={category}, "
            f"kp={knowledge_points}, type={question_type}"
        )
        print(
            f"[FOLLOW_UP] extract | category={category} | "
            f"kp={knowledge_points} | type={question_type}",
            flush=True,
        )
        return ProblemFeatures(
            category=category,
            knowledge_points=knowledge_points,
            question_type=question_type,
        )
    except (asyncio.TimeoutError, json.JSONDecodeError, Exception) as e:
        logger.warning(f"[FOLLOW_UP] extract LLM失败，使用关键词兜底: {e}")
        print(f"[FOLLOW_UP] extract fallback | reason={e}", flush=True)
        return fallback


def _extract_by_keywords(text: str) -> ProblemFeatures:
    """关键词兜底映射。"""
    category = "未知"
    max_hits = 0
    for kw, cat in _CATEGORY_KEYWORD_MAP.items():
        if kw in text:
            # 优先匹配更长的关键词（更精确）
            hits = len(kw)
            if hits > max_hits:
                max_hits = hits
                category = cat

    question_type = "未知"
    for kw, qt in _TYPE_KEYWORD_MAP.items():
        if kw in text:
            question_type = qt
            break

    # 尝试从文本中提取知识点
    knowledge_points = []
    for kw, cat in _CATEGORY_KEYWORD_MAP.items():
        if kw in text and cat == category:
            knowledge_points.append(kw)
    if not knowledge_points and category != "未知":
        knowledge_points = [category]

    return ProblemFeatures(
        category=category,
        knowledge_points=knowledge_points[:3],
        question_type=question_type,
    )


# ── 核心推荐服务 ──

class FollowUpRecommender:
    """问答后跟进推荐服务。"""

    def __init__(
        self,
        difficulty_estimator: Optional[DifficultyEstimator] = None,
        llm_service: Optional[LLMService] = None,
    ):
        self._difficulty_estimator = difficulty_estimator or DifficultyEstimator()
        self._llm = llm_service
        self._session_factory = get_db_session

    def _get_llm(self) -> Optional[LLMService]:
        if self._llm is None:
            try:
                self._llm = get_llm_service()
            except Exception:
                pass
        return self._llm

    async def recommend(
        self,
        user_input: str,
        user_id: str = "anonymous",
    ) -> FollowUpResult:
        """
        主入口：为用户推荐 2 道难度递增的练习题。

        Args:
            user_input: 用户原始输入文本
            user_id: 用户 ID

        Returns:
            FollowUpResult: 包含 2 道题的推荐结果
        """
        start_time = time.time()
        print(f"\n[FOLLOW_UP] ====== 跟进推荐启动 ======", flush=True)
        logger.info(f"[FOLLOW_UP] 跟进推荐启动 | user={user_id} | input='{user_input[:50]}...'")

        try:
            # Step 1: 提取知识点
            features = await extract_problem_features(user_input, self._get_llm())
            if features.category == "未知":
                features.category = "导数"  # 默认回退到导数（题库中最多）
            logger.info(
                f"[FOLLOW_UP] extract完成: category={features.category}, "
                f"kp={features.knowledge_points}, type={features.question_type}"
            )

            # Step 2: 计算双难度
            diff_q1, diff_q2 = await self._compute_dual_difficulty(
                user_id, features.category
            )
            logger.info(f"[FOLLOW_UP] 双难度: Q1={diff_q1}(基础巩固), Q2={diff_q2}(能力提升)")
            print(
                f"[FOLLOW_UP] 双难度 | Q1={diff_q1}(基础巩固) | Q2={diff_q2}(能力提升)",
                flush=True,
            )

            # Step 3: 从题库检索
            questions = await self._retrieve_from_db(
                features, diff_q1, diff_q2, user_id
            )

            if len(questions) >= 2:
                elapsed = (time.time() - start_time) * 1000
                logger.info(f"[FOLLOW_UP] 题库检索成功: {len(questions)}题 | {elapsed:.0f}ms")
                print(
                    f"[FOLLOW_UP] 题库检索成功 | {len(questions)}题 | {elapsed:.0f}ms",
                    flush=True,
                )
                return FollowUpResult(
                    questions=questions[:2],
                    source="rag",
                    meta={
                        "category": features.category,
                        "knowledge_points": features.knowledge_points,
                        "difficulty_q1": diff_q1,
                        "difficulty_q2": diff_q2,
                        "latency_ms": elapsed,
                    },
                )

            # Step 4: 题库不足，LLM 兜底
            logger.info(f"[FOLLOW_UP] 题库不足({len(questions)}题)，切换LLM兜底")
            print(f"[FOLLOW_UP] 题库不足({len(questions)}题)，切换LLM兜底", flush=True)
            fallback_questions = await self._llm_fallback_generate(
                features, diff_q1, diff_q2
            )
            elapsed = (time.time() - start_time) * 1000
            return FollowUpResult(
                questions=fallback_questions,
                source="llm_fallback",
                meta={
                    "category": features.category,
                    "knowledge_points": features.knowledge_points,
                    "difficulty_q1": diff_q1,
                    "difficulty_q2": diff_q2,
                    "latency_ms": elapsed,
                    "rag_result_count": len(questions),
                },
            )

        except Exception as e:
            elapsed = (time.time() - start_time) * 1000
            logger.error(f"[FOLLOW_UP] 推荐异常: {e}", exc_info=True)
            print(f"[FOLLOW_UP] 推荐异常 | error={e}", flush=True)

            # 最终兜底：LLM 生成
            try:
                features = _extract_by_keywords(user_input)
                diff_q1, diff_q2 = 2, 3  # 安全默认值
                fallback_questions = await self._llm_fallback_generate(
                    features, diff_q1, diff_q2
                )
                return FollowUpResult(
                    questions=fallback_questions,
                    source="llm_fallback",
                    meta={"category": features.category, "latency_ms": elapsed, "error": str(e)},
                    error=str(e),
                )
            except Exception as e2:
                logger.error(f"[FOLLOW_UP] LLM兜底也失败: {e2}")
                return FollowUpResult(
                    source="failed",
                    meta={"latency_ms": elapsed, "error": str(e2)},
                    error=str(e2),
                )

    async def _compute_dual_difficulty(
        self, user_id: str, category: str
    ) -> tuple[int, int]:
        """
        计算两道题的难度等级。

        Q1 = 基础巩固（practice 模式，偏简单）
        Q2 = 能力提升（challenge 模式，偏难）

        确保 Q2 > Q1，且 Q1 ∈ [1,3], Q2 ∈ [3,5]。
        会根据数据库中实际存在的难度分布进行调整。
        """
        try:
            base_diff = await self._difficulty_estimator.estimate(
                user_id=user_id, category=category, context="practice"
            )
        except Exception:
            base_diff = 3  # 新用户默认

        # 获取数据库中该 category 实际存在的难度列表
        available_diffs = await self._get_available_difficulties(category)

        # Q1: 基础巩固 — 比推荐难度低 1 级（最低 1）
        diff_q1 = max(1, base_diff - 1)

        # Q2: 能力提升 — 比推荐难度高 1 级（最高 5）
        diff_q2 = min(5, base_diff + 1)

        # 确保 Q2 > Q1
        if diff_q2 <= diff_q1:
            diff_q2 = min(5, diff_q1 + 1)

        # 约束：Q1 ∈ [1,3], Q2 ∈ [3,5]
        diff_q1 = min(3, diff_q1)
        diff_q2 = max(3, diff_q2)

        # 再次确保梯度
        if diff_q2 <= diff_q1:
            diff_q2 = diff_q1 + 1
            if diff_q2 > 5:
                diff_q1 = max(1, diff_q1 - 1)
                diff_q2 = diff_q1 + 1

        # 根据数据库实际分布调整：如果目标难度没有题目，调整到最近的有题目的难度
        if available_diffs:
            if diff_q1 not in available_diffs:
                # 找到 <= diff_q1 的最大可用难度
                lower = [d for d in available_diffs if d <= diff_q1]
                diff_q1 = max(lower) if lower else min(available_diffs)

            if diff_q2 not in available_diffs:
                # 找到 >= diff_q2 的最小可用难度；如果没有，用最大可用难度
                higher = [d for d in available_diffs if d >= diff_q2]
                diff_q2 = min(higher) if higher else max(available_diffs)

        # 最终确保梯度
        if diff_q2 <= diff_q1:
            diff_q2 = min(available_diffs) if available_diffs else 4
            if diff_q2 <= diff_q1:
                diff_q1 = max(1, diff_q2 - 1)

        logger.info(f"[FOLLOW_UP] 难度计算: base={base_diff}, Q1={diff_q1}, Q2={diff_q2}, available={available_diffs}")
        return diff_q1, diff_q2

    async def _get_available_difficulties(self, category: str) -> set[int]:
        """获取指定 category 在数据库中实际存在的难度等级。"""
        try:
            async with self._session_factory() as db:
                result = await db.execute(
                    select(Question.difficulty).where(
                        and_(
                            Question.category == category,
                            Question.is_active == True,
                        )
                    ).distinct()
                )
                return {row[0] for row in result.fetchall()}
        except Exception as e:
            logger.warning(f"[FOLLOW_UP] 获取可用难度失败: {e}")
            return set()

    async def _retrieve_from_db(
        self,
        features: ProblemFeatures,
        diff_q1: int,
        diff_q2: int,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """
        从题库检索 2 道相关题目（1 道 Q1 难度 + 1 道 Q2 难度）。

        多维度匹配：knowledge_points（核心）+ category + question_type
        """
        questions: List[Dict[str, Any]] = []

        # 获取近期已练题目
        exclude_ids = await self._get_recently_done_ids(user_id)

        # 分别检索两个难度的题目
        for label, difficulty in [("Q1", diff_q1), ("Q2", diff_q2)]:
            q = await self._search_one_question(
                features, difficulty, exclude_ids, [q.get("id") for q in questions]
            )
            if q:
                questions.append(q)
                logger.info(
                    f"[FOLLOW_UP] {label}命中: ID={q['id']} | "
                    f"difficulty={q['difficulty']} | source={q.get('source')}"
                )
                print(
                    f"[FOLLOW_UP] {label}命中 | ID={q['id']} | "
                    f"difficulty={q['difficulty']} | source={q.get('source', '?')}",
                    flush=True,
                )

        # 兜底：如果只找到1题，尝试跨类别补全
        if len(questions) == 1:
            missing_label = "Q1" if questions[0].get("difficulty", 0) >= 3 else "Q2"
            missing_diff = diff_q1 if missing_label == "Q1" else diff_q2
            logger.info(f"[FOLLOW_UP] 题库仅{len(questions)}题，启动跨类别兜底检索({missing_label})")
            # 尝试使用通用类别（导数/函数等常见分类）作为兜底
            fallback_categories = ["导数", "函数", "极限", "积分", "微分"]
            for cat in fallback_categories:
                if cat == features.category:
                    continue
                fallback_features = ProblemFeatures(
                    category=cat,
                    knowledge_points=[cat],
                    question_type="未知",
                )
                q = await self._search_one_question(
                    fallback_features, missing_diff, exclude_ids,
                    [q.get("id") for q in questions]
                )
                if q:
                    questions.append(q)
                    logger.info(f"[FOLLOW_UP] {missing_label}兜底命中: ID={q['id']} | category={cat}")
                    print(f"[FOLLOW_UP] {missing_label}兜底命中 | ID={q['id']} | category={cat}", flush=True)
                    break

        return questions

    async def _search_one_question(
        self,
        features: ProblemFeatures,
        difficulty: int,
        exclude_ids: List[str],
        already_found_ids: List[str],
    ) -> Optional[Dict[str, Any]]:
        """
        搜索一道符合条件的题目。

        多维度评分：
        1. category 精确匹配（必须）
        2. difficulty 匹配（必须，可放宽 ±1）
        3. knowledge_points 匹配（加分）
        4. question_type 匹配（加分）

        检索策略（由严格到宽松）：
        - 第一轮：精确匹配 category + difficulty
        - 第二轮：放宽难度 ±1
        - 第三轮：全难度范围 + 正常质量阈值
        - 第四轮：全难度范围 + 降低质量阈值（20字符）
        - 第五轮：全难度范围 + 极低质量阈值（10字符）
        """
        all_exclude = list(set(exclude_ids + already_found_ids))

        try:
            async with self._session_factory() as db:
                # 第一轮：精确匹配 category + difficulty
                candidates = await self._query_candidates(
                    db, features.category, difficulty, all_exclude, limit=20
                )
                logger.debug(f"[FOLLOW_UP] 第1轮检索(精确): cat={features.category}, diff={difficulty}, 候选={len(candidates)}")

                # 第二轮：放宽难度 ±1
                if not candidates:
                    candidates = await self._query_candidates(
                        db, features.category, difficulty, all_exclude,
                        difficulty_range=(max(1, difficulty - 1), min(5, difficulty + 1)),
                        limit=30,
                    )
                    logger.debug(f"[FOLLOW_UP] 第2轮检索(±1): 候选={len(candidates)}")

                # 质量过滤 + 评分（正常阈值：20字符）
                scored = []
                if candidates:
                    for q in candidates:
                        content = q.content or ""
                        if len(content.strip()) < 20:  # 从30降到20
                            continue
                        score = self._compute_relevance_score(q, features, difficulty)
                        scored.append((q, score))
                    logger.debug(f"[FOLLOW_UP] 质量过滤后(≥20字符): {len(scored)}题")

                # 第三轮：放宽难度至全范围 + 正常质量阈值
                if not scored:
                    logger.debug(f"[FOLLOW_UP] 启动第3轮检索(全范围+正常质量)")
                    candidates3 = await self._query_candidates(
                        db, features.category, difficulty, all_exclude,
                        difficulty_range=(1, 5), limit=50,
                    )
                    for q in candidates3:
                        content = q.content or ""
                        if len(content.strip()) < 20:
                            continue
                        score = self._compute_relevance_score(q, features, difficulty)
                        scored.append((q, score))
                    logger.debug(f"[FOLLOW_UP] 第3轮结果: {len(scored)}题")

                # 第四轮：降低质量阈值到10字符
                if not scored:
                    logger.debug(f"[FOLLOW_UP] 启动第4轮检索(低质量阈值)")
                    if not locals().get('candidates3'):
                        candidates3 = await self._query_candidates(
                            db, features.category, difficulty, all_exclude,
                            difficulty_range=(1, 5), limit=50,
                        )
                    else:
                        candidates3 = candidates3  # 复用第三轮的查询结果
                    for q in candidates3:
                        content = q.content or ""
                        if len(content.strip()) < 10:  # 兜底阈值降到10
                            continue
                        score = self._compute_relevance_score(q, features, difficulty)
                        scored.append((q, score))
                    logger.debug(f"[FOLLOW_UP] 第4轮结果(≥10字符): {len(scored)}题")

                if not scored:
                    logger.info(f"[FOLLOW_UP] 所有检索均未找到合适题目 | cat={features.category}, diff={difficulty}")
                    return None

                scored.sort(key=lambda x: x[1], reverse=True)
                best = scored[0][0]
                result = self._question_to_dict(best)
                logger.info(
                    f"[FOLLOW_UP] 检索成功: ID={best.id[:8]}... | "
                    f"cat={best.category} | diff={best.difficulty} | score={scored[0][1]:.2f}"
                )
                return result

        except Exception as e:
            logger.warning(f"[FOLLOW_UP] 数据库查询失败: {e}")
            return None

    async def _query_candidates(
        self,
        db,
        category: str,
        difficulty: int,
        exclude_ids: List[str],
        limit: int = 20,
        difficulty_range: Optional[tuple] = None,
    ) -> list:
        """查询候选题目。"""
        if difficulty_range:
            query = select(Question).where(
                and_(
                    Question.category == category,
                    Question.difficulty.between(difficulty_range[0], difficulty_range[1]),
                    Question.is_active == True,
                )
            )
        else:
            query = select(Question).where(
                and_(
                    Question.category == category,
                    Question.difficulty == difficulty,
                    Question.is_active == True,
                )
            )

        if exclude_ids:
            query = query.where(Question.id.notin_(exclude_ids))

        query = query.order_by(Question.usage_count.asc()).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    def _compute_relevance_score(
        self,
        question: Question,
        features: ProblemFeatures,
        target_difficulty: int,
    ) -> float:
        """
        计算题目与目标特征的相关性评分。

        权重：knowledge_points 50% + category 30% + question_type 20%
        """
        score = 0.0

        # Category 匹配（30%）— 查询时已保证，这里作为保底
        if question.category == features.category:
            score += 0.30

        # Knowledge points 匹配（50%）
        q_kps = set()
        if question.knowledge_points:
            try:
                kp_data = json.loads(question.knowledge_points) if isinstance(question.knowledge_points, str) else question.knowledge_points
                if isinstance(kp_data, list):
                    q_kps = {str(k).strip() for k in kp_data}
                elif isinstance(kp_data, str):
                    q_kps = {k.strip() for k in kp_data.split(",")}
            except Exception:
                q_kps = {k.strip() for k in str(question.knowledge_points).split(",") if k.strip()}

        target_kps = set(features.knowledge_points)
        if q_kps and target_kps:
            overlap = len(q_kps & target_kps)
            total = len(q_kps | target_kps)
            jaccard = overlap / total if total > 0 else 0
            score += 0.50 * jaccard
        elif q_kps:
            # 有知识点但不匹配，给少量分
            score += 0.10

        # Question type 匹配（20%）
        if features.question_type and features.question_type != "未知":
            if question.question_type == features.question_type:
                score += 0.20

        # 难度精确匹配加分
        if question.difficulty == target_difficulty:
            score += 0.05

        return score

    async def _get_recently_done_ids(self, user_id: str) -> List[str]:
        """获取用户近30天已练题目ID。"""
        try:
            from datetime import datetime, timezone
            async with self._session_factory() as db:
                thirty_days_ago = datetime.now(timezone.utc)
                from datetime import timedelta
                thirty_days_ago = thirty_days_ago - timedelta(days=30)
                result = await db.execute(
                    select(LearningRecord.question_id).where(
                        and_(
                            LearningRecord.user_id == user_id,
                            LearningRecord.question_id.isnot(None),
                            LearningRecord.created_at >= thirty_days_ago,
                        )
                    ).limit(200)
                )
                return [r[0] for r in result.fetchall() if r[0]]
        except Exception:
            return []

    async def _llm_fallback_generate(
        self,
        features: ProblemFeatures,
        diff_q1: int,
        diff_q2: int,
    ) -> List[Dict[str, Any]]:
        """LLM 兜底生成 2 道原创练习题。"""
        llm = self._get_llm()
        if llm is None:
            logger.error("[FOLLOW_UP] LLM不可用，无法兜底生成")
            return []

        diff_labels = {1: "入门", 2: "基础", 3: "标准", 4: "进阶", 5: "挑战"}
        kp_str = "、".join(features.knowledge_points) if features.knowledge_points else features.category

        prompt = f"""请生成2道关于「{features.category}」的数学练习题，知识点涉及：{kp_str}。

要求：
- 第1题：难度{diff_q1}级（{diff_labels.get(diff_q1, "基础")}），作为基础巩固题
- 第2题：难度{diff_q2}级（{diff_labels.get(diff_q2, "进阶")}），作为能力提升题
- 题目要有完整的题目内容和参考答案
- 数学公式用 $...$ 或 $$...$$ 包裹
- 题型优先：{features.question_type if features.question_type != "未知" else "不限"}

严格按以下JSON格式返回（不要用markdown代码块）：
[
  {{
    "content": "第1题题目内容",
    "answer": "第1题参考答案",
    "difficulty": {diff_q1},
    "question_type": "题型"
  }},
  {{
    "content": "第2题题目内容",
    "answer": "第2题参考答案",
    "difficulty": {diff_q2},
    "question_type": "题型"
  }}
]

只返回JSON数组，不要其他内容。"""

        try:
            response = await asyncio.wait_for(
                llm.generate(
                    prompt=prompt,
                    model=settings.LLM_MATH_MODEL or "qwen-turbo",
                    temperature=0.7,
                    max_tokens=1024,
                    use_cache=False,
                ),
                timeout=10.0,
            )
            content = response.content.strip()
            # 清理 markdown 代码块
            content = re.sub(r'^```json\s*', '', content)
            content = re.sub(r'^```\s*', '', content)
            content = re.sub(r'\s*```$', '', content)

            data = json.loads(content)
            if not isinstance(data, list):
                data = [data]

            questions = []
            for i, item in enumerate(data[:2]):
                questions.append({
                    "id": f"AI_gen_{int(time.time())}_{i+1}",
                    "content": item.get("content", ""),
                    "answer": item.get("answer", ""),
                    "difficulty": item.get("difficulty", diff_q1 if i == 0 else diff_q2),
                    "question_type": item.get("question_type", "解答题"),
                    "category": features.category,
                    "knowledge_points": json.dumps(features.knowledge_points, ensure_ascii=False),
                    "source": "AI生成",
                    "options": None,
                    "analysis": None,
                    "estimated_time": 5 if i == 0 else 8,
                })

            logger.info(f"[FOLLOW_UP] LLM兜底生成成功: {len(questions)}题")
            print(f"[FOLLOW_UP] LLM兜底生成成功 | {len(questions)}题", flush=True)
            return questions

        except Exception as e:
            logger.error(f"[FOLLOW_UP] LLM兜底生成失败: {e}")
            print(f"[FOLLOW_UP] LLM兜底生成失败 | error={e}", flush=True)
            return []

    @staticmethod
    def _question_to_dict(q: Question) -> Dict[str, Any]:
        return {
            "id": q.id,
            "content": q.content,
            "question_type": q.question_type,
            "options": q.options,
            "answer": q.answer,
            "analysis": q.analysis,
            "category": q.category,
            "sub_categories": q.sub_categories,
            "knowledge_points": q.knowledge_points,
            "difficulty": q.difficulty,
            "estimated_time": q.estimated_time,
            "source": q.source,
        }


# ── 格式化输出 ──

def format_follow_up_text(result: FollowUpResult) -> str:
    """将推荐结果格式化为 Markdown 文本，追加到 AI 回复末尾。"""
    if not result.questions:
        return ""

    diff_labels = {1: "入门", 2: "基础", 3: "标准", 4: "进阶", 5: "挑战"}

    lines = [
        "\n\n---\n",
        "**推荐练习**\n",
    ]

    for i, q in enumerate(result.questions):
        diff = q.get("difficulty", 3)
        diff_label = diff_labels.get(diff, str(diff))
        label = "基础巩固" if i == 0 else "能力提升"
        qid = q.get("id", "?")
        src = q.get("source", "?")
        qtype = q.get("question_type", "")

        lines.append(
            f"**第{i+1}题** [{label}] (ID: {qid} | 来源: {src} | "
            f"难度: {diff}级-{diff_label} | 题型: {qtype}):\n"
        )
        lines.append(f"{q.get('content', '')}\n")

        # 答案折叠提示
        answer = q.get("answer", "")
        if answer:
            lines.append(f"<details><summary>查看答案</summary>\n\n{answer}\n</details>\n")

    lines.append("\n---\n")

    return "\n".join(lines)


# ── 单例 ──

_follow_up_recommender: Optional[FollowUpRecommender] = None


def get_follow_up_recommender() -> FollowUpRecommender:
    global _follow_up_recommender
    if _follow_up_recommender is None:
        _follow_up_recommender = FollowUpRecommender()
    return _follow_up_recommender
