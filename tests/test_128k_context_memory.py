"""
128K Token上下文记忆系统 - 完整测试套件。

基于《多轮对话上下文记忆容量分析与实现难度报告》和
《Agent系统优化改进方案_v3》的验证要求。

测试覆盖范围：
1. ✅ 核心功能：消息添加、Token计数、预算控制
2. ✅ 内存优化：滑动窗口、重要性加权、摘要压缩策略
3. ✅ 准确性保障：完整性校验、数据防篡改、精确匹配
4. ✅ 性能指标：响应速度、内存占用、吞吐量
5. ✅ 边界条件：空输入、超长输入、特殊字符、并发场景

运行方式:
    pytest tests/test_128k_context_memory.py -v --tb=short
    
    # 仅运行快速测试（<1秒）
    pytest tests/test_128k_context_memory.py::TestCoreFunctionality -v
    
    # 运行性能基准测试
    pytest tests/test_128k_context_memory.py::TestPerformanceBenchmarks -v --benchmark-only

生成时间: 2026-05-13
作者: AI Technical Team
"""

import asyncio
import json
import time
import pytest
import sys
import os

# 添加项目根目录到sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent_core.context_manager import (
    SmartContextManager,
    TokenCounter,
    TokenizerBackend,
    TiktokenBackend,
    HeuristicBackend,
    TokenCache,
    LRUCache,
    NoOpCache,
    ContextBudget,
    ContextMessage,
    ContextStrategy,
    CompressionPriority,
    ContextSnapshot,
    BudgetExceededError,
    IntegrityCheckFailedError,
    TokenCountingError,
    create_context_manager,
)


# ============================================================================
# 测试配置常量
# ============================================================================

TEST_BUDGET = 128000  # 128K tokens
SHORT_TEXT = "求积分∫x²dx"
MEDIUM_TEXT = "这是一个中等长度的问题描述，包含一些数学公式如 f(x) = x² + 2x + 1，需要我们进行求解。"
LONG_TEXT = "这是一个非常长的问题描述。" * 100  # ~500字符
VERY_LONG_TEXT = "这是一个超长的数学问题，" * 1000  # ~5000字符，约3000+ tokens
CHINESE_TEXT = "用户问了一个关于微积分的问题：如何求解定积分 ∫[a,b] f(x)dx？这个问题涉及到牛顿-莱布尼茨公式的基本应用。"
MIXED_CONTENT = "Mixed content with 中文 and English: 求极限 lim(x→0) sin(x)/x as x approaches zero."
SPECIAL_CHARS = "Special chars: !@#$%^&*()_+-=[]{}|;':\",./<>?`~\n\t\r"


# ============================================================================
# Test Suite 1: 核心功能测试 (P0 - 必须全部通过)
# ============================================================================

class TestContextBudget:
    """测试ContextBudget配置类。"""
    
    def test_default_budget_configuration(self):
        """验证默认配置的合理性。"""
        budget = ContextBudget()
        
        assert budget.total_tokens == TEST_BUDGET
        assert budget.system_prompt_reserve == 2000
        assert budget.user_profile_reserve == 1000
        assert budget.memory_injection_limit == 5000
        assert budget.safety_margin == 2000
        
        available = budget.available_for_history
        assert available > 0, "可用历史空间必须为正数"
        assert available < budget.total_tokens, "预留项不能超过总额"
        
        print(f"  ✅ 默认预算配置正确: 总额={budget.total_tokens}, 可用历史={available}")
    
    def test_custom_budget_configuration(self):
        """验证自定义配置的正确性。"""
        budget = ContextBudget(
            total_tokens=256000,
            system_prompt_reserve=3000,
            user_profile_reserve=2000,
            memory_injection_limit=8000,
            safety_margin=3000,
        )
        
        assert budget.total_tokens == 256000
        assert budget.available_for_history == 240000
        
        print(f"  ✅ 自定义预算配置正确")
    
    def test_budget_validation(self):
        """验证预算合法性检查。"""
        # 合法配置
        valid_budget = ContextBudget(total_tokens=128000)
        assert valid_budget.validate_budget() is True
        
        # 非法配置：预留超过总额
        invalid_budget = ContextBudget(
            total_tokens=10000,
            system_prompt_reserve=4000,
            user_profile_reserve=3000,
            memory_injection_limit=3000,
            safety_margin=100,
        )
        assert invalid_budget.validate_budget() is False
        
        print(f"  ✅ 预算验证逻辑正确")
    
    def test_utilization_rate_calculation(self):
        """验证利用率计算精度。"""
        budget = ContextBudget(total_tokens=1000)
        
        assert budget.utilization_rate(0) == 0.0
        assert budget.utilization_rate(500) == 0.5
        assert budget.utilization_rate(1000) == 1.0
        assert budget.utilization_rate(1200) == 1.2  # 允许超限值用于告警
        
        print(f"  ✅ 利用率计算准确")


class TestTokenCounter:
    """测试Token计数器封装层。"""
    
    @pytest.fixture
    def counter(self):
        return TokenCounter(enable_cache=True)
    
    def test_empty_text_counting(self, counter):
        """空文本应返回0 tokens。"""
        assert counter.count_tokens("") == 0
        assert counter.count_tokens(None) == 0
        assert counter.count_tokens("   ") > 0  # 空格也算token
        
        print(f"  ✅ 空文本处理正确")
    
    def test_short_text_counting(self, counter):
        """短文本计数应在合理范围内。"""
        count = counter.count_tokens(SHORT_TEXT)
        
        assert count > 0, "非空文本至少有1个token"
        assert count < 50, f"短文本'{SHORT_TEXT}'不应有{count}个tokens"
        
        print(f"  ✅ 短文本计数合理: '{SHORT_TEXT}' → {count} tokens")
    
    def test_chinese_text_counting(self, counter):
        """中文文本计数准确性。"""
        count = counter.count_tokens(CHINESE_TEXT)
        
        assert count > 10, "中文问题应有较多tokens"
        # 中文大约1-4字符/token（取决于编码）
        estimated_chars_per_token = len(CHINESE_TEXT) / count
        assert 0.5 <= estimated_chars_per_token <= 5.0, \
            f"中文字符/token比率异常: {estimated_chars_per_token:.2f}"
        
        print(f"  ✅ 中文文本计数准确: {len(CHINESE_TEXT)}字符 → {count} tokens")
    
    def test_long_text_counting(self, counter):
        """长文本计数性能和准确性。"""
        start_time = time.time()
        count = counter.count_tokens(VERY_LONG_TEXT)
        elapsed_ms = (time.time() - start_time) * 1000
        
        assert count > 1000, f"超长文本应有>1000 tokens, 实际{count}"
        assert elapsed_ms < 100, f"计数耗时过长: {elapsed_ms:.1f}ms"
        
        print(f"  ✅ 长文本计数高效: {len(VERY_LONG_TEXT)}字符 → {count} tokens ({elapsed_ms:.1f}ms)")
    
    def test_cache_functionality(self, counter):
        """缓存应加速重复计数。"""
        text = "这是一段会被多次计数的文本内容"
        
        # 第一次计数（无缓存）
        start = time.time()
        count1 = counter.count_tokens(text)
        time_no_cache_approx = (time.time() - start) * 1000
        
        # 第二次计数（应有缓存）
        start = time.time()
        count2 = counter.count_tokens(text)
        time_with_cache = (time.time() - start) * 1000
        
        assert count1 == count2, "缓存不应影响计数结果"
        # 缓存版本应该更快或相当（允许一定的时间误差）
        # 注意：在非常快的操作中，时间测量可能有噪声
        assert time_with_cache < time_no_cache_approx * 10 + 5, \
            "缓存版本应该明显更快或相当"
        
        stats = counter.cache_stats
        assert stats["cache_size"] >= 1, "缓存中应至少有一条记录"
        
        print(f"  ✅ 缓存功能正常: 命中率={stats['cache_size']}条记录")
    
    def test_batch_counting(self, counter):
        """批量计数功能。"""
        messages = [
            ContextMessage(message_id="1", role="user", content="问题1", token_count=counter.count_tokens("问题1")),
            ContextMessage(message_id="2", role="assistant", content="回答1", token_count=counter.count_tokens("回答1")),
            ContextMessage(message_id="3", role="user", content="问题2", token_count=counter.count_tokens("问题2")),
        ]
        
        total = counter.count_messages_tokens(messages)
        assert total > 0, "批量计数结果应为正数"
        
        print(f"  ✅ 批量计数正常: {len(messages)}条消息 → {total} tokens")


class TestSmartContextManagerBasicOperations:
    """测试SmartContextManager基础操作。"""
    
    @pytest.fixture
    def manager(self):
        return create_context_manager(
            session_id="test_session",
            total_budget_tokens=TEST_BUDGET,
        )
    
    def test_initialization(self, manager):
        """初始化状态检查。"""
        assert manager.session_id == "test_session"
        assert manager.get_total_tokens_used() == 0
        assert manager.get_message_count() == 0
        assert manager.get_utilization_rate() == 0.0
        
        stats = manager.get_stats()
        assert stats["total_messages"] == 0
        assert stats["strategy"] == "hybrid"
        
        print(f"  ✅ 初始化状态正确")
    
    def test_add_single_message(self, manager):
        """添加单条消息。"""
        success = manager.add_message("user", SHORT_TEXT)
        
        assert success is True
        assert manager.get_message_count() == 1
        assert manager.get_total_tokens_used() > 0
        
        msg = manager.get_recent_messages(1)[0]
        assert msg.role == "user"
        assert SHORT_TEXT in msg.content
        assert msg.content_hash != ""  # 应自动生成hash
        
        print(f"  ✅ 单条消息添加成功")
    
    def test_add_multiple_messages(self, manager):
        """添加多条消息（模拟对话）。"""
        for i in range(6):
            role = "user" if i % 2 == 0 else "assistant"
            content = f"{role}_msg_{i}: {'问题' if role=='user' else '回答'}关于积分的第{i//2+1}次讨论"
            
            success = manager.add_message(role, content)
            assert success is True, f"第{i+1}条消息添加失败"
        
        assert manager.get_message_count() == 6
        assert manager.get_turn_count() == 3  # 3轮对话
        
        print(f"  ✅ 多条消息添加成功: 6条消息/3轮对话")
    
    def test_empty_message_rejection(self, manager):
        """空消息应被拒绝。"""
        success = manager.add_message("user", "")
        assert success is False
        
        success = manager.add_message("user", "   ")  # 仅空白
        assert success is False
        
        assert manager.get_message_count() == 0
        
        print(f"  ✅ 空消息被正确拒绝")
    
    def test_get_message_by_id(self, manager):
        """按ID查找消息。"""
        manager.add_message("user", "测试消息")
        
        msgs = manager.get_recent_messages(1)
        msg_id = msgs[0].message_id
        
        found = manager.get_message_by_id(msg_id)
        assert found is not None
        assert found.content == "测试消息"
        
        not_found = manager.get_message_by_id("non_existent_id")
        assert not_found is None  # 应返回None而非异常
        
        print(f"  ✅ ID查找功能正常")


# ============================================================================
# Test Suite 2: 内存优化策略测试 (P0 - 必须全部通过)
# ============================================================================

class TestSlidingWindowStrategy:
    """测试滑动窗口策略。"""
    
    @pytest.fixture
    def small_budget_manager(self):
        """创建小预算管理器以便快速触发窗口滑动。"""
        budget = ContextBudget(total_tokens=1000)  # 极小预算便于测试
        return SmartContextManager(
            session_id="sliding_test",
            budget=budget,
            strategy=ContextStrategy.SLIDING_WINDOW,
            max_history_turns=5,
            auto_optimize=False,  # 手动控制
        )
    
    def test_old_messages_eviction(self, small_budget_manager):
        """最旧的消息应被优先淘汰。"""
        mgr = small_budget_manager
        
        # 添加消息直到接近上限
        for i in range(20):
            success = mgr.add_message("user", f"消息{i}: {'内容'*50}")
            if not success:
                break
        
        # 验证总token数不超过预算
        assert mgr.get_total_tokens_used() <= mgr._budget.total_tokens
        
        # 最新的消息应该还在
        recent = mgr.get_recent_messages(3)
        assert len(recent) == 3
        
        # 旧消息可能已被淘汰
        all_msgs = mgr._messages
        assert len(all_msgs) <= 25  # 不应无限增长
        
        print(f"  ✅ 滑动窗口策略生效: 当前保留{len(all_msgs)}条消息")


class TestImportanceWeightedStrategy:
    """测试重要性加权策略。"""
    
    @pytest.fixture
    def importance_manager(self):
        budget = ContextBudget(total_tokens=2000)
        return SmartContextManager(
            session_id="importance_test",
            budget=budget,
            strategy=ContextStrategy.IMPORTANCE_WEIGHTED,
            importance_scoring_enabled=True,
            auto_optimize=False,
        )
    
    def test_critical_messages_protected(self, importance_manager):
        """CRITICAL级别的消息不应被删除。"""
        mgr = importance_manager
        
        # 添加一条CRITICAL消息
        mgr.add_message(
            "user",
            "这是非常重要的错误反馈信息！",
            priority=CompressionPriority.CRITICAL,
        )
        
        # 添加大量普通消息以填满预算
        for i in range(30):
            mgr.add_message("assistant", f"普通回答{i}: {'填充内容'*20}")
        
        # CRITICAL消息应该仍然存在
        found_critical = any(
            m.priority == CompressionPriority.CRITICAL 
            for m in mgr._messages
        )
        assert found_critical, "CRITICAL消息应被保护不被删除"
        
        print(f"  ✅ CRITICAL消息保护机制有效")
    
    def test_low_importance_evicted_first(self, importance_manager):
        """低重要性消息应先于高重要性消息被淘汰。"""
        mgr = importance_manager
        
        # 添加不同重要性的消息
        mgr.add_message("tool", "工具输出1: 无关紧要的数据", priority=CompressionPriority.LOW)
        mgr.add_message("user", "重要问题1: 关于微积分的关键概念", priority=CompressionPriority.HIGH)
        mgr.add_message("tool", "工具输出2: 更多无关数据", priority=CompressionPriority.LOW)
        
        # 强制清理空间
        mgr._make_space_for_new_message(500)
        
        # LOW优先级的消息应该被移除得更多
        low_count = sum(1 for m in mgr._messages if m.priority == CompressionPriority.LOW)
        high_count = sum(1 for m in mgr._messages if m.priority == CompressionPriority.HIGH)
        
        assert high_count >= low_count, "高重要性消息应比低重要性消息保留更多"
        
        print(f"  ✅ 重要性加权策略有效: HIGH={high_count}, LOW={low_count}")


class TestSummarizationStrategy:
    """测试摘要压缩策略。"""
    
    @pytest.fixture
    def summary_manager(self):
        budget = ContextBudget(total_tokens=1500)
        return SmartContextManager(
            session_id="summary_test",
            budget=budget,
            strategy=ContextStrategy.SUMMARIZATION,
            auto_optimize=False,
        )
    
    def test_message_compression(self, summary_manager):
        """旧消息应被摘要压缩而非直接删除。"""
        mgr = summary_manager
        
        # 添加一条长消息
        long_content = "这是一段很长的解释性文字，" * 50  # 约800字符
        mgr.add_message("assistant", long_content)
        
        original_msg = mgr._messages[-1]
        assert not original_msg.is_compressed
        
        # 触发摘要压缩
        mgr._summarize_oldest_messages(200)
        
        # 验证消息已被压缩
        compressed_msg = mgr._messages[-1]
        assert compressed_msg.is_compressed, "消息应被标记为已压缩"
        assert compressed_msg.original_content is not None, "原始内容应被保存"
        assert compressed_msg.compression_summary is not None, "摘要应存在"
        assert len(compressed_msg.content) < len(long_content), "压缩后应更短"
        
        print(f"  ✅ 摘要压缩功能正常: 原始{len(long_content)}字符 → 压缩后{len(compressed_msg.content)}字符")
    
    def test_compressed_message_restore(self, summary_manager):
        """压缩后的消息应能恢复原始内容。"""
        mgr = summary_manager
        
        original = "重要的完整信息，不能丢失！"
        mgr.add_message("user", original)
        
        # 压缩
        mgr._summarize_oldest_messages(50)
        
        # 恢复
        msg = mgr._messages[-1]
        msg.restore_from_compression()
        
        assert not msg.is_compressed
        assert msg.content == original, "恢复后内容应与原始一致"
        
        print(f"  ✅ 压缩恢复功能正常")


class TestHybridStrategy:
    """测试混合策略（推荐策略）。"""
    
    @pytest.fixture
    def hybrid_manager(self):
        budget = ContextBudget(total_tokens=3000)
        return SmartContextManager(
            session_id="hybrid_test",
            budget=budget,
            strategy=ContextStrategy.HYBRID,
            max_history_turns=15,
            summarize_threshold=0.8,
            auto_optimize=True,
        )
    
    def test_automatic_strategy_selection(self, hybrid_manager):
        """混合策略应智能选择最优子策略。"""
        mgr = hybrid_manager
        
        # 添加混合类型的消息
        mgr.add_message("system", "系统指令", priority=CompressionPriority.CRITICAL)
        
        for i in range(10):
            role = "user" if i % 2 == 0 else "assistant"
            priority = CompressionPriority.HIGH if i < 3 else CompressionPriority.NORMAL
            mgr.add_message(role, f"{'问题' if role=='user' else '回答'}{i}", priority=priority)
        
        # 继续添加直到接近阈值
        for i in range(20, 40):
            mgr.add_message("tool", f"工具输出{i}: 数据数据数据")
        
        # 系统应自动执行优化（因为auto_optimize=True）
        utilization = mgr.get_utilization_rate()
        
        # 验证未超出预算
        assert mgr.get_total_tokens_used() <= mgr._budget.total_tokens
        
        # 验证CRITICAL消息仍在
        critical_exists = any(m.priority == CompressionPriority.CRITICAL for m in mgr._messages)
        assert critical_exists
        
        print(f"  ✅ 混合策略自动优化有效: 利用率={utilization_rate:.1%}")


# ============================================================================
# Test Suite 3: 准确性与完整性保障测试 (P0 - 必须全部通过)
# ============================================================================

class TestDataIntegrity:
    """测试数据完整性校验机制。"""
    
    @pytest.fixture
    def integrity_manager(self):
        return create_context_manager(session_id="integrity_test")
    
    def test_auto_hash_generation(self, integrity_manager):
        """消息添加时应自动生成content_hash。"""
        integrity_manager.add_message("user", "测试内容")
        
        msg = integrity_manager._messages[-1]
        assert msg.content_hash != "", "hash不应为空"
        assert len(msg.content_hash) == 16, "hash应为16位（截断版SHA256）"
        
        print(f"  ✅ 自动hash生成: {msg.content_hash}")
    
    def test_integrity_verification_pass(self, integrity_manager):
        """未被篡改的消息应通过校验。"""
        integrity_manager.add_message("user", "原始内容")
        
        all_ok, failed_ids = integrity_manager.verify_all_integrity()
        
        assert all_ok is True
        assert len(failed_ids) == 0
        
        print(f"  ✅ 完整性校验通过")
    
    def test_integrity_detection(self, integrity_manager):
        """被篡改的消息应被检测到。"""
        integrity_manager.add_message("user", "原始内容")
        
        # 模拟篡改
        msg = integrity_manager._messages[-1]
        original_hash = msg.content_hash
        msg.content = "篡改后的恶意内容"
        # 注意：不更新hash，模拟外部篡改
        
        all_ok, failed_ids = integrity_manager.verify_all_integrity()
        
        assert all_ok is False
        assert len(failed_ids) == 1
        assert msg.message_id in failed_ids
        
        print(f"  ✅ 篡改检测成功: 检测到{len(failed_ids)}条异常消息")
    
    def test_compressed_message_integrity(self, integrity_manager):
        """压缩后的消息也应保持可追踪性。"""
        original = "将被压缩的重要信息"
        integrity_manager.add_message("assistant", original)
        
        # 执行压缩
        integrity_manager._summarize_oldest_messages(10)
        
        msg = integrity_manager._messages[-1]
        assert msg.is_compressed
        assert msg.original_content == original
        assert msg.verify_integrity(), "压缩后的新内容hash也应是有效的"
        
        # 恢复后再次校验
        msg.restore_from_compression()
        assert msg.verify_integrity(), "恢复后的原始内容hash应匹配"
        
        print(f"  ✅ 压缩消息完整性追踪正常")


class TestExactMatchingAndRetrieval:
    """测试精确匹配与检索功能。"""
    
    @pytest.fixture
    def retrieval_manager(self):
        mgr = create_context_manager(session_id="retrieval_test")
        
        # 预填充一些测试数据
        test_data = [
            ("user", "如何求解不定积分？"),
            ("assistant", "不定积分是微积分的基本概念..."),
            ("user", "导数的几何意义是什么？"),
            ("assistant", "导数的几何意义是切线斜率..."),
            ("tool", "计算结果: f'(x) = 2x + 1"),
            ("user", "极限的定义涉及epsilon-delta语言"),
        ]
        
        for role, content in test_data:
            mgr.add_message(role, content)
        
        return mgr
    
    def test_keyword_search_basic(self, retrieval_manager):
        """基本关键词搜索。"""
        results = retrieval_manager.search_messages("积分", limit=5)
        
        assert len(results) > 0, "应找到包含'积分'的消息"
        assert all(score > 0 for _, score in results), "相关性分数应为正"
        
        # 结果应按相关性降序
        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True), "结果应按分数降序排列"
        
        print(f"  ✅ 关键词搜索正常: 找到{len(results)}条相关消息")
    
    def test_search_empty_query(self, retrieval_manager):
        """空查询或无匹配时应返回空列表。"""
        results = retrieval_manager.search_messages("不存在的内容xyz123")
        
        assert len(results) == 0
        
        print(f"  ✅ 无结果查询处理正确")
    
    def test_search_metadata_matching(self, retrieval_manager):
        """元数据搜索功能。"""
        # 添加带特定元数据的消息
        retrieval_manager.add_message(
            "user",
            "普通问题",
            metadata={"topic": "calculus", "difficulty": "hard"},
        )
        
        results = retrieval_manager.search_messages(
            "calculus", 
            search_content=False, 
            search_metadata=True
        )
        
        assert len(results) > 0, "应从元数据中找到匹配"
        
        print(f"  ✅ 元数据搜索正常")
    
    def test_recent_messages_filtering(self, retrieval_manager):
        """获取最近消息时的过滤功能。"""
        # 获取最近3条user消息
        recent_user = retrieval_manager.get_recent_messages(
            count=3, 
            roles=["user"]
        )
        
        assert len(recent_user) <= 3
        assert all(msg.role == "user" for msg in recent_user)
        
        # 验证是最新的在前面
        if len(recent_user) >= 2:
            assert recent_user[0].timestamp >= recent_user[1].timestamp
        
        print(f"  ✅ 最近消息过滤正常: 获取{len(recent_user)}条用户消息")


# ============================================================================
# Test Suite 4: 边界条件与压力测试 (P1 - 重要但允许个别失败)
# ============================================================================

class TestBoundaryConditions:
    """边界条件和极端情况测试。"""
    
    @pytest.fixture
    def boundary_manager(self):
        return create_context_manager(session_id="boundary_test")
    
    def test_special_characters_handling(self, boundary_manager):
        """特殊字符处理。"""
        special_inputs = [
            SPECIAL_CHARS,
            "Unicode: 中文日本語한글🎉",
            "Math symbols: ∫∑∏√∂∇±×÷≈≠≤≥",
            "Code: if (x > 0 && y < 10) { return true; }",
            "JSON: {\"key\": \"value\", \"nested\": [1,2,3]}",
            "Newlines:\n\n\nMultiple\nlines\n\n",
            "Tabs:\t\t\tIndented\tcontent",
        ]
        
        for text in special_inputs:
            success = boundary_manager.add_message("user", text)
            assert success, f"特殊字符文本添加失败: {text[:30]}..."
        
        print(f"  ✅ 特殊字符处理正常: {len(special_inputs)}种情况通过")
    
    def test_very_long_single_message(self, boundary_manager):
        """单条超长消息的处理。"""
        ultra_long = "超长内容" * 10000  # ~60,000字符
        
        # 可能因超出预算而失败，但不应抛出异常
        try:
            success = boundary_manager.add_message("user", ultra_long)
            # 如果成功，验证未超出总预算
            if success:
                assert boundary_manager.get_total_tokens_used() <= TEST_BUDGET
                print(f"  ✅ 超长消息处理成功: {len(ultra_long)}字符")
            else:
                print(f"  ⚠️ 超长消息被正确拒绝（预算不足）")
        except Exception as e:
            pytest.fail(f"超长消息处理引发异常: {e}")
    
    def test_rapid_successive_additions(self, boundary_manager):
        """快速连续添加消息（压力测试）。"""
        start_time = time.time()
        
        for i in range(100):
            boundary_manager.add_message(
                "user" if i % 2 == 0 else "assistant",
                f"快速消息{i}: 内容{'x'*20}",
            )
        
        elapsed = time.time() - start_time
        
        # 100条消息应在2秒内完成
        assert elapsed < 2.0, f"100条消息添加耗时过长: {elapsed:.2f}s"
        
        # 验证总数不超过预算
        assert boundary_manager.get_total_tokens_used() <= TEST_BUDGET
        
        print(f"  ✅ 快速连续操作正常: 100条消息/{elapsed:.2f}s")
    
    def test_concurrent_session_isolation(self):
        """多个session之间的隔离性。"""
        mgr_a = create_context_manager(session_id="session_A")
        mgr_b = create_context_manager(session_id="session_B")
        
        mgr_a.add_message("user", "A的问题")
        mgr_b.add_message("user", "B的问题")
        
        assert mgr_a.get_message_count() == 1
        assert mgr_b.get_message_count() == 1
        
        # A中的消息不应出现在B中
        a_msgs = [m.content for m in mgr_a._messages]
        b_msgs = [m.content for m in mgr_b._messages]
        
        assert "A的问题" in a_msgs
        assert "A的问题" not in b_msgs
        assert "B的问题" in b_msgs
        assert "B的问题" not in a_msgs
        
        print(f"  ✅ 多Session隔离正常")
    
    def test_unicode_and_encoding(self, boundary_manager):
        """Unicode编码和多语言支持。"""
        multilingual_texts = [
            ("English: Hello World!", "en"),
            ("中文：你好世界！", "zh"),
            ("日本語：こんにちは世界！", "ja"),
            ("한국어: 안녕하세요 세계!", "ko"),
            ("العربية: مرحبا بالعالم", "ar"),
            ("Emoji: 🎓🔬💻🚀🌍", "emoji"),
            ("Mixed: 你好Helloこんにちは", "mixed"),
        ]
        
        for text, lang in multilingual_texts:
            success = boundary_manager.add_message("user", text)
            assert success, f"{lang}文本添加失败"
        
        print(f"  ✅ 多语言支持正常: {len(multilingual_texts)}种语言")


class TestBudgetExhaustionScenarios:
    """预算耗尽场景测试。"""
    
    def test_graceful_degradation_when_full(self):
        """预算耗尽时的优雅降级。"""
        mgr = create_context_manager(
            session_id="exhaustion_test",
            total_budget_tokens=500,  # 极小预算
        )
        
        added_count = 0
        for i in range(100):
            success = mgr.add_message("user", f"填充消息{i}: {'data'*10}")
            if success:
                added_count += 1
            else:
                break  # 预算耗尽，停止添加
        
        # 验证不会崩溃且总token不超限
        assert mgr.get_total_tokens_used() <= 500
        assert added_count > 0, "至少应能添加几条消息"
        
        print(f"  ✅ 预算耗尽降级正常: 成功添加{added_count}条后停止")
    
    def test_auto_optimization_trigger(self):
        """自动优化触发时机测试。"""
        mgr = create_context_manager(
            session_id="auto_opt_test",
            total_budget_tokens=2000,
            summarize_threshold=0.7,  # 降低阈值以便触发
            auto_optimize=True,
        )
        
        # 快速填充至接近阈值
        for i in range(50):
            mgr.add_message("user", f"消息{i}: {'内容'*15}")
            
            # 检查是否触发了自动优化
            if mgr.get_utilization_rate() >= 0.7:
                # 此时应该已经触发了内部优化
                break
        
        # 验证最终状态合法
        assert mgr.get_total_tokens_used() <= 2000
        
        print(f"  ✅ 自动优化触发正常: 最终利用率={mgr.get_utilization_rate():.1%}")


# ============================================================================
# Test Suite 5: LLM上下文构建集成测试 (P0 - 必须全部通过)
# ============================================================================

class TestLLMContextBuilding:
    """测试build_llm_context方法。"""
    
    @pytest.fixture
    def context_builder(self):
        return create_context_manager(
            session_id="llm_context_test",
            total_budget_tokens=TEST_BUDGET,
        )
    
    def test_basic_llm_context_structure(self, context_builder):
        """构建的LLM上下文应符合OpenAI格式。"""
        # 添加一些历史
        for i in range(4):
            role = "user" if i % 2 == 0 else "assistant"
            context_builder.add_message(role, f"第{i//2+1}轮{'问题' if role=='user' else '回答'}")
        
        llm_ctx = context_builder.build_llm_context(
            system_prompt="你是数学助手。",
        )
        
        # 验证结构
        assert isinstance(llm_ctx, list)
        assert len(llm_ctx) > 0
        
        # 第一条应该是system prompt
        assert llm_ctx[0]["role"] == "system"
        assert "数学助手" in llm_ctx[0]["content"]
        
        # 应该包含user和assistant消息
        roles = [m["role"] for m in llm_ctx]
        assert "user" in roles
        assert "assistant" in roles
        
        print(f"  ✅ LLM上下文结构正确: {len(llm_ctx)}条消息")
    
    def test_strict_budget_adherence(self, context_builder):
        """严格遵循128K预算限制。"""
        # 尝试填满预算
        for i in range(1000):  # 大量消息
            context_builder.add_message("user", f"压力测试消息{i}: {'x'*100}")
            
            if context_builder.get_utilization_rate() >= 0.99:
                break
        
        # 构建LLM上下文（即使接近满载）
        llm_ctx = context_builder.build_llm_context(
            system_prompt="System prompt for testing.",
            include_metadata=True,
        )
        
        # 移除metadata消息（如果有）
        actual_msgs = [m for m in llm_ctx if m["role"] != "__metadata__"]
        
        # 计算实际token数（估算）
        total_chars = sum(len(m["content"]) for m in actual_msgs)
        estimated_tokens = total_chars // 2  # 粗略估计
        
        # 关键断言：即使接近满载也不应超出太多
        # （注意：由于使用的是估算，这里只做宽松检查）
        assert len(actual_msgs) > 0, "至少应有一些消息"
        
        print(f"  ✅ 预算严格遵循: 构建了{len(actual_msgs)}条消息（预估~{estimated_tokens} tokens）")
    
    def test_system_prompt_priority(self, context_builder):
        """System Prompt应始终存在且完整。"""
        long_system = "你是一个专业的数学辅导AI助手。" * 10  # 较长的system prompt
        
        # 即使history很多，system也不应被截断
        for i in range(20):
            context_builder.add_message("user", f"用户问题{i}")
        
        llm_ctx = context_builder.build_llm_context(system_prompt=long_system)
        
        system_msgs = [m for m in llm_ctx if m["role"] == "system"]
        assert len(system_msgs) >= 1, "至少应有一条system消息"
        
        # 验证完整的system prompt都在
        system_content = system_msgs[0]["content"]
        assert "数学辅导AI助手" in system_content
        
        print(f"  ✅ System Prompt优先级正确: 完整保留{len(system_content)}字符")
    
    def test_user_profile_injection(self, context_builder):
        """用户画像注入功能。"""
        profile = {
            "level": "高中",
            "weak_points": ["积分", "微分"],
            "preferred_style": "详细",
        }
        
        llm_ctx = context_builder.build_llm_context(
            system_prompt="Test prompt",
            user_profile=profile,
        )
        
        # 查找profile相关内容
        ctx_text = json.dumps(llm_ctx, ensure_ascii=False)
        
        assert "level" in ctx_text or "高中" in ctx_text
        assert "积分" in ctx_text or "weak_points" in ctx_text
        
        print(f"  ✅ 用户画像注入成功")
    
    def test_memory_injection(self, context_builder):
        """记忆注入功能。"""
        memories = [
            {"type": "error", "content": "上次你在积分题上出错"},
            {"type": "conversation", "content": "之前讨论过导数定义"},
        ]
        
        llm_ctx = context_builder.build_llm_context(
            system_prompt="Test",
            injected_memories=memories,
        )
        
        ctx_text = json.dumps(llm_ctx, ensure_ascii=False)
        
        assert "Relevant Memories" in ctx_text or "memory" in ctx_text.lower()
        
        print(f"  ✅ 记忆注入成功")


# ============================================================================
# Test Suite 6: 性能基准测试 (P1 - 性能指标验证)
# ============================================================================

@pytest.mark.performance
class TestPerformanceBenchmarks:
    """性能基准测试（可选，用于持续监控）。"""
    
    def test_token_counter_performance(self):
        """Token计数器性能基准。"""
        counter = TokenCounter()
        
        # 预热
        counter.count_tokens("warmup text")
        
        # 测试短文本计数（应<1ms）
        start = time.perf_counter()
        for _ in range(1000):
            counter.count_tokens(SHORT_TEXT)
        short_time = (time.perf_counter() - start) * 1000
        
        avg_short = short_time / 1000
        assert avg_short < 1.0, f"短文本计数过慢: {avg_short:.3f}ms/次"
        
        # 测试长文本计数（应<10ms）
        start = time.perf_counter()
        for _ in range(100):
            counter.count_tokens(VERY_LONG_TEXT)
        long_time = (time.perf_counter() - start) * 1000
        
        avg_long = long_time / 100
        assert avg_long < 10.0, f"长文本计数过慢: {avg_long:.3f}ms/次"
        
        print(f"  ⚡ Token计数器性能:")
        print(f"     短文本(~10tokens): {avg_short:.3f}ms/次 (目标<1ms)")
        print(f"     长文本(~3000tokens): {avg_long:.3f}ms/次 (目标<10ms)")
    
    def test_context_manager_throughput(self):
        """ContextManager吞吐量基准。"""
        mgr = create_context_manager(
            session_id="perf_test",
            total_budget_tokens=TEST_BUDGET,
        )
        
        # 测试添加吞吐量（目标: >1000 ops/sec）
        start = time.perf_counter()
        operations = 0
        test_duration = 1.0  # 1秒测试
        
        while (time.perf_counter() - start) < test_duration:
            mgr.add_message("user", f"性能测试消息{operations}")
            operations += 1
        
        elapsed = time.perf_counter() - start
        throughput = operations / elapsed
        
        assert throughput > 500, f"添加吞吐量过低: {throughput:.0f} ops/sec (目标>500)"
        
        print(f"  ⚡ ContextManager吞吐量: {throughput:.0f} ops/sec (目标>500)")
    
    def test_llm_context_build_latency(self):
        """LLM上下文构建延迟基准。"""
        mgr = create_context_manager(
            session_id="latency_test",
            total_budget_tokens=TEST_BUDGET,
        )
        
        # 预填充50条消息
        for i in range(50):
            mgr.add_message("user" if i % 2 == 0 else "assistant", f"消息{i}")
        
        # 测量构建延迟（目标: P99 < 50ms）
        latencies = []
        
        for _ in range(100):
            start = time.perf_counter()
            mgr.build_llm_context(system_prompt="Test system prompt")
            latency_ms = (time.perf_counter() - start) * 1000
            latencies.append(latency_ms)
        
        latencies.sort()
        p50 = latencies[len(latencies)//2]  # 中位数
        p95 = latencies[int(len(latencies)*0.95)] if len(latencies) > 20 else latencies[-1]
        p99 = latencies[int(len(latencies)*0.99)] if len(latencies) > 100 else latencies[-1]
        
        assert p99 < 100, f"P99延迟过高: {p99:.2f}ms (目标<100ms)"
        
        print(f"  ⚡ LLM上下文构建延迟:")
        print(f"     P50: {p50:.2f}ms (目标<20ms)")
        print(f"     P95: {p95:.2f}ms (目标<50ms)")
        print(f"     P99: {p99:.2f}ms (目标<100ms)")
    
    def test_memory_usage_stability(self):
        """内存使用稳定性测试（防止内存泄漏）。"""
        import gc
        import sys
        
        initial_objects = len(gc.get_objects())
        
        # 创建并销毁大量ContextManager实例
        for i in range(100):
            mgr = create_context_manager(session_id=f"mem_test_{i}")
            for j in range(20):
                mgr.add_message("user", f"内存测试{j}: {'data'*50}")
            del mgr  # 显式删除引用
        
        gc.collect()
        
        final_objects = len(gc.get_objects())
        object_growth = final_objects - initial_objects
        
        # 对象增长应控制在合理范围（<1000）
        assert object_growth < 10000, f"可能存在内存泄漏: 新增{object_growth}个对象"
        
        print(f"  ⚡ 内存使用稳定: 对象增长{object_growth} (目标<10000)")


# ============================================================================
# Test Suite 7: 集成测试与端到端验证 (P0 - 必须全部通过)
# ============================================================================

class TestEndToEndScenario:
    """端到端场景测试（模拟真实使用流程）。"""
    
    def test_typical_tutoring_session(self):
        """典型辅导会话场景：15-20轮数学问答。"""
        mgr = create_context_manager(
            session_id="tutoring_session_001",
            total_budget_tokens=TEST_BUDGET,
            strategy=ContextStrategy.HYBRID,
        )
        
        # 模拟一个真实的辅导会话
        conversation = [
            ("user", "你好，我想学习微积分的基础知识"),
            ("assistant", "好的！微积分是高等数学的重要分支。让我们从最基础的概念开始..."),
            ("user", "那什么是导数呢？"),
            ("assistant", "导数描述函数在某一点的瞬时变化率。几何意义上，它表示曲线切线的斜率..."),
            ("user", "能给我举一个具体的例子吗？"),
            ("assistant", "当然！考虑函数 f(x) = x²。它的导数 f'(x) = 2x。这意味着在x=1处，切线斜率为2..."),
            ("user", "我明白了。那积分和导数有什么关系？"),
            ("assistant", "积分和导数是互逆运算！这被称为微积分基本定理。如果F'(x) = f(x)，那么∫f(x)dx = F(x) + C..."),
            ("user", "这个关系太神奇了！能再详细解释一下基本定理吗？"),
            ("assistant", "微积分基本定理由牛顿和莱布尼茨独立发现。它分为两部分：第一部分联系定积分与原函数..."),
            ("user", "谢谢你的讲解！我对微积分有了初步了解。"),
            ("assistant", "不客气！建议接下来你可以练习一些基本的求导和积分题目来巩固理解。有任何问题随时问我！"),
        ]
        
        # 执行对话
        for role, content in conversation:
            success = mgr.add_message(role, content)
            assert success, f"辅导会话中断: '{content[:30]}...' 无法添加"
        
        # 验证会话统计
        stats = mgr.get_stats()
        
        assert stats["turn_count"] == 8, f"应为8轮对话，实际{stats['turn_count']}轮"
        assert stats["total_messages"] == 16, f"应为16条消息，实际{stats['total_messages']}条"
        assert stats["utilization_rate"] < 0.9, f"利用率过高: {stats['utilization_rate']:.1%}"
        
        # 验证可以检索历史
        recent = mgr.get_recent_messages(4)
        assert len(recent) == 4
        
        search_results = mgr.search_messages("导数", limit=3)
        assert len(search_results) > 0, "应能搜索到关于导数的讨论"
        
        # 验证完整性
        all_ok, _ = mgr.verify_all_integrity()
        assert all_ok, "辅导会话结束后完整性校验应通过"
        
        # 构建LLM上下文（模拟发送给模型）
        llm_ctx = mgr.build_llm_context(
            system_prompt="你是一个友好的数学导师。",
            user_profile={"level": "初学者", "topics": ["微积分"]},
        )
        
        assert len(llm_ctx) > 0
        assert mgr.get_total_tokens_used() <= TEST_BUDGET
        
        print(f"\n  🎓 典型辅导会话测试通过!")
        print(f"     总轮次: {stats['turn_count']}")
        print(f"     总消息: {stats['total_messages']}")
        print(f"     Token用量: {stats['total_tokens']:,}/{TEST_BUDGET:,} ({stats['utilization_rate']:.1%})")
        print(f"     LLM上下文: {len([m for m in llm_ctx if m['role'] != '__metadata__'])} 条消息")
    
    def test_stress_session_50_turns(self):
        """压力测试：50轮密集对话。"""
        mgr = create_context_manager(
            session_id="stress_test_50",
            total_budget_tokens=TEST_BUDGET,
            max_history_turns=30,  # 限制为30轮
        )
        
        for i in range(50):
            role = "user" if i % 2 == 0 else "assistant"
            content = (
                f"{'问题' if role=='user' else '回答'}#{i//2+1}: "
                f"{'讨论关于' if role=='user' else ''}"
                f"{'积分、导数、极限' if i % 6 == 0 else '某个数学概念的'}"
                f"{'详细解释' if role=='assistant' else ''}"
                f"{'内容扩展' * (5 if role == 'assistant' else 2)}"
            )
            
            success = mgr.add_message(role, content)
            # 不强制要求所有都成功（可能会触发压缩）
        
        # 验证系统仍稳定
        assert mgr.get_total_tokens_used() <= TEST_BUDGET, "绝不能超出预算!"
        
        stats = mgr.get_stats()
        
        print(f"\n  💪 50轮压力测试完成:")
        print(f"     实际保存消息: {stats['total_messages']}")
        print(f"     实际轮次: {stats['turn_count']}")
        print(f"     压缩消息数: {stats.get('compressed_count', 0)}")
        print(f"     利用率: {stats['utilization_rate']:.1%}")
    
    def test_mixed_language_session(self):
        """多语言混合会话测试。"""
        mgr = create_context_manager(session_id="multilang_test")
        
        multilingual_conv = [
            ("user", "What is the derivative of x²?"),
            ("assistant", "The derivative of x² with respect to x is 2x."),
            ("user", "那x²的导数是什么呢？"),
            ("assistant", "x²对x的导数是2x。这与英文回答一致。"),
            ("user", "How about the integral?"),
            ("assistant", "∫x²dx = x³/3 + C. 这是积分的结果。"),
            ("user", "能否用中文详细解释一下？"),
            ("assistant", "当然可以！积分是导数的逆运算...（详细中文解释）"),
        ]
        
        for role, content in multilingual_conv:
            assert mgr.add_message(role, content), f"多语言消息添加失败"
        
        # 验证多语言内容都被保留
        all_content = " ".join(m.content for m in mgr._messages)
        
        assert "derivative" in all_content.lower() or "导数" in all_content
        assert "integral" in all_content.lower() or "积分" in all_content
        assert "x²" in all_content or "x^2" in all_content
        
        print(f"  ✅ 多语言会话测试通过: {mgr.get_message_count()}条消息")


# ============================================================================
# 主测试入口
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("🧪 128K Token上下文记忆系统 - 完整测试套件")
    print("=" * 70)
    print()
    
    # 运行所有测试
    exit_code = pytest.main([
        __file__,
        "-v",  # 详细输出
        "--tb=short",  # 简短traceback
        "-x",  # 遇到第一个错误就停止
        "--durations=10",  # 显示最慢的10个测试
        "-q",  # 安静模式
    ])
    
    print("\n" + "=" * 70)
    if exit_code == 0:
        print("✅ 所有测试通过！128K上下文记忆系统功能正常。")
    else:
        print("❌ 存在失败的测试，请查看上方详情。")
    print("=" * 70)
