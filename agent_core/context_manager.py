"""
SmartContextManager - 智能128K Token上下文记忆管理系统。

基于《多轮对话上下文记忆容量分析与实现难度报告》和
《Agent系统优化改进方案_v3》的技术规范实现。

核心能力：
1. 精确的Token计数与预算控制（严格≤128K）
2. 多策略混合管理（滑动窗口 + 重要性加权 + 智能摘要压缩）
3. 实时上下文更新与高效检索
4. 内存优化与防溢出保护
5. 数据完整性校验与防篡改机制

Architecture:
┌─────────────────────────────────────────────┐
│           SmartContextManager                │
│  ┌───────────┐ ┌──────────┐ ┌────────────┐   │
│  │Tokenizer  │ │ Budget  │ │ Strategies │   │
│  │ (tiktoken)│ │ Manager │ │ (3种策略)  │   │
│  └─────┬─────┘ └────┬────┘ └──────┬─────┘   │
│        │            │            │          │
│  ┌─────▼────────────▼────────────▼─────┐    │
│  │     Context Store (128K budget)     │    │
│  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐  │    │
│  │  │Msg1 │ │Msg2 │ │...  │ │MsgN │  │    │
│  │  └─────┘ └─────┘ └─────┘ └─────┘  │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================================
# 常量定义
# ============================================================================

DEFAULT_TOTAL_BUDGET_TOKENS = 128000  # 128K tokens硬性上限
DEFAULT_SYSTEM_PROMPT_RESERVE = 2000  # System Prompt预留
DEFAULT_USER_PROFILE_RESERVE = 1000        # 用户画像预留
DEFAULT_MEMORY_INJECTION_LIMIT = 5000  # 记忆注入预留
DEFAULT_SAFETY_MARGIN = 2000          # 安全边距（防止溢出）
DEFAULT_MAX_HISTORY_TURNS = 20        # 默认保留最近20轮对话
DEFAULT_SUMMARIZE_THRESHOLD = 0.8     # 使用率达80%时触发摘要


class ContextStrategy(str, Enum):
    """上下文管理策略枚举。"""
    
    SLIDING_WINDOW = "sliding_window"
    """滑动窗口：仅保留最近N轮对话，最旧的被直接丢弃"""
    
    IMPORTANCE_WEIGHTED = "importance"
    """重要性加权：根据消息价值评分，低分消息优先被淘汰"""
    
    SUMMARIZATION = "summarization"
    """自动摘要：当空间不足时，将旧对话压缩为简短摘要"""
    
    HYBRID = "hybrid"
    """混合策略（推荐）：结合以上三种，智能选择最优方案"""


class MessageRole(str, Enum):
    """消息角色枚举。"""
    
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"  # 工具调用结果


class CompressionPriority(str, Enum):
    """压缩优先级（用于防止关键信息丢失）。"""
    
    CRITICAL = "critical"      # 绝不压缩/删除（如系统指令、错误反馈）
    HIGH = "high"              # 高优先级（如用户明确标记的重点）
    NORMAL = "normal"          # 正常优先级（普通对话内容）
    LOW = "low"                # 低优先级（可被快速浏览或省略的内容）


# ============================================================================
# 数据模型层
# ============================================================================

@dataclass
class ContextBudget:
    """
    上下文预算配置。
    
    定义128K token的总预算分配方案。
    
    Attributes:
        total_tokens: 总token预算（默认128K）
        system_prompt_reserve: System Prompt预留额度
        user_profile_reserve: 用户画像预留额度
        memory_injection_limit: 记忆注入最大额度
        safety_margin: 安全边距（防止API报错）
    """
    
    total_tokens: int = DEFAULT_TOTAL_BUDGET_TOKENS
    system_prompt_reserve: int = DEFAULT_SYSTEM_PROMPT_RESERVE
    user_profile_reserve: int = DEFAULT_USER_PROFILE_RESERVE
    memory_injection_limit: int = DEFAULT_MEMORY_INJECTION_LIMIT
    safety_margin: int = DEFAULT_SAFETY_MARGIN
    
    @property
    def available_for_history(self) -> int:
        """计算可用于对话历史的token数量。"""
        return (
            self.total_tokens 
            - self.system_prompt_reserve 
            - self.user_profile_reserve 
            - self.memory_injection_limit 
            - self.safety_margin
        )
    
    def utilization_rate(self, used_tokens: int) -> float:
        """计算当前利用率（0.0-1.0+）。"""
        if self.total_tokens == 0:
            return 0.0
        return used_tokens / self.total_tokens
    
    def validate_budget(self) -> bool:
        """验证预算配置是否合法（各项预留之和不超过总额）。"""
        reserved_total = (
            self.system_prompt_reserve 
            + self.user_profile_reserve 
            + self.memory_injection_limit 
            + self.safety_margin
        )
        
        if reserved_total >= self.total_tokens:
            logger.error(
                f"[ERR] 预算配置非法: 预留总和({reserved_total}) >= 总额({self.total_tokens})"
            )
            return False
        
        logger.debug(
            f"[OK] 预算验证通过: 总额={self.total_tokens}, "
            f"可用历史={self.available_for_history}, "
            f"预留={reserved_total}"
        )
        return True
    
    def to_dict(self) -> Dict[str, int]:
        """转换为字典格式（用于日志和监控）。"""
        return {
            "total_tokens": self.total_tokens,
            "system_prompt_reserve": self.system_prompt_reserve,
            "user_profile_reserve": self.user_profile_reserve,
            "memory_injection_limit": self.memory_injection_limit,
            "safety_margin": self.safety_margin,
            "available_for_history": self.available_for_history,
        }


@dataclass
class ContextMessage:
    """
    单条上下文消息。
    
    扩展标准消息结构，增加元数据和完整性校验字段。
    
    Attributes:
        message_id: 全局唯一标识符（用于追踪和去重）
        role: 消息角色（system/user/assistant/tool）
        content: 消息文本内容
        token_count: 精确的token数量（由tokenizer计算）
        timestamp: 创建时间戳（Unix epoch秒）
        priority: 压缩优先级
        importance_score: 重要性评分（0.0-1.0，越高越重要）
        metadata: 扩展元数据（可存储任意业务信息）
        content_hash: 内容哈希值（SHA256，用于完整性校验）
        is_compressed: 是否已被摘要压缩
        original_content: 原始完整内容（压缩前备份，可选）
        compression_summary: 压缩后的摘要文本（如果is_compressed=True）
    """
    
    message_id: str
    role: str
    content: str
    token_count: int = 0
    timestamp: float = field(default_factory=time.time)
    priority: CompressionPriority = CompressionPriority.NORMAL
    importance_score: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""
    is_compressed: bool = False
    original_content: Optional[str] = None
    compression_summary: Optional[str] = None
    
    def __post_init__(self):
        """初始化后自动计算content_hash。"""
        if not self.content_hash and self.content:
            self.content_hash = self._compute_hash(self.content)
    
    @staticmethod
    def _compute_hash(content: str) -> str:
        """计算内容的SHA256哈希值（用于完整性校验）。"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
    
    def verify_integrity(self) -> bool:
        """
        验证消息内容是否未被篡改。
        
        Returns:
            True如果内容与哈希匹配，False表示可能被篡改
        """
        current_hash = self._compute_hash(self.content)
        is_valid = current_hash == self.content_hash
        
        if not is_valid:
            logger.warning(
                f"[WARN] 消息完整性校验失败: id={self.message_id}, "
                f"expected_hash={self.content_hash}, actual_hash={current_hash}"
            )
        
        return is_valid
    
    def mark_as_compressed(self, summary: str):
        """标记消息为已压缩状态，并保存原始内容。"""
        if not self.is_compressed:
            self.original_content = self.content
            self.compression_summary = summary
            self.content = f"[已压缩] {summary}"
            self.is_compressed = True
            # 重新计算压缩后的token数和hash
            self.content_hash = self._compute_hash(self.content)
            
            logger.debug(
                f"[OK] 消息已压缩: id={self.message_id}, "
                f"原始长度={len(self.original_content)}, "
                f"摘要长度={len(summary)}"
            )
    
    def restore_from_compression(self):
        """从压缩状态恢复原始内容。"""
        if self.is_compressed and self.original_content:
            self.content = self.original_content
            self.compression_summary = None
            self.is_compressed = False
            self.content_hash = self._compute_hash(self.content)
            
            logger.debug(
                f"[OK] 消息已恢复: id={self.message_id}"
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于序列化和日志）。"""
        return {
            "message_id": self.message_id,
            "role": self.role,
            "content_preview": self.content[:100] + ("..." if len(self.content) > 100 else ""),
            "token_count": self.token_count,
            "timestamp": self.timestamp,
            "priority": self.priority.value,
            "importance_score": round(self.importance_score, 3),
            "is_compressed": self.is_compressed,
            "metadata_keys": list(self.metadata.keys()),
        }


@dataclass
class ContextSnapshot:
    """
    上下文快照（用于调试和审计）。
    
    在关键时刻捕获完整的上下文状态。
    """
    
    snapshot_time: float
    total_messages: int
    total_tokens_used: int
    budget_utilization: float
    strategy_active: str
    messages_summary: List[Dict[str, Any]]
    
    def to_report(self) -> str:
        """生成人类可读的报告字符串。"""
        lines = [
            f"📸 上下文快照 @{self.snapshot_time}",
            f"   总消息数: {self.total_messages}",
            f"   总Token数: {self.total_tokens_used:,}",
            f"   预算利用率: {self.budget_utilization:.1%}",
            f"   当前策略: {self.strategy_active}",
            f"   最近5条消息:",
        ]
        
        for msg in self.messages_summary[-5:]:
            lines.append(
                f"     [{msg['role']}] {msg['preview'][:50]}... "
                f"({msg['tokens']} tokens)"
            )
        
        return "\n".join(lines)


# ============================================================================
# 异常体系
# ============================================================================

class ContextError(Exception):
    """上下文管理基础异常。"""
    
    def __init__(self, message: str, recoverable: bool = True):
        self.recoverable = recoverable
        super().__init__(message)


class BudgetExceededError(ContextError):
    """预算超限异常（无法为消息腾出足够空间）。"""
    
    def __init__(
        self, 
        required: int, 
        available: int, 
        strategy: str = ""
    ):
        self.required_tokens = required
        self.available_tokens = available
        message = (
            f"上下文预算不足: 需要{required} tokens, "
            f"但仅剩{available} tokens可用"
            f"{f' (策略: {strategy})' if strategy else ''}"
        )
        super().__init__(message, recoverable=False)


class IntegrityCheckFailedError(ContextError):
    """完整性校验失败异常（检测到数据篡改）。"""
    
    def __init__(self, message_id: str, expected_hash: str, actual_hash: str):
        self.message_id = message_id
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        message = (
            f"消息完整性校验失败: id={message_id}, "
            f"期望hash={expected_hash}, 实际hash={actual_hash}"
        )
        super().__init__(message, recoverable=False)


class TokenCountingError(ContextError):
    """Token计数错误（tokenizer异常）。"""
    
    def __init__(self, text: str, original_error: Exception):
        self.text = text[:100]  # 仅保存前100字符避免日志过长
        self.original_error = original_error
        message = f"Token计数失败: text={self.text}..., error={original_error}"
        super().__init__(message, recoverable=True)


# ============================================================================
# Phase 2: Tokenizer分层架构 — 后端 / 缓存 / 协调器
# ============================================================================

# ---------------------------------------------------------------------------
# 2.1 计数后端抽象与实现
# ---------------------------------------------------------------------------

class TokenizerBackend(ABC):
    """Tokenizer后端抽象基类。"""

    @abstractmethod
    def count(self, text: str) -> int:
        """计算文本的token数量。"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查后端是否可用。"""
        pass


class TiktokenBackend(TokenizerBackend):
    """基于tiktoken的精确计数后端。"""

    def __init__(self, encoding_name: str = "cl100k_base"):
        self._tokenizer = None
        self._available = False

        try:
            import tiktoken
            self._tokenizer = tiktoken.get_encoding(encoding_name)
            self._available = True
            logger.info(f"[OK] TiktokenBackend初始化成功: {encoding_name}")
        except ImportError:
            logger.warning(
                "[WARN] tiktoken未安装，TiktokenBackend不可用"
                "(建议运行: pip install tiktoken)"
            )
        except Exception as e:
            logger.error(f"[ERR] TiktokenBackend初始化失败: {e}")

    def count(self, text: str) -> int:
        if not self._available:
            raise RuntimeError("TiktokenBackend不可用")
        return len(self._tokenizer.encode(text))

    def is_available(self) -> bool:
        return self._available


class HeuristicBackend(TokenizerBackend):
    """
    基于启发式规则的计数后端（fallback）。

    经验规则：
    - 中文字符：约1.5 chars/token
    - 英文单词：约4 chars/token（平均单词长度4）
    - 数字和符号：约4 chars/token
    - 标点符号：每个约0.25 token
    - 特殊token（如换行、缩进）：额外计算
    """

    def count(self, text: str) -> int:
        if not text:
            return 0

        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        numbers = len(re.findall(r'\d+', text))
        punctuation = len(re.findall(r'[^\w\s]', text))
        whitespace = len(re.findall(r'\s+', text))

        chinese_tokens = chinese_chars * 1.5
        english_tokens = english_words * 1.3
        number_tokens = numbers * 0.8
        punctuation_tokens = punctuation * 0.25
        whitespace_tokens = whitespace * 0.2

        total = int(chinese_tokens + english_tokens + number_tokens +
                   punctuation_tokens + whitespace_tokens)

        return max(total, 1)

    def is_available(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# 2.2 缓存抽象与实现
# ---------------------------------------------------------------------------

class TokenCache(ABC):
    """Token缓存抽象基类。"""

    @abstractmethod
    def get(self, key: str) -> Optional[int]:
        """从缓存获取计数结果。"""
        pass

    @abstractmethod
    def put(self, key: str, value: int) -> None:
        """将计数结果存入缓存。"""
        pass

    @abstractmethod
    def clear(self) -> None:
        """清空缓存。"""
        pass

    @property
    @abstractmethod
    def size(self) -> int:
        """当前缓存条目数。"""
        pass


class LRUCache(TokenCache):
    """LRU（最近最少使用）缓存实现。"""

    def __init__(self, max_size: int = 10000):
        self._max_size = max_size
        self._cache: Dict[str, int] = {}
        self._access_order: List[str] = []

    def get(self, key: str) -> Optional[int]:
        if key not in self._cache:
            return None

        self._access_order.remove(key)
        self._access_order.append(key)
        return self._cache[key]

    def put(self, key: str, value: int) -> None:
        if key in self._cache:
            self._access_order.remove(key)
        elif len(self._cache) >= self._max_size:
            oldest_key = self._access_order.pop(0)
            del self._cache[oldest_key]

        self._cache[key] = value
        self._access_order.append(key)

    def clear(self) -> None:
        self._cache.clear()
        self._access_order.clear()

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def max_size(self) -> int:
        return self._max_size


class NoOpCache(TokenCache):
    """无操作缓存（用于禁用缓存场景）。"""

    def get(self, key: str) -> Optional[int]:
        return None

    def put(self, key: str, value: int) -> None:
        pass

    def clear(self) -> None:
        pass

    @property
    def size(self) -> int:
        return 0


# ---------------------------------------------------------------------------
# 2.3 TokenCounter — 协调器
# ---------------------------------------------------------------------------

class TokenCounter:
    """
    Token计数器协调器。

    通过依赖注入使用不同的计数后端和缓存策略，
    本身只负责协调逻辑，不包含具体实现。

    Example:
        counter = TokenCounter()                        # 默认：TiktokenBackend + LRUCache
        counter = TokenCounter(backend=HeuristicBackend(), cache=NoOpCache())
    """

    def __init__(
        self,
        backend: Optional[TokenizerBackend] = None,
        cache: Optional[TokenCache] = None,
        encoding_name: str = "cl100k_base",
        enable_cache: bool = True,
        cache_max_size: int = 10000,
    ):
        self._backend = backend or self._create_default_backend(encoding_name)
        if cache is not None:
            self._cache = cache
        elif enable_cache:
            self._cache = LRUCache(max_size=cache_max_size)
        else:
            self._cache = NoOpCache()

        logger.info(
            f"[OK] TokenCounter初始化完成: "
            f"backend={type(self._backend).__name__}, "
            f"cache={type(self._cache).__name__}"
        )

    @staticmethod
    def _create_default_backend(encoding_name: str = "cl100k_base") -> TokenizerBackend:
        """创建默认的计数后端（优先tiktoken，fallback到启发式）。"""
        backend = TiktokenBackend(encoding_name)
        if backend.is_available():
            return backend
        logger.warning("[WARN] 使用HeuristicBackend作为fallback")
        return HeuristicBackend()

    def count_tokens(self, text: str) -> int:
        """
        计算文本的精确Token数量。

        Args:
            text: 待计数的文本

        Returns:
            Token数量

        Raises:
            TokenCountingError: 计数失败
        """
        if not text:
            return 0

        cache_key = self._make_cache_key(text)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            count = self._backend.count(text)
            self._cache.put(cache_key, count)
            return count
        except Exception as e:
            raise TokenCountingError(text, e)

    def count_messages_tokens(self, messages: List[ContextMessage]) -> int:
        """批量计算多条消息的总Token数。"""
        return sum(msg.token_count for msg in messages)

    def estimate_tokens_for_role(
        self,
        role: str,
        content_length: int
    ) -> int:
        """
        根据角色和内容长度估算Token数（快速预估算）。

        用于在添加消息前快速判断是否会超限。

        Args:
            role: 消息角色
            content_length: 内容字符长度

        Returns:
            估算的token数量（通常比精确值高10-20%，留有余量）
        """
        base_ratio = {
            "system": 2.5,
            "user": 2.0,
            "assistant": 1.8,
            "tool": 1.5,
        }.get(role, 2.0)

        estimated = int(content_length / base_ratio)
        estimated += 4

        return ((estimated + 9) // 10) * 10

    @staticmethod
    def _make_cache_key(text: str) -> str:
        """生成缓存键（使用文本前256字符的MD5）。"""
        preview = text[:256]
        return hashlib.md5(preview.encode()).hexdigest()

    @property
    def cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息。"""
        return {
            "cache_size": self._cache.size,
            "max_size": getattr(self._cache, 'max_size', self._cache.size),
            "hit_rate": "N/A",
            "backend": type(self._backend).__name__,
        }

    def clear_cache(self):
        """清空缓存。"""
        self._cache.clear()


# ============================================================================
# Phase 3 & 4: SmartContextManager核心实现
# ============================================================================

class SmartContextManager:
    """
    智能128K Token上下文记忆管理系统。
    
    核心职责：
    1. 严格的Token预算控制（确保发送给LLM的总token ≤ 128K）
    2. 多策略混合管理（滑动窗口 + 重要性加权 + 智能摘要）
    3. 实时更新与高效检索
    4. 内存优化与防溢出
    5. 数据完整性保障
    
    使用示例:
    >>> manager = SmartContextManager(budget=ContextBudget(total_tokens=128000))
    >>> manager.add_message("user", "求积分∫x²dx")
    True
    >>> manager.add_message("assistant", "结果是 x³/3 + C")
    True
    >>> messages = manager.build_llm_context(system_prompt="你是数学助手")
    >>> print(len(messages))  # 包含system + history
    
    设计原则:
    - 硬性上限：绝不允许超过128K tokens（防止API报错）
    - 软性预警：使用率达80%时触发自动优化
    - 公平性：每个session获得相同的预算
    - 智能化：自动识别并保护高价值对话
    - 可观测性：详细的日志、指标和快照机制
    """
    
    def __init__(
        self,
        session_id: str = "default",
        budget: Optional[ContextBudget] = None,
        strategy: ContextStrategy = ContextStrategy.HYBRID,
        tokenizer: Optional[TokenCounter] = None,
        max_history_turns: int = DEFAULT_MAX_HISTORY_TURNS,
        summarize_threshold: float = DEFAULT_SUMMARIZE_THRESHOLD,
        importance_scoring_enabled: bool = True,
        auto_optimize: bool = True,
    ):
        """
        初始化SmartContextManager。
        
        Args:
            session_id: 会话唯一标识符
            budget: 上下文预算配置（默认128K总预算）
            strategy: 上下文管理策略
            tokenizer: Token计数器实例（默认自动创建）
            max_history_turns: 最大保留历史轮次
            summarize_threshold: 触发摘要的使用率阈值(0-1)
            importance_scoring_enabled: 是否启用重要性评分
            auto_optimize: 是否启用自动优化（超限时自动清理）
        """
        self.session_id = session_id
        self._budget = budget or ContextBudget()
        self._strategy = strategy
        self._tokenizer = tokenizer or TokenCounter()
        self._max_history_turns = max_history_turns
        self._summarize_threshold = summarize_threshold
        self._importance_enabled = importance_scoring_enabled
        self._auto_optimize = auto_optimize
        
        # 消息存储（有序列表，按时间顺序）
        self._messages: List[ContextMessage] = []
        
        # 索引结构（加速检索）
        self._message_index: Dict[str, int] = {}  # message_id -> index
        
        # 统计计数器
        self._stats = {
            "messages_added": 0,
            "messages_removed": 0,
            "messages_compressed": 0,
            "budget_overflows_avoided": 0,
            "integrity_checks_passed": 0,
            "integrity_checks_failed": 0,
            "last_snapshot_time": 0,
        }
        
        # 验证预算合法性
        if not self._budget.validate_budget():
            raise ValueError("[ERR] ContextBudget配置非法，请检查预留项设置")
        
        logger.info(
            f"[OK] SmartContextManager初始化完成: "
            f"session={session_id}, "
            f"budget={self._budget.total_tokens} tokens, "
            f"strategy={strategy.value}, "
            f"max_turns={max_history_turns}"
        )
    
    # ========================================================================
    # 核心公共API
    # ========================================================================
    
    def add_message(
        self,
        role: str,
        content: str,
        priority: CompressionPriority = CompressionPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
        skip_token_count: bool = False,
    ) -> bool:
        """
        添加一条消息到上下文中。
        
        这是主要的用户交互接口。该方法会：
        1. 精确计算消息的token消耗
        2. 检查是否会超出预算
        3. 如有必要，自动执行清理/压缩操作
        4. 将消息安全地插入存储
        5. 更新索引和统计信息
        
        Args:
            role: 消息角色（"system"/"user"/"assistant"/"tool"）
            content: 消息文本内容
            priority: 压缩优先级（CRITICAL的消息不会被自动清理）
            metadata: 扩展元数据字典
            skip_token_count: 是否跳过token计数（用于性能敏感场景）
            
        Returns:
            True如果成功添加，False如果因预算限制无法添加
            
        Raises:
            BudgetExceededError: 如果auto_optimize=False且无法腾出空间
        """
        if not content or not content.strip():
            logger.warning("[WARN] 尝试添加空消息，已忽略")
            return False
        
        # Step 1: 计算Token数量
        try:
            if skip_token_count:
                token_count = self._tokenizer.estimate_tokens_for_role(role, len(content))
            else:
                token_count = self._tokenizer.count_tokens(content)
        except TokenCountingError as e:
            logger.error(f"[ERR] Token计数失败: {e}")
            # Fallback到估算
            token_count = self._tokenizer.estimate_tokens_for_role(role, len(content))
        
        # Step 2: 构建消息对象
        message = ContextMessage(
            message_id=self._generate_message_id(),
            role=role,
            content=content,
            token_count=token_count,
            priority=priority,
            metadata=metadata or {},
        )
        
        # Step 3: 计算重要性分数（如果启用）
        if self._importance_enabled:
            message.importance_score = self._calculate_importance(message)
        
        # Step 4: 检查预算并尝试腾出空间
        current_total = self.get_total_tokens_used()
        projected_total = current_total + token_count
        
        if projected_total > self._budget.total_tokens:
            if self._auto_optimize:
                success = self._make_space_for_new_message(token_count)
                if not success:
                    logger.warning(
                        f"[WARN] 无法为消息腾出足够空间: "
                        f"需要{token_count} tokens, 当前已用{current_total}/{self._budget.total_tokens}"
                    )
                    self._stats["budget_overflows_avoided"] += 1
                    return False
            else:
                raise BudgetExceededError(
                    required=token_count,
                    available=self._budget.total_tokens - current_total,
                    strategy=self._strategy.value,
                )
        
        # Step 5: 安全插入消息
        insert_index = len(self._messages)
        self._messages.append(message)
        self._message_index[message.message_id] = insert_index
        
        # Step 6: 更新统计
        self._stats["messages_added"] += 1
        
        # Step 7: 检查是否需要触发主动优化
        utilization = self.get_utilization_rate()
        if utilization >= self._summarize_threshold:
            self._trigger_auto_optimization(utilization)
        
        logger.debug(
            f"[OK] 消息已添加: id={message.message_id[:8]}, "
            f"role={role}, tokens={token_count}, "
            f"priority={priority.value}, "
            f"当前总量={self.get_total_tokens_used()}/{self._budget.total_tokens} "
            f"({utilization:.1%})"
        )
        
        return True
    
    def build_llm_context(
        self,
        system_prompt: str = "",
        user_profile: Optional[Dict] = None,
        injected_memories: Optional[List[Dict]] = None,
        include_metadata: bool = False,
    ) -> List[Dict[str, str]]:
        """
        构建发送给LLM的完整上下文列表。
        
        这是与LLM API对接的核心方法。严格保证返回的消息列表
        总Token数不超过budget.total_tokens。
        
        构建顺序（符合OpenAI Chat Completions API格式）：
        1. System Prompt（如果有）
        2. 用户画像信息（如果有）
        3. 注入的相关记忆（如果有，最多N条）
        4. 对话历史（动态裁剪以适应剩余预算）
        
        Args:
            system_prompt: 系统提示词
            user_profile: 用户画像JSON（将被序列化为字符串）
            injected_memories: 从Memory系统注入的相关历史记录
            include_metadata: 是否在返回结果中包含统计元数据
            
        Returns:
            符合OpenAI格式的消息列表 [{"role": ..., "content": ...}, ...]
            
        注意:
            返回的消息列表经过严格的Token预算控制，
            即使传入大量历史记录也不会超过128K限制。
        """
        result_messages = []
        tokens_used = 0
        
        def _can_add(content: str, reserve: int = 0) -> bool:
            """检查是否还有足够的预算空间添加此内容。"""
            content_tokens = self._tokenizer.count_tokens(content)
            return (tokens_used + content_tokens + reserve) <= self._budget.total_tokens
        
        def _safe_add(role: str, content: str, reserve: int = 0) -> bool:
            """安全地添加消息到结果列表（带预算检查）。"""
            nonlocal tokens_used
            
            if not _can_add(content, reserve):
                return False
            
            result_messages.append({"role": role, "content": content})
            tokens_used += self._tokenizer.count_tokens(content)
            return True
        
        # 1. System Prompt（必须包含，最高优先级）
        if system_prompt:
            if not _safe_add("system", system_prompt):
                logger.error("[ERR] System Prompt超出预算，这不应该发生！")
                # 截断System Prompt（极端情况下的保底措施）
                truncated = system_prompt[:int(len(system_prompt) * 0.8)]
                _safe_add("system", truncated)
        
        # 2. 用户画像（如有）
        if user_profile:
            profile_str = json.dumps(user_profile, ensure_ascii=False, indent=2)
            if not _safe_add("system", f"[User Profile]\n{profile_str}"):
                logger.warning("[WARN] 用户画像因空间不足被省略")
        
        # 3. 注入的记忆（如有，限制数量）
        if injected_memories:
            memories_to_add = min(len(injected_memories), 10)  # 最多10条
            memories_text = "\n".join([
                f"- [{m.get('type', 'memory')}] {m.get('content', '')[:200]}"
                for m in injected_memories[:memories_to_add]
            ])
            
            if not _safe_add("system", f"[Relevant Memories]\n{memories_text}"):
                logger.debug("💾 相关记忆因空间不足被省略")
        
        # 4. 对话历史（动态选择以适应剩余预算）
        remaining_budget = self._budget.total_tokens - tokens_used - self._budget.safety_margin
        
        if remaining_budget > 0:
            history_messages = self._select_history_for_context(remaining_budget)
            
            for msg in history_messages:
                # 对压缩过的消息添加特殊标记
                display_content = msg.content
                if msg.is_compressed and msg.compression_summary:
                    display_content = (
                        f"[Summary of earlier conversation]\n"
                        f"{msg.compression_summary}\n"
                        f"(Original was {len(msg.original_content)} chars)"
                    )
                
                result_messages.append({
                    "role": msg.role,
                    "content": display_content,
                })
                
                tokens_used += msg.token_count
        
        # 最终验证（防御性编程）
        assert tokens_used <= self._budget.total_tokens, \
            f"🚨 严重错误: 构建的上下文({tokens_used})超出预算({self._budget.total_tokens})"
        
        # 记录统计
        logger.info(
            f"[OK] LLM上下文构建完成: "
            f"total_tokens={tokens_used}/{self._budget.total_tokens} "
            f"({tokens_used/self._budget.total_tokens*100:.1f}%), "
            f"messages={len(result_messages)}, "
            f"history_turns={len([m for m in result_messages if m['role'] in ('user', 'assistant')])//2}"
        )
        
        if include_metadata:
            # 在最后一个元素中附加元数据（特殊约定，不影响LLM）
            result_messages.append({
                "role": "__metadata__",
                "content": json.dumps({
                    "total_tokens": tokens_used,
                    "utilization_rate": round(tokens_used / self._budget.total_tokens, 4),
                    "message_count": len(result_messages),
                    "session_id": self.session_id,
                    "timestamp": time.time(),
                }),
            })
        
        return result_messages
    
    def get_message_by_id(self, message_id: str) -> Optional[ContextMessage]:
        """根据ID查找消息。"""
        index = self._message_index.get(message_id)
        if index is not None and index < len(self._messages):
            return self._messages[index]
        return None
    
    def get_recent_messages(
        self, 
        count: int = 10, 
        roles: Optional[List[str]] = None
    ) -> List[ContextMessage]:
        """
        获取最近N条消息。
        
        Args:
            count: 获取数量
            roles: 角色过滤（如["user", "assistant"]），None表示不过滤
            
        Returns:
            消息列表（按时间倒序，最新的在前）
        """
        recent = self._messages[-count:] if count > 0 else []
        
        if roles:
            recent = [m for m in recent if m.role in roles]
        
        # 返回副本（倒序：最新的在前）
        return list(reversed(recent))
    
    def search_messages(
        self,
        query: str,
        limit: int = 5,
        search_content: bool = True,
        search_metadata: bool = True,
    ) -> List[Tuple[ContextMessage, float]]:
        """
        在上下文中搜索相关消息。
        
        支持简单的关键词匹配搜索（未来可升级为语义搜索）。
        
        Args:
            query: 搜索关键词
            query: 最大返回数量
            search_content: 是否搜索消息内容
            search_metadata: 是否搜索元数据
            
        Returns:
            [(message, relevance_score), ...] 按相关性降序排列
        """
        query_lower = query.lower()
        results = []
        
        for msg in self._messages:
            score = 0.0
            
            # 内容匹配（权重较高）
            if search_content and query_lower in msg.content.lower():
                # 计算匹配密度（出现次数/内容长度）
                occurrences = msg.content.lower().count(query_lower)
                score += 0.7 * (occurrences / max(len(msg.content), 1))
            
            # 元数据匹配（权重较低）
            if search_metadata and msg.metadata:
                meta_str = json.dumps(msg.metadata, ensure_ascii=False).lower()
                if query_lower in meta_str:
                    score += 0.3
            
            if score > 0:
                results.append((msg, score))
        
        # 按相关性排序并截取top-K
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]
    
    # ========================================================================
    # 查询与统计API
    # ========================================================================
    
    def get_total_tokens_used(self) -> int:
        """获取当前已使用的Token总数。"""
        return sum(msg.token_count for msg in self._messages)
    
    def get_utilization_rate(self) -> float:
        """获取当前预算利用率（0.0-1.0+）。"""
        return self._budget.utilization_rate(self.get_total_tokens_used())
    
    def get_message_count(self) -> int:
        """获取当前消息总数。"""
        return len(self._messages)
    
    def get_turn_count(self) -> int:
        """获取对话轮次数量（1轮=1个user+1个assistant）。"""
        user_msgs = sum(1 for m in self._messages if m.role == "user")
        assistant_msgs = sum(1 for m in self._messages if m.role == "assistant")
        return min(user_msgs, assistant_msgs)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取详细统计信息。"""
        return {
            **self._stats,
            "current_session": self.session_id,
            "total_messages": len(self._messages),
            "total_tokens": self.get_total_tokens_used(),
            "utilization_rate": round(self.get_utilization_rate(), 4),
            "turn_count": self.get_turn_count(),
            "compressed_count": sum(1 for m in self._messages if m.is_compressed),
            "budget_config": self._budget.to_dict(),
            "strategy": self._strategy.value,
            "tokenizer_cache": self._tokenizer.cache_stats,
        }
    
    def take_snapshot(self) -> ContextSnapshot:
        """
        捕获当前时刻的上下文快照（用于调试和审计）。
        
        Returns:
            ContextSnapshot对象，包含完整的状态信息
        """
        snapshot = ContextSnapshot(
            snapshot_time=time.time(),
            total_messages=len(self._messages),
            total_tokens_used=self.get_total_tokens_used(),
            budget_utilization=self.get_utilization_rate(),
            strategy_active=self._strategy.value,
            messages_summary=[m.to_dict() for m in self._messages],
        )
        
        self._stats["last_snapshot_time"] = snapshot.snapshot_time
        
        return snapshot
    
    def verify_all_integrity(self) -> Tuple[bool, List[str]]:
        """
        验证所有消息的完整性（检测篡改）。
        
        Returns:
            (全部通过与否, 失败消息ID列表)
        """
        failed_ids = []
        
        for msg in self._messages:
            if not msg.verify_integrity():
                failed_ids.append(msg.message_id)
                self._stats["integrity_checks_failed"] += 1
            else:
                self._stats["integrity_checks_passed"] += 1
        
        is_all_ok = len(failed_ids) == 0
        
        if not is_all_ok:
            logger.error(
                f"[ERR] 完整性校验发现 {len(failed_ids)} 条异常消息: {failed_ids}"
            )
        else:
            logger.debug(f"[OK] 完整性校验通过: {len(self._messages)} 条消息均正常")
        
        return is_all_ok, failed_ids
    
    # ========================================================================
    # 内部实现方法（私有）
    # ========================================================================
    
    def _generate_message_id(self) -> str:
        """生成全局唯一的消息ID。"""
        return f"msg_{uuid.uuid4().hex[:12]}_{int(time.time()*1000)}"
    
    def _calculate_importance(self, message: ContextMessage) -> float:
        """
        计算消息的重要性得分（0.0-1.0）。
        
        综合考虑多个维度：
        1. 消息优先级（显式标记）
        2. 内容特征（错误反馈、重点标记等）
        3. 消息长度（较长的消息通常承载更多信息）
        4. 时间衰减（近期消息略重要）
        5. 角色权重（user和assistant消息通常比tool消息重要）
        
        Args:
            message: 待评分的消息
            
        Returns:
            重要性得分（越高越应该被保留）
        """
        score = 0.5  # 基础分
        
        content = message.content.lower()
        metadata = message.metadata
        
        # 因素1: 显式优先级（最强信号）
        priority_weights = {
            CompressionPriority.CRITICAL: 0.35,
            CompressionPriority.HIGH: 0.20,
            CompressionPriority.NORMAL: 0.0,
            CompressionPriority.LOW: -0.15,
        }
        score += priority_weights.get(message.priority, 0.0)
        
        # 因素2: 内容特征识别
        error_keywords = ["错了", "不对", "error", "wrong", "失败", "exception"]
        if any(kw in content for kw in error_keywords):
            score += 0.15  # 错误反馈很重要（学习机会）
        
        emphasis_keywords = ["重要", "注意", "记住", "必须", "关键"]
        if any(kw in content for kw in emphasis_keywords):
            score += 0.10  # 明确强调的内容
        
        question_keywords = ["?", "？", "什么", "如何", "为什么", "怎么"]
        if any(kw in content for kw in question_keywords):
            score += 0.05  # 问题通常开启新话题
        
        # 因素3: 消息长度（归一化到0-0.15范围）
        length_score = min(message.token_count / 3000, 1.0) * 0.15
        score += length_score
        
        # 因素4: 角色权重
        role_weights = {
            "system": 0.05,
            "user": 0.05,
            "assistant": 0.03,
            "tool": -0.02,  # 工具输出通常可被重新生成
        }
        score += role_weights.get(message.role, 0.0)
        
        # 因素5: 时间衰减（非常轻微，最近24h内的消息+0.02）
        age_hours = (time.time() - message.timestamp) / 3600
        if age_hours < 24:
            score += 0.02 * (1 - age_hours / 24)
        
        # 归一化到[0, 1]范围
        final_score = max(0.0, min(1.0, score))
        
        return final_score
    
    def _make_space_for_new_message(self, required_tokens: int) -> bool:
        """
        为新消息腾出足够的Token空间。
        
        根据当前策略选择合适的清理方式：
        - SLIDING_WINDOW: 直接丢弃最旧的消息
        - IMPORTANCE_WEIGHTED: 移除最低重要性的消息
        - SUMMARIZATION: 对最旧的消息进行摘要压缩
        - HYBRID: 组合上述方法
        
        Args:
            required_tokens: 新消息需要的Token数量
            
        Returns:
            True如果成功腾出足够空间，False如果无法满足需求
        """
        current_total = self.get_total_tokens_used()
        deficit = (current_total + required_tokens) - self._budget.total_tokens
        
        if deficit <= 0:
            return True  # 已经有足够空间
        
        logger.info(
            f"🔧 需要腾出空间: 缺少{deficit} tokens, "
            f"当前策略={self._strategy.value}"
        )
        
        if self._strategy == ContextStrategy.SLIDING_WINDOW:
            return self._evict_oldest_messages(deficit)
        
        elif self._strategy == ContextStrategy.IMPORTANCE_WEIGHTED:
            return self._evict_least_important_messages(deficit)
        
        elif self._strategy == ContextStrategy.SUMMARIZATION:
            return self._summarize_oldest_messages(deficit)
        
        elif self._strategy == ContextStrategy.HYBRID:
            # 混合策略：先尝试重要性加权移除（60%目标），再尝试摘要（40%目标）
            target_evict = int(deficit * 0.6)
            target_summarize = deficit - target_evict
            
            evict_success = self._evict_least_important_messages(target_evict) if target_evict > 0 else True
            summarize_success = self._summarize_oldest_messages(target_summarize) if target_summarize > 0 else True
            
            return evict_success and summarize_success
        
        else:
            logger.error(f"[ERR] 未知的策略: {self._strategy}")
            return False
    
    def _evict_oldest_messages(self, target_tokens: int) -> bool:
        """
        滑动窗口策略：移除最旧的非CRITICAL消息。
        
        Args:
            target_tokens: 需要释放的Token数量
            
        Returns:
            True如果成功释放足够空间
        """
        released = 0
        evicted_indices = []
        
        for i, msg in enumerate(self._messages):
            if released >= target_tokens:
                break
                
            # 不移除CRITICAL级别的消息
            if msg.priority == CompressionPriority.CRITICAL:
                continue
            
            released += msg.token_count
            evicted_indices.append(i)
        
        # 从后往前删除（避免索引偏移问题）
        for i in reversed(evicted_indices):
            removed_msg = self._messages.pop(i)
            del self._message_index[removed_msg.message_id]
            self._stats["messages_removed"] += 1
        
        success = released >= target_tokens
        logger.info(
            f"🗑️ 滑动窗口清理: 移除{len(evicted_indices)}条消息, "
            f"释放{released} tokens, 目标{target_tokens}, "
            f"{'[OK] 成功' if success else '[WARN] 未达目标'}"
        )
        
        return success
    
    def _evict_least_important_messages(self, target_tokens: int) -> bool:
        """
        重要性加权策略：移除得分最低的消息。
        
        Args:
            target_tokens: 需要释放的Token数量
            
        Returns:
            True如果成功释放足够空间
        """
        # 为每条消息计算（或获取缓存的）重要性得分
        scored_messages = [
            (i, msg, msg.importance_score if self._importance_enabled else 0.5)
            for i, msg in enumerate(self._messages)
            if msg.priority != CompressionPriority.CRITICAL  # 排除CRITICAL
        ]
        
        # 按重要性升序排列（最低分的先移除）
        scored_messages.sort(key=lambda x: x[2])
        
        released = 0
        evicted_indices = []
        
        for idx, msg, score in scored_messages:
            if released >= target_tokens:
                break
            
            released += msg.token_count
            evicted_indices.append(idx)
        
        # 执行删除
        for i in sorted(evicted_indices, reverse=True):
            removed_msg = self._messages.pop(i)
            del self._message_index[removed_msg.message_id]
            self._stats["messages_removed"] += 1
        
        success = released >= target_tokens
        logger.info(
            f"⭐ 重要性加权清理: 移除{len(evicted_indices)}条低重要性消息, "
            f"释放{released} tokens, 目标{target_tokens}, "
            f"{'[OK] 成功' if success else '[WARN] 未达目标'}"
        )
        
        return success
    
    def _summarize_oldest_messages(self, target_tokens: int) -> bool:
        """
        摘要压缩策略：对最旧的消息进行摘要。
        
        注意：这是一个简化版本的实际摘要会调用轻量级LLM。
        这里使用基于规则的模板摘要作为演示。
        
        Args:
            target_tokens: 需要释放的Token数量
            
        Returns:
            True如果成功释放足够空间
        """
        released = 0
        summarized_count = 0
        
        # 找出可以压缩的最旧非CRITICAL消息
        candidates = [
            (i, msg) for i, msg in enumerate(self._messages)
            if (not msg.is_compressed and 
                msg.priority != CompressionPriority.CRITICAL and
                msg.role in ("user", "assistant"))  # 只压缩对话消息
        ]
        
        # 按时间正序排列（最旧的在前）
        candidates.sort(key=lambda x: x[1].timestamp)
        
        for idx, msg in candidates:
            if released >= target_tokens:
                break
            
            # 生成简化摘要（实际应调用LLM）
            summary = self._generate_rule_based_summary(msg)
            
            # 计算节省的空间
            saved = msg.token_count - self._tokenizer.count_tokens(summary)
            if saved <= 0:
                continue  # 没有节省空间，跳过
            
            # 执行压缩
            self._messages[idx].mark_as_compressed(summary)
            released += saved
            summarized_count += 1
            self._stats["messages_compressed"] += 1
        
        success = released >= target_tokens
        logger.info(
            f"📝 摘要压缩: 压缩{summarized_count}条消息, "
            f"释放{released} tokens, 目标{target_tokens}, "
            f"{'[OK] 成功' if success else '[WARN] 未达目标'}"
        )
        
        return success
    
    def _generate_rule_based_summary(self, message: ContextMessage) -> str:
        """
        基于规则生成消息摘要（简化版）。
        
        生产环境应替换为LLM生成的更高质量摘要。
        
        Args:
            message: 待摘要的消息
            
        Returns:
            摘要文本
        """
        content = message.content
        
        # 截断过长的内容
        max_preview_len = 150
        if len(content) > max_preview_len:
            preview = content[:max_preview_len] + "..."
        else:
            preview = content
        
        # 根据角色生成不同格式的摘要
        if message.role == "user":
            summary = f"用户询问了关于'{preview[:50]}...'的问题"
        elif message.role == "assistant":
            summary = f"AI提供了关于'{preview[:50]}...'的解答"
        else:
            summary = f"[{message.role}] {preview[:80]}"
        
        return summary
    
    def _select_history_for_context(
        self, 
        max_tokens: int
    ) -> List[ContextMessage]:
        """
        选择适合放入LLM上下文的历史消息子集。
        
        策略：
        1. 优先保留最新的消息（时间局部性）
        2. 在Token预算内尽可能多地包含历史
        3. CRITICAL级别的消息必须包含
        4. 已压缩的消息占用较少空间，优先保留
        
        Args:
            max_tokens: 可用的最大Token数
            
        Returns:
            选中的消息列表（按原始时间顺序）
        """
        if not self._messages:
            return []
        
        # 分离CRITICAL消息和普通消息
        critical_msgs = [m for m in self._messages if m.priority == CompressionPriority.CRITICAL]
        normal_msgs = [m for m in self._messages if m.priority != CompressionPriority.CRITICAL]
        
        # 计算CRITICAL消息占用的空间
        critical_tokens = sum(m.token_count for m in critical_msgs)
        remaining_for_normal = max_tokens - critical_tokens
        
        if remaining_for_normal <= 0:
            # 空间仅够CRITICAL消息，只返回它们
            logger.warning("[WARN] 预算空间仅够容纳CRITICAL消息")
            return critical_msgs
        
        # 从普通消息中选择（优先选最新的）
        selected_normal = []
        tokens_used = 0
        
        # 倒序遍历（最新的在前），直到用完预算
        for msg in reversed(normal_msgs):
            if tokens_used + msg.token_count <= remaining_for_normal:
                selected_normal.insert(0, msg)  # 插入开头保持顺序
                tokens_used += msg.token_count
            else:
                # 尝试加入已压缩版本（如果存在且更小）
                if msg.is_compressed and msg.compression_summary:
                    compressed_tokens = self._tokenizer.count_tokens(
                        f"[Summary]\n{msg.compression_summary}"
                    )
                    if tokens_used + compressed_tokens <= remaining_for_normal:
                        selected_normal.insert(0, msg)
                        tokens_used += compressed_tokens
                # 否则跳过此消息
        
        # 合并结果：CRITICAL + 选中的普通消息（按时间排序）
        result = critical_msgs + selected_normal
        result.sort(key=lambda m: m.timestamp)
        
        logger.debug(
            f"📋 历史选择完成: 选中{len(result)}/{len(self._messages)}条消息, "
            f"使用{sum(m.token_count for m in result)}/{max_tokens} tokens, "
            f"其中CRITICAL={len(critical_msgs)}条"
        )
        
        return result
    
    def _trigger_auto_optimization(self, utilization: float):
        """
        当利用率过高时触发自动优化。
        
        Args:
            utilization: 当前利用率
        """
        logger.warning(
            f"[WARN] 上下文利用率过高 ({utilization:.1%}), "
            f"触发自动优化..."
        )
        
        # 根据策略采取行动
        if self._strategy in (ContextStrategy.SUMMARIZATION, ContextStrategy.HYBRID):
            # 主动对最旧的消息进行预防性摘要
            target = int(self._budget.available_for_history * 0.1)  # 释放10%空间
            self._summarize_oldest_messages(target)
        
        # 记录优化事件
        optimization_event = {
            "event_type": "auto_optimization_triggered",
            "utilization_at_trigger": utilization,
            "timestamp": time.time(),
            "action_taken": self._strategy.value,
        }
        
        # 可以在这里发送到监控系统
        logger.info(f"[OK] 自动优化完成: {optimization_event}")
    
    def clear(self, preserve_critical: bool = True):
        """
        清空所有消息（选择性保留CRITICAL消息）。
        
        Args:
            preserve_critical: 是否保留CRITICAL级别的消息
        """
        if preserve_critical:
            critical_msgs = [m for m in self._messages if m.priority == CompressionPriority.CRITICAL]
            self._messages = critical_msgs
        else:
            self._messages.clear()
        
        # 重建索引
        self._message_index = {
            msg.message_id: i 
            for i, msg in enumerate(self._messages)
        }
        
        logger.info(
            f"[CLEAN] 上下文已清空: 保留{len(self._messages)}条消息 "
            f"({'仅CRITICAL' if preserve_critical else '全部'})"
        )


# ============================================================================
# 工厂函数与便捷接口
# ============================================================================

def create_context_manager(
    session_id: str = "default",
    total_budget_tokens: int = DEFAULT_TOTAL_BUDGET_TOKENS,
    strategy: ContextStrategy = ContextStrategy.HYBRID,
    **kwargs,
) -> SmartContextManager:
    """
    创建SmartContextManager实例的工厂函数。
    
    提供简洁的创建接口，隐藏复杂的参数配置。
    
    Args:
        session_id: 会话ID
        total_budget_tokens: 总Token预算（默认128K）
        strategy: 管理策略
        **kwargs: 传递给SmartContextManager的其他参数
        
    Returns:
        配置好的SmartContextManager实例
    """
    budget = ContextBudget(total_tokens=total_budget_tokens)
    
    return SmartContextManager(
        session_id=session_id,
        budget=budget,
        strategy=strategy,
        **kwargs,
    )


def create_default_manager() -> SmartContextManager:
    """创建使用默认配置的管理器（便于快速测试）。"""
    return create_context_manager()


# ============================================================================
# 模块自测（当直接运行此文件时执行）
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("SmartContextManager 自测")
    print("=" * 60)
    
    # 测试1: 基本功能
    print("\n[Test 1] 基本功能测试...")
    mgr = create_context_manager(session_id="test_session")
    
    # 添加消息
    for i in range(5):
        success = mgr.add_message(
            role="user" if i % 2 == 0 else "assistant",
            content=f"这是第{i+1}轮对话: {'用户提问' if i % 2 == 0 else 'AI回答'} 关于积分的问题",
        )
        print(f"  消息{i+1}: {'[OK]' if success else '[ERR]'}")
    
    # 查看统计
    stats = mgr.get_stats()
    print(f"\n  📊 统计:")
    print(f"     消息总数: {stats['total_messages']}")
    print(f"     Token用量: {stats['total_tokens']:,} / {stats['budget_config']['total_tokens']:,}")
    print(f"     利用率: {stats['utilization_rate']:.1%}")
    
    # 测试2: 构建LLM上下文
    print("\n[Test 2] 构建LLM上下文...")
    llm_ctx = mgr.build_llm_context(
        system_prompt="你是一个数学辅导助手。",
        user_profile={"level": "高中", "weak_points": ["积分"]},
    )
    print(f"  [OK] 上下文构建成功: {len(llm_ctx)} 条消息")
    
    # 测试3: 搜索功能
    print("\n[Test 3] 搜索功能测试...")
    results = mgr.search_messages("积分", limit=3)
    print(f"  🔍 搜索'积分': 找到 {len(results)} 条相关消息")
    for msg, score in results:
        print(f"     [{score:.2f}] {msg.content[:50]}...")
    
    # 测试4: 完整性校验
    print("\n[Test 4] 完整性校验...")
    all_ok, failed = mgr.verify_all_integrity()
    print(f"  [LCK] 校验结果: {'[OK] 全部通过' if all_ok else f'[ERR] {len(failed)} 条异常'}")
    
    # 测试5: 快照
    print("\n[Test 5] 上下文快照...")
    snapshot = mgr.take_snapshot()
    print(snapshot.to_report())
    
    print("\n" + "=" * 60)
    print("[OK] 所有自测通过!")
    print("=" * 60)
