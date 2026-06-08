from __future__ import annotations

import asyncio
import json
import logging
import re as _regex
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

INTENT_KEYWORDS = {
    "problem_solving": ["求", "计算", "解", "证明", "化简", "因式分解", "积分", "导数", "极限"],
    "concept_inquiry": ["什么是", "为什么", "怎么理解", "定义", "定理", "公式"],
    "error_analysis": ["错在哪", "哪里错了", "为什么错了", "这题做错了"],
    "review": ["复习", "回顾", "总结一下", "帮我梳理"],
    "casual_chat": ["你好", "谢谢", "哈哈", "无聊", "天气"],
}

CATEGORY_RULES = [
    ("极限", ["极限", "lim", "收敛", "发散", "无穷"]),
    ("导数", ["导数", "微分", "求导", "切线", "极值", "最值", "单调"]),
    ("积分", ["积分", "∫", "定积分", "不定积分", "面积", "体积"]),
    ("三角函数", ["sin", "cos", "tan", "三角", "角度", "弧度", "正弦", "余弦"]),
    ("代数", ["方程", "不等式", "因式分解", "多项式", "根", "解集"]),
    ("解析几何", ["直线", "圆", "抛物线", "椭圆", "双曲线", "向量", "坐标"]),
    ("概率统计", ["概率", "期望", "方差", "分布", "排列", "组合", "抽样"]),
    ("数列", ["数列", "等差", "等比", "通项", "求和", "递推"]),
]

SUBCATEGORY_PATTERNS = {
    "极限": ["洛必达", "重要极限", "夹逼定理", "等价无穷小", "连续性", "无穷极限"],
    "导数": ["链式法则", "乘积法则", "商法则", "隐函数", "参数方程", "高阶导数", "三角函数求导"],
    "积分": ["换元法", "分部积分", "三角换元", "有理函数", "幂函数", "指数函数", "三角函数积分"],
    "三角函数": ["二倍角", "半角公式", "和角", "差角", "辅助角", "诱导公式"],
}

VALID_INTENTS = {"problem_solving", "concept_inquiry", "error_analysis", "review", "casual_chat"}
VALID_CATEGORIES = {"极限", "导数", "积分", "三角函数", "代数", "解析几何", "概率统计", "数列"}

MAX_LLM_RETRIES = 3
LLM_RETRY_BASE_DELAY = 1.0
LLM_TIMEOUT_SECONDS = 8.0


class LearningBehaviorTracker:
    """
    用户学习行为追踪器。

    分类策略: LLM-First（LLM 优先 + Rule-Based 兜底）
      1. LLM 完整分类 (~300ms) — 直接判断 intent/category/sub_category/difficulty
      2. Rule-Based Fallback (< 1ms) — LLM 不可用时使用关键词匹配
      3. 安全默认值 — 最终兜底，确保不阻塞主流程
    """

    def __init__(self):
        self._llm_classifier = None
        self._stats = {
            "total_tracks": 0,
            "llm_classified": 0,
            "llm_failed": 0,
            "rule_based_fallback": 0,
            "default_fallback": 0,
        }

    def set_llm_classifier(self, classifier_callable):
        self._llm_classifier = classifier_callable

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    def track(
        self,
        user_id: str,
        raw_input: str,
        source: str = "chat",
        metadata: Optional[Dict[str, Any]] = None,
        llm=None,
    ) -> Dict[str, Any]:
        start_time = time.time()
        self._stats["total_tracks"] += 1

        base_event = {
            "user_id": user_id,
            "event_type": None,
            "question_content": raw_input[:1000],
            "category": None,
            "sub_categories": None,
            "source": source,
            "difficulty": None,
            # 聊天/问答场景无法判断"对错"，但用户通过交互获得了知识
            # source=chat 时视为有效学习事件（is_correct=True）
            # source=quiz/exam 时由调用方传入实际判定结果
            "is_correct": True if source == "chat" else None,
            "time_spent": None,
            "metadata_": metadata or {},
            "_classification_source": None,
        }

        classification_result = None
        source_tag = "default"

        if self._llm_classifier or llm:
            try:
                classification_result = self._classify_with_llm(raw_input, llm=llm)
                if classification_result:
                    base_event.update(classification_result)
                    source_tag = "llm_classified"
                    self._stats["llm_classified"] += 1
                    logger.info(
                        f"[Skill] LLM classified: intent={base_event.get('event_type')}, "
                        f"cat={base_event.get('category')}, sub={base_event.get('sub_categories')}, "
                        f"diff={base_event.get('difficulty')}"
                    )
            except Exception as e:
                self._stats["llm_failed"] += 1
                logger.warning(f"LLM classification failed ({e}), falling back to rules")

        if not classification_result:
            rule_result = self._classify_with_rules(raw_input)
            if rule_result:
                base_event.update(rule_result)
                source_tag = "rule_based_fallback"
                self._stats["rule_based_fallback"] += 1
                logger.info(
                    f"[Skill] Rule-based fallback: intent={base_event.get('event_type')}, "
                    f"cat={base_event.get('category')}"
                )
            else:
                base_event.update(self._get_safe_defaults())
                source_tag = "default_fallback"
                self._stats["default_fallback"] += 1
                logger.debug("[Skill] Using safe defaults for classification")

        base_event["_classification_source"] = source_tag
        base_event["tracking_latency_ms"] = int((time.time() - start_time) * 1000)
        return base_event

    def _classify_with_llm(self, raw_text: str, llm=None) -> Optional[Dict[str, Any]]:
        classifier = llm or self._llm_classifier
        if not classifier:
            return None

        from prompts.behavior_classify_prompt import (
            BEHAVIOR_CLASSIFY_SYSTEM_PROMPT,
            BEHAVIOR_CLASSIFY_USER_TEMPLATE,
        )
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=BEHAVIOR_CLASSIFY_SYSTEM_PROMPT),
            HumanMessage(content=BEHAVIOR_CLASSIFY_USER_TEMPLATE.format(content=raw_text[:500])),
        ]

        raw_response = None
        last_error = None

        for attempt in range(MAX_LLM_RETRIES):
            try:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None

                if loop and loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(
                            lambda: classifier.invoke(messages).content
                        )
                        raw_response = future.result(timeout=LLM_TIMEOUT_SECONDS)
                else:
                    response = classifier.invoke(messages)
                    raw_response = response.content

                if raw_response:
                    break

            except Exception as e:
                last_error = e
                if attempt < MAX_LLM_RETRIES - 1:
                    delay = LLM_RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        f"LLM classify attempt {attempt+1}/{MAX_LLM_RETRIES} failed: {e}, "
                        f"retrying in {delay}s"
                    )
                    time.sleep(delay)

        if not raw_response:
            raise last_error or RuntimeError("LLM returned empty response")

        parsed = self._parse_llm_json(raw_response)
        return self._validate_llm_result(parsed)

    def _classify_with_rules(self, text: str) -> Optional[Dict[str, Any]]:
        intent = self._detect_intent(text)
        category, sub_categories = self._classify_content(text)

        if intent and category:
            return {
                "event_type": intent,
                "category": category,
                "sub_categories": sub_categories or None,
                "difficulty": None,
            }
        elif intent:
            return {
                "event_type": intent,
                "category": "未分类",
                "sub_categories": None,
                "difficulty": None,
            }
        return None

    @staticmethod
    def _get_safe_defaults() -> Dict[str, Any]:
        return {
            "event_type": "concept_inquiry",
            "category": "未分类",
            "sub_categories": None,
            "difficulty": None,
        }

    def _detect_intent(self, text: str) -> str:
        text_lower = text.lower()
        scores = {}
        for intent, keywords in INTENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text_lower)
            if score > 0:
                scores[intent] = score
        if scores:
            return max(scores, key=scores.get)
        return "concept_inquiry"

    def _classify_content(self, text: str) -> tuple:
        best_category = ""
        best_score = 0
        best_sub = ""

        for cat, keywords in CATEGORY_RULES:
            score = sum(1 for kw in keywords if kw in text)
            if score > best_score:
                best_score = score
                best_category = cat

        if best_category and best_category in SUBCATEGORY_PATTERNS:
            for sub in SUBCATEGORY_PATTERNS[best_category]:
                if sub in text:
                    best_sub = sub
                    break

        return best_category, best_sub

    @staticmethod
    def _parse_llm_json(raw_text: str) -> Dict[str, Any]:
        match = _regex.search(r"\{.*\}", raw_text, _regex.DOTALL)
        if not match:
            logger.warning(f"No JSON found in LLM response: {raw_text[:200]}")
            return {}

        try:
            data = json.loads(match.group())
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON: {e}")
        return {}

    def _validate_llm_result(self, parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        result = {}

        llm_intent = parsed.get("event_type", "")
        if llm_intent and llm_intent in VALID_INTENTS:
            result["event_type"] = llm_intent
        elif llm_intent:
            logger.debug(f"LLM returned invalid intent '{llm_intent}', will use fallback")

        llm_cat = parsed.get("category", "")
        if llm_cat and llm_cat in VALID_CATEGORIES:
            result["category"] = llm_cat
        elif llm_cat:
            logger.debug(f"LLM returned invalid category '{llm_cat}', will use fallback")

        llm_sub = parsed.get("sub_categories", "")
        if llm_sub and isinstance(llm_sub, str) and len(llm_sub.strip()) > 0:
            result["sub_categories"] = llm_sub.strip()

        llm_diff = parsed.get("difficulty")
        if llm_diff is not None:
            try:
                d = int(llm_diff)
                if 1 <= d <= 5:
                    result["difficulty"] = d
            except (ValueError, TypeError):
                pass

        tags = parsed.get("tags", [])
        if tags and isinstance(tags, list) and not result.get("sub_categories"):
            first_tag = tags[0] if isinstance(tags[0], str) else str(tags[0])
            if first_tag:
                result.setdefault("sub_categories", first_tag)

        if "event_type" not in result or "category" not in result:
            logger.debug("LLM result missing required fields (intent/category), will use fallback")
            return None

        return result

    @staticmethod
    def record_feedback(
        user_id: str,
        event_ref: str,
        is_helpful: bool,
        is_correct: Optional[bool] = None,
        time_spent_seconds: Optional[int] = None,
        error_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "event_type": "feedback",
            "event_ref": event_ref,
            "is_helpful": is_helpful,
            "is_correct": is_correct,
            "time_spent": time_spent_seconds,
            "error_reason": error_reason,
            "source": "feedback",
        }

    @staticmethod
    def from_error_book_entry(user_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        categories = entry.get("categories") or []
        primary_cat = categories[0] if categories else "未分类"

        return {
            "user_id": user_id,
            "event_type": "error_recorded",
            "question_content": entry.get("question", "") or entry.get("display_question", ""),
            "category": primary_cat,
            "sub_categories": ", ".join(categories[1:]) if len(categories) > 1 else "",
            "is_correct": False,
            "difficulty": entry.get("difficulty") or entry.get("mastery_level") or 3,
            "error_reason": entry.get("error_reason", ""),
            "source": "error_book",
            "error_book_id": entry.get("id"),
            "is_mastered": entry.get("is_mastered", False),
        }
