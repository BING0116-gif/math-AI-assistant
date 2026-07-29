"""
LLMComplexityClassifier — 基于快速LLM的数学问题复杂度分类器。

核心功能:
    1. 调用 qwen-turbo（独立快速LLM实例）进行复杂度评估
    2. MD5缓存在内存中，避免重复调用
    3. 三级降级策略（LLM → 缓存 → 规则兜底）
    4. 完整的日志记录，便于调试和监控

使用示例:
    from langchain_openai import ChatOpenAI
    from agent_core.classifier import LLMComplexityClassifier, ClassifierConfig

    fast_llm = ChatOpenAI(
        model="qwen-turbo",
        temperature=0.0,
        api_key="your-api-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    classifier = LLMComplexityClassifier(llm=fast_llm)
    result = await classifier.classify("求∫x²dx")
    print(result.score)       # 3
    print(result.strategy)    # "react"
    print(result.method)      # "llm"
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Dict

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

from agent_core.classifier.complexity_levels import (
    ComplexityLevel,
    ComplexityCategory,
    level_to_strategy,
    is_simple,
    is_complex,
)
from agent_core.classifier.output_parser import RobustOutputParser
from prompts.classifier_prompt import (
    ClassificationPromptTemplate,
    CLASSIFICATION_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


@dataclass
class ClassifierConfig:
    """
    分类器配置参数。

    Attributes:
        cache_max_size: 内存缓存最大条目数（LRU淘汰）
        enable_cache: 是否启用缓存
        enable_fallback: LLM失败时是否降级到规则匹配
        classification_timeout: 单次分类超时秒数
        temperature: LLM temperature（建议0.0保证确定性）
    """

    cache_max_size: int = 2000
    enable_cache: bool = True
    enable_fallback: bool = True
    classification_timeout: float = 5.0
    temperature: float = 0.0


@dataclass
class ClassificationResult:
    """
    分类结果。

    Attributes:
        score: 复杂度分数 (1-5)
        confidence: 置信度 (0.0-1.0)
        strategy: 推荐的执行策略 ("react" 或 "planned")
        reasoning: 人类可读的推理描述
        method: 分类方法 ("llm" | "cache" | "fallback")
        latency_ms: 分类耗时（毫秒）
        token_usage: LLM Token用量（如有）
    """

    score: int
    confidence: float
    strategy: str
    reasoning: str
    method: str
    latency_ms: float = 0.0
    token_usage: Optional[Dict[str, int]] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典，便于日志记录和序列化。"""
        return {
            "score": self.score,
            "confidence": round(self.confidence, 3),
            "strategy": self.strategy,
            "reasoning": self.reasoning,
            "method": self.method,
            "latency_ms": round(self.latency_ms, 1),
            "token_usage": self.token_usage or {},
        }

    def __repr__(self) -> str:
        label = ComplexityCategory.get_label(self.score)
        return (
            f"ClassificationResult("
            f"score={self.score}({label}), "
            f"strategy={self.strategy}, "
            f"confidence={self.confidence:.2f}, "
            f"method={self.method}, "
            f"latency={self.latency_ms:.0f}ms)"
        )


class LLMComplexityClassifier:
    """
    LLM驱动的数学问题复杂度分类器。

    设计要点:
        - 使用独立的快速LLM实例（qwen-turbo），不干扰主解题流程
        - 内置MD5缓存，相同问题不会重复调用LLM
        - 三级降级策略保证可用性

    Example:
        classifier = LLMComplexityClassifier(llm=fast_llm)

        # 方式1: 获取完整结果
        result = await classifier.classify("用分部积分求∫x·eˣdx")
        if result.score >= 4:
            ...
        else:
            ...

        # 方式2: 快速判断是否复杂
        if await classifier.is_complex_problem("证明eˣ > x+1"):
            ...

        # 方式3: 批量分类
        results = await classifier.batch_classify([
            "1+1=?",
            "求∫x²dx",
            "证明闭区间连续函数一致连续",
        ])
    """

    def __init__(
        self,
        llm: ChatOpenAI,
        config: Optional[ClassifierConfig] = None,
    ):
        """
        初始化分类器。

        Args:
            llm: 独立的快速 ChatOpenAI 实例。
                 建议配置: model="qwen-turbo", temperature=0.0
            config: 可选配置对象
        """
        self._llm = llm
        self._config = config or ClassifierConfig()
        self._parser = RobustOutputParser()

        self._cache: Dict[str, ClassificationResult] = {}

        self._stats = {
            "total_calls": 0,
            "llm_calls": 0,
            "cache_hits": 0,
            "fallbacks": 0,
            "errors": 0,
        }

        self._prompt_template = ClassificationPromptTemplate()

        logger.info(
            f"LLMComplexityClassifier 初始化完成 "
            f"(model={getattr(llm, 'model_name', 'unknown')}, "
            f"cache_max={self._config.cache_max_size}, "
            f"fallback={'启用' if self._config.enable_fallback else '禁用'})"
        )

    async def classify(self, problem: str) -> ClassificationResult:
        """
        对单个问题进行复杂度分类。

        执行流程:
            1. 输入合法性检查
            2. 查 MD5 内存缓存
            3. 调用 qwen-turbo LLM
            4. 鲁棒解析输出
            5. 合理性校验
            6. 存入缓存
            7. 返回结果

        Args:
            problem: 用户输入的数学问题文本

        Returns:
            ClassificationResult 包含分数、策略建议和元信息
        """
        start_time = time.perf_counter()
        self._stats["total_calls"] += 1

        if not problem or not problem.strip():
            logger.debug("收到空输入，返回默认结果")
            return self._empty_input_result(start_time)

        problem = problem.strip()

        if self._config.enable_cache:
            cache_key = self._compute_cache_key(problem)
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._stats["cache_hits"] += 1
                self._cache[cache_key] = cached
                cached.latency_ms = (time.perf_counter() - start_time) * 1000
                cached.method = "cache"
                logger.debug(
                    f"缓存命中: '{problem[:40]}...' → "
                    f"score={cached.score} ({cached.strategy})"
                )
                return cached

        try:
            result = await self._call_llm(problem, start_time)
            self._stats["llm_calls"] += 1

            result = self._validate_result(problem, result)

            if self._config.enable_cache:
                self._store_in_cache(problem, result)

            return result

        except asyncio.TimeoutError:
            logger.error(f"LLM分类超时 ({self._config.classification_timeout}s)")
            self._stats["errors"] += 1
            return await self._handle_failure(problem, start_time, "LLM调用超时")

        except Exception as e:
            logger.error(f"LLM分类异常: {type(e).__name__}: {e}")
            self._stats["errors"] += 1
            return await self._handle_failure(problem, start_time, str(e))

    async def is_complex_problem(self, problem: str) -> bool:
        """
        快捷判断: 是否为复杂问题（需要PlannedStrategy）。

        Args:
            problem: 问题文本

        Returns:
            True 表示分数 >= 4，应使用 PlannedStrategy
        """
        result = await self.classify(problem)
        return result.score >= 4

    async def batch_classify(
        self,
        problems: list[str],
        max_concurrency: int = 5,
    ) -> list[ClassificationResult]:
        """
        批量分类多个问题（并发执行）。

        Args:
            problems: 问题文本列表
            max_concurrency: 最大并发数

        Returns:
            ClassificationResult 列表，顺序与输入一致
        """
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _classify_with_semaphore(problem: str) -> ClassificationResult:
            async with semaphore:
                return await self.classify(problem)

        tasks = [_classify_with_semaphore(p) for p in problems]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def _call_llm(
        self,
        problem: str,
        start_time: float,
    ) -> ClassificationResult:
        """
        实际调用 LLM 进行分类。

        使用 SystemMessage + HumanMessage 构建消息，
        调用 ChatOpenAI.ainvoke() 获取回复。
        """
        messages = [
            SystemMessage(content=CLASSIFICATION_SYSTEM_PROMPT),
            HumanMessage(
                content=ClassificationPromptTemplate.build_human_message(problem)["content"]
            ),
        ]

        response = await asyncio.wait_for(
            self._llm.ainvoke(messages),
            timeout=self._config.classification_timeout,
        )

        raw_output = response.content.strip()
        token_usage = {}
        if hasattr(response, 'response_metadata'):
            metadata = response.response_metadata
            token_usage = metadata.get('token_usage', {})

        score, confidence = self._parser.parse_with_validation(raw_output)

        latency_ms = (time.perf_counter() - start_time) * 1000

        strategy = level_to_strategy(score)

        label = ComplexityCategory.get_label(score)
        reasoning = (
            f"LLM判断: {score}分({label}), "
            f"raw_output='{raw_output[:80]}', "
            f"confidence={confidence:.2f}"
        )

        result = ClassificationResult(
            score=score,
            confidence=confidence,
            strategy=strategy,
            reasoning=reasoning,
            method="llm",
            latency_ms=latency_ms,
            token_usage=token_usage,
        )

        logger.info(
            f"LLM分类完成: [{score}分/{label}] "
            f"→ {strategy} | "
            f"'{problem[:50]}...' | "
            f"延迟={latency_ms:.0f}ms | "
            f"tokens={token_usage.get('total_tokens', 'N/A')}"
        )

        return result

    async def _handle_failure(
        self,
        problem: str,
        start_time: float,
        error_reason: str,
    ) -> ClassificationResult:
        """
        处理LLM调用失败的情况。

        策略:
            1. 检查缓存中是否有相似问题
            2. 降级到规则匹配
            3. 返回中等复杂度（保守策略）
        """
        self._stats["fallbacks"] += 1

        if not self._config.enable_fallback:
            logger.warning("降级机制已禁用，返回中等复杂度默认值")
            return self._default_result(start_time, error_reason)

        fallback_score = self._rule_based_fallback(problem)
        strategy = level_to_strategy(fallback_score)
        latency_ms = (time.perf_counter() - start_time) * 1000

        label = ComplexityCategory.get_label(fallback_score)

        result = ClassificationResult(
            score=fallback_score,
            confidence=0.25,
            strategy=strategy,
            reasoning=f"规则降级({error_reason[:60]}): {fallback_score}分({label})",
            method="fallback",
            latency_ms=latency_ms,
        )

        logger.warning(
            f"降级到规则匹配: [{fallback_score}分/{label}] "
            f"→ {strategy} | '{problem[:50]}...' | "
            f"原因: {error_reason[:80]}"
        )

        return result

    def _rule_based_fallback(self, problem: str) -> int:
        """
        LLM不可用时的规则降级。

        基于如下启发式:
            - 文本长度 (越长越可能复杂)
            - 数学符号密度 (越多越可能复杂)
            - 关键词 (证明/验证/求解ODE/PDE → 复杂)

        Args:
            problem: 问题文本

        Returns:
            1-5 的复杂度分数
        """
        text = problem.strip()
        length = len(text)

        if length <= 8:
            base_score = 1
        elif length <= 20:
            base_score = 2
        elif length <= 45:
            base_score = 3
        elif length <= 80:
            base_score = 4
        else:
            base_score = 5

        complex_keywords = {
            "证明": 1.2, "验证": 0.8,
            "综上所述": 1.2, "求解": 0.3,
            "微分方程": 1.0, "偏微分": 1.5,
            "二重积分": 0.8, "三重积分": 1.0,
            "曲面积分": 1.2, "曲线积分": 0.8,
            "一致连续": 1.0, "收敛": 0.5,
            "画出": 0.7, "图像": 0.5,
            "比较": 0.6, "第一步": 1.0,
            "首先": 0.4, "然后": 0.5,
            "并且": 0.4, "最后": 0.4,
            "拉格朗日": 0.8, "泰勒": 0.6,
        }

        for keyword, weight in complex_keywords.items():
            if keyword in text:
                base_score += weight

        math_symbols = re.findall(
            r'[∫∬∭∮∑∏∞∂∇Δ√±→⇒⇔∀∃∈⊂⊆∪∩'
            r'∫∬∭∮∑∏∞∂∇Δ√±→⇒⇔∀∃∈⊂⊆∪∩'
            r'dx|dy|dz|lim|sin|cos|tan|log|ln'
            r"['\"]{2,}|\\frac|\\sqrt|\\int|\\sum]",
            text
        )
        symbol_count = len(math_symbols)
        base_score += min(symbol_count * 0.2, 1.0)

        simple_patterns = [
            r"^(什么|怎么)是",
            r"等于多少[？?]$",
            r"^(求|计算)\s*(sin|cos|tan)\(?[\dπ/]+\)?",
        ]
        for pattern in simple_patterns:
            if re.search(pattern, text):
                base_score -= 0.5
                break

        return max(1, min(5, int(round(base_score))))

    def _validate_result(
        self,
        problem: str,
        result: ClassificationResult,
    ) -> ClassificationResult:
        """
        对分类结果进行合理性校验。

        如果 LLM 的分类明显不合理（如"1+1=?"被判为5分），
        会用规则兜底纠正。

        Args:
            problem: 原始问题
            result: LLM分类结果

        Returns:
            可能被修正后的分类结果
        """
        text = problem.strip()

        is_trivial = (
            len(text) <= 6
            and re.match(r'^[\d\s\+\-\*\/\(\)\=\?\.]+$', text)
        )
        if is_trivial and result.score >= 4:
            logger.warning(
                f"分类不合理 (极简问题被判{result.score}分), "
                f"修正为2分: '{text}'"
            )
            return ClassificationResult(
                score=2,
                confidence=0.30,
                strategy="react",
                reasoning=f"修正: 极简问题原判{result.score}分→修正为2分",
                method="fallback",
                latency_ms=result.latency_ms,
            )

        if len(text) > 200 and result.score <= 2:
            logger.warning(
                f"分类可能偏低 (长文本被判{result.score}分), "
                f"修正为3分: '{text[:50]}...'"
            )
            return ClassificationResult(
                score=3,
                confidence=0.30,
                strategy="react",
                reasoning=f"修正: 长文本原判{result.score}分→修正为3分",
                method="fallback",
                latency_ms=result.latency_ms,
            )

        return result

    def _empty_input_result(self, start_time: float) -> ClassificationResult:
        """处理空输入的情况。"""
        latency_ms = (time.perf_counter() - start_time) * 1000
        return ClassificationResult(
            score=2,
            confidence=0.5,
            strategy="react",
            reasoning="空输入，默认简单",
            method="fallback",
            latency_ms=latency_ms,
        )

    def _default_result(
        self,
        start_time: float,
        error_reason: str = "",
    ) -> ClassificationResult:
        """返回中等复杂度的默认结果（最安全的默认值）。"""
        latency_ms = (time.perf_counter() - start_time) * 1000
        return ClassificationResult(
            score=3,
            confidence=0.10,
            strategy="react",
            reasoning=f"默认结果 (错误: {error_reason[:60]})",
            method="fallback",
            latency_ms=latency_ms,
        )

    def _compute_cache_key(self, problem: str) -> str:
        """计算问题的MD5哈希作为缓存键。"""
        normalized = problem.strip().lower()
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()

    def _store_in_cache(
        self,
        problem: str,
        result: ClassificationResult,
    ) -> None:
        """将分类结果存入缓存（LRU淘汰策略）。"""
        cache_key = self._compute_cache_key(problem)

        if cache_key in self._cache:
            self._cache[cache_key] = result
            logger.debug(
                f"更新缓存: key={cache_key[:8]}..., "
                f"size={len(self._cache)}/{self._config.cache_max_size}"
            )
            return

        if len(self._cache) >= self._config.cache_max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
            logger.debug(f"LRU淘汰: {oldest_key[:8]}...")

        self._cache[cache_key] = result
        logger.debug(
            f"存入缓存: key={cache_key[:8]}..., "
            f"size={len(self._cache)}/{self._config.cache_max_size}"
        )

    def clear_cache(self) -> None:
        """清空内存缓存。"""
        count = len(self._cache)
        self._cache.clear()
        logger.info(f"缓存已清空 (共{count}条)")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取分类器运行统计。

        Returns:
            包含缓存命中率、调用次数等统计数据的字典
        """
        total = max(self._stats["total_calls"], 1)
        cache_hit_rate = self._stats["cache_hits"] / total

        return {
            "total_calls": self._stats["total_calls"],
            "llm_calls": self._stats["llm_calls"],
            "cache_hits": self._stats["cache_hits"],
            "cache_hit_rate": round(cache_hit_rate, 3),
            "cache_size": len(self._cache),
            "cache_max_size": self._config.cache_max_size,
            "fallbacks": self._stats["fallbacks"],
            "fallback_rate": round(self._stats["fallbacks"] / total, 3),
            "errors": self._stats["errors"],
            "error_rate": round(self._stats["errors"] / total, 3),
        }
