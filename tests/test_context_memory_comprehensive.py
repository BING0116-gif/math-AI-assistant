"""
上下文记忆功能全面测试套件 — 专项验证记忆准确性、跨话题关联、长期稳定性

测试目标：
1. 连续多轮对话中系统对历史对话信息的记忆准确性
2. 跨话题讨论时上下文信息的关联与调用能力
3. 长时间对话场景下上下文信息的保持稳定性

运行方式:
    python tests/test_context_memory_comprehensive.py

生成时间: 2026-05-18
作者: AI Testing Team
"""

# 强制使用UTF-8编码以支持emoji输出（Windows兼容）
import sys
import io
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import time
import json
import os
import hashlib
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

# 添加项目根目录到sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent_core.context_manager import (
    SmartContextManager,
    TokenCounter,
    ContextBudget,
    ContextStrategy,
    CompressionPriority,
    ContextMessage,
    create_context_manager,
)


# ============================================================================
# 数据模型
# ============================================================================

@dataclass
class TestCaseResult:
    """单个测试用例的结果。"""
    test_id: str
    test_name: str
    passed: bool
    score: float  # 0.0 - 1.0
    details: str
    execution_time_ms: float
    artifacts: Dict[str, Any] = None


@dataclass 
class TestSuiteResult:
    """测试套件结果。"""
    suite_name: str
    total_tests: int
    passed_tests: int
    failed_tests: int
    total_score: float
    results: List[TestCaseResult]
    execution_time_seconds: float


# ============================================================================
# 工具函数
# ============================================================================

def generate_math_conversation(topic: str, turns: int = 10) -> List[Tuple[str, str]]:
    """
    生成模拟的数学辅导对话。
    
    Args:
        topic: 数学主题（如"积分"、"导数"、"极限"）
        turns: 对话轮数
        
    Returns:
        [(role, content), ...] 对话列表
    """
    conversations = {
        "积分": [
            ("user", f"你好，我想学习{topic}的基础知识"),
            ("assistant", f"好的！{topic}是微积分的核心概念之一。让我们从定义开始..."),
            ("user", f"那什么是定{topic}呢？"),
            ("assistant", f"定{topic}表示函数在某区间上的累积量。几何意义上是曲线下的面积..."),
            ("user", f"能给我举一个具体的例子吗？比如求∫x²dx"),
            ("assistant", f"当然！∫x²dx = x³/3 + C。这是幂函数的{topic}公式..."),
            ("user", f"我明白了。那{topic}和导数有什么关系？"),
            ("assistant", f"{topic}和导数是互逆运算！这被称为微积分基本定理..."),
            ("user", f"这个关系太神奇了！能详细解释一下牛顿-莱布尼茨公式吗？"),
            ("assistant", f"牛顿-莱布尼茨公式：∫[a,b]f(x)dx = F(b) - F(a)，其中F是f的原函数..."),
            ("user", f"谢谢！我对{topic}有了初步了解，想练习一些题目"),
            ("assistant", f"很好！建议从基本的多项式{topic}开始练习，有任何问题随时问我！"),
        ],
        "导数": [
            ("user", f"我想了解{topic}的概念"),
            ("assistant", f"{topic}描述函数在某一点的瞬时变化率。几何意义是切线斜率..."),
            ("user", f"那如何求f(x) = x³的{topic}呢？"),
            ("assistant", f"使用幂函数求导法则：f'(x) = 3x²。每一步都要应用链式法则..."),
            ("user", f"{topic}在实际生活中有什么应用？"),
            ("assistant", f"{topic}广泛应用于物理（速度、加速度）、经济学（边际成本）等领域..."),
            ("user", f"能解释一下复合函数求导的链式法则吗？"),
            ("assistant", f"链式法则：若y=f(g(x))，则dy/dx = f'(g(x)) · g'(x)..."),
            ("user", f"我理解了。那高阶{topic}是什么意思？"),
            ("assistant", f"高阶{topic}是对{topic}再求导。f''(x)表示二阶{topic}，描述变化率的变化率..."),
            ("user", f"感谢讲解！我想多做些练习"),
            ("assistant", f"建议从基本初等函数的{topic}开始，逐步过渡到复合函数！"),
        ],
        "极限": [
            ("user", f"请帮我理解{topic}的概念"),
            ("assistant", f"{topic}描述当自变量趋近某值时，函数值趋近的目标..."),
            ("user", f"如何求lim(x→0) sin(x)/x？"),
            ("assistant", f"这是重要极限之一，答案是1。可以用夹逼定理或洛必达法则证明..."),
            ("user", f"什么是洛必达法则？"),
            ("assistant", f"当lim f(x)/g(x) 是0/0或∞/∞型时，可转化为lim f'(x)/g'(x)..."),
            ("user", f"{topic}和连续性有什么关系？"),
            ("assistant", f"函数在一点连续的充要条件是：该点的{topic}值等于函数值..."),
            ("user", f"能举例说明无穷{topic}吗？"),
            ("assistant", f"例如lim(x→∞) 1/x = 0，当x无限增大时，1/x趋近于0..."),
            ("user", f"我懂了。数列{topic}又是什么？"),
            ("assistant", f"数列{topic}研究当n趋近无穷时，数列aₙ的行为..."),
            ("user", f"谢谢！我会多加练习"),
            ("assistant", f"很好！{topic}是微积分的基础，务必掌握牢固！"),
        ],
    }
    
    base_conversation = conversations.get(topic, conversations["积分"])
    
    # 根据需要的轮数截取或扩展
    if turns <= len(base_conversation):
        return base_conversation[:turns * 2]  # 每轮2条消息
    
    # 如果需要更多轮次，循环扩展
    extended = list(base_conversation)
    while len(extended) < turns * 2:
        # 添加一些变体问题
        extra_turn = len(extended) // 2 + 1
        extended.extend([
            ("user", f"关于{topic}的第{extra_turn}个深入问题：能否举个更复杂的例子？"),
            (f"assistant", f"当然可以！让我们看一个综合性的{topic}应用案例（第{extra_turn}轮详细解释）..." + 
             "这是一个很长的解释性回答，包含多个步骤和详细的推导过程。" * 3),
        ])
    
    return extended[:turns * 2]


def measure_memory_usage() -> Dict[str, int]:
    """测量当前进程的内存使用情况。"""
    import psutil
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    return {
        "rss_mb": mem_info.rss / (1024 * 1024),  # 物理内存 MB
        "vms_mb": mem_info.vms / (1024 * 1024),  # 虚拟内存 MB
    }


# ============================================================================
# Test Suite 1: 连续多轮对话记忆准确性测试
# ============================================================================

class TestContinuousConversationMemory:
    """
    测试场景1：连续多轮对话中的记忆准确性。
    
    验证要点：
    1. 历史消息完整性：所有添加的消息都能被检索到
    2. 内容准确性：消息内容未被篡改或损坏
    3. 时间顺序：消息按正确的时间顺序排列
    4. Token计数准确性：预算控制精确无误
    5. 引用能力：能够准确引用早期对话的内容
    """
    
    def __init__(self):
        self.results: List[TestCaseResult] = []
        self.start_time = time.time()
    
    def run_all_tests(self) -> TestSuiteResult:
        """执行所有连续对话记忆测试。"""
        print("\n" + "="*70)
        print("📝 Test Suite 1: 连续多轮对话记忆准确性测试")
        print("="*70)
        
        self.test_basic_message_integrity()
        self.test_content_preservation_across_20_turns()
        self.test_token_counting_accuracy()
        self.test_temporal_ordering()
        self.test_early_conversation_recall()
        self.test_message_metadata_persistence()
        
        elapsed = time.time() - self.start_time
        passed = sum(1 for r in self.results if r.passed)
        total_score = sum(r.score for r in self.results) / len(self.results) if self.results else 0
        
        return TestSuiteResult(
            suite_name="连续多轮对话记忆准确性",
            total_tests=len(self.results),
            passed_tests=passed,
            failed_tests=len(self.results) - passed,
            total_score=total_score,
            results=self.results,
            execution_time_seconds=elapsed,
        )
    
    def test_basic_message_integrity(self):
        """测试1.1: 基本消息完整性验证。"""
        test_id = "T1.1"
        test_name = "基本消息完整性验证"
        start = time.time()
        
        try:
            mgr = create_context_manager(
                session_id="integrity_test",
                total_budget_tokens=128000,
            )
            
            # 添加10轮对话
            conversation = generate_math_conversation("积分", turns=10)
            added_messages = []
            
            for role, content in conversation:
                success = mgr.add_message(role, content)
                assert success, f"消息添加失败: {content[:30]}"
                added_messages.append((role, content))
            
            # 验证所有消息都存在
            assert mgr.get_message_count() == len(added_messages), \
                f"消息数量不匹配: 期望{len(added_messages)}, 实际{mgr.get_message_count()}"
            
            # 验证每条消息的内容完整性
            all_msgs = mgr._messages
            for i, (expected_role, expected_content) in enumerate(added_messages):
                actual_msg = all_msgs[i]
                assert actual_msg.role == expected_role, \
                    f"第{i+1}条消息角色不匹配: 期望{expected_role}, 实际{actual_msg.role}"
                assert actual_msg.content == expected_content, \
                    f"第{i+1}条消息内容不匹配"
                assert actual_msg.content_hash != "", \
                    f"第{i+1}条消息hash为空"
                assert actual_msg.verify_integrity(), \
                    f"第{i+1}条消息完整性校验失败"
            
            # 完整性批量验证
            all_ok, failed_ids = mgr.verify_all_integrity()
            assert all_ok and len(failed_ids) == 0, \
                f"批量完整性校验失败: {len(failed_ids)}条异常"
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=True,
                score=1.0,
                details=f"✅ 所有{len(added_messages)}条消息完整保留，内容准确，hash校验通过",
                execution_time_ms=elapsed_ms,
                artifacts={"message_count": len(added_messages)},
            ))
            print(f"  [{test_id}] {test_name}: ✅ PASS ({elapsed_ms:.1f}ms)")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")
    
    def test_content_preservation_across_20_turns(self):
        """测试1.2: 20轮长对话的内容保持性。"""
        test_id = "T1.2"
        test_name = "20轮长对话内容保持性"
        start = time.time()
        
        try:
            mgr = create_context_manager(
                session_id="long_conv_test",
                total_budget_tokens=128000,
                strategy=ContextStrategy.HYBRID,
                max_history_turns=25,
            )
            
            # 生成并添加20轮对话
            conversation = generate_math_conversation("导数", turns=20)
            original_contents = []
            
            for role, content in conversation:
                success = mgr.add_message(role, content)
                if success:
                    original_contents.append((role, content))
            
            # 验证关键信息点未被丢失
            all_content = " ".join(m.content for m in mgr._messages)
            
            # 检查关键术语是否仍然存在
            key_terms = ["导数", "瞬时变化率", "切线斜率", "链式法则", "幂函数"]
            preserved_terms = []
            lost_terms = []
            
            for term in key_terms:
                if term in all_content:
                    preserved_terms.append(term)
                else:
                    lost_terms.append(term)
            
            # 计算保持率
            preservation_rate = len(preserved_terms) / len(key_terms)
            
            # 验证首尾消息的准确性
            first_msg = mgr._messages[0] if mgr._messages else None
            last_msg = mgr._messages[-1] if mgr._messages else None
            
            assert first_msg is not None, "第一条消息丢失"
            assert last_msg is not None, "最后一条消息丢失"
            assert first_msg.content == original_contents[0][1], "首消息内容被篡改"
            
            score = preservation_rate
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=preservation_rate >= 0.8,  # 80%以上关键词保留视为通过
                score=score,
                details=(
                    f"{'✅' if preservation_rate >= 0.8 else '⚠️'} "
                    f"20轮对话完成, {len(original_contents)}条消息保留, "
                    f"关键词保持率: {preservation_rate:.1%} "
                    f"({len(preserved_terms)}/{len(key_terms)}), "
                    f"丢失: {lost_terms}"
                ),
                execution_time_ms=elapsed_ms,
                artifacts={
                    "total_messages": len(original_contents),
                    "preserved_terms": preserved_terms,
                    "lost_terms": lost_terms,
                    "preservation_rate": preservation_rate,
                },
            ))
            status = "✅ PASS" if preservation_rate >= 0.8 else "⚠️ PARTIAL"
            print(f"  [{test_id}] {test_name}: {status} ({elapsed_ms:.1f}ms) - 保持率{preservation_rate:.1%}")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")
    
    def test_token_counting_accuracy(self):
        """测试1.3: Token计数准确性验证。"""
        test_id = "T1.3"
        test_name = "Token计数准确性验证"
        start = time.time()
        
        try:
            mgr = create_context_manager(session_id="token_accuracy_test")
            counter = TokenCounter()
            
            # 添加各种类型的文本
            test_texts = [
                ("短文本", "求积分"),
                ("中文长文本", "这是一个关于微积分基本定理的长问题描述，包含多个数学符号如∫∑∏√∂∇"),
                ("英文文本", "Calculate the derivative of f(x) = x³ + 2x² - 5x + 1"),
                ("混合文本", "Mixed: 求极限 lim(x→0) sin(x)/x = ? Answer: 1"),
                ("特殊字符", "Formula: $$\\int_{0}^{\\infty} e^{-x^2} dx = \\frac{\\sqrt{\\pi}}{2}$$"),
            ]
            
            counting_errors = []
            
            for text_name, text in test_texts:
                # 使用独立计数器计算期望token数
                expected_tokens = counter.count_tokens(text)
                
                # 添加到manager
                success = mgr.add_message("user", text)
                assert success, f"添加失败: {text_name}"
                
                # 获取实际存储的token数
                actual_msg = mgr._messages[-1]
                actual_tokens = actual_msg.token_count
                
                # 计算误差（允许±10%误差）
                error_rate = abs(expected_tokens - actual_tokens) / max(expected_tokens, 1)
                
                if error_rate > 0.15:  # 15%误差阈值
                    counting_errors.append({
                        "text_type": text_name,
                        "expected": expected_tokens,
                        "actual": actual_tokens,
                        "error_rate": error_rate,
                    })
            
            # 验证总计数的合理性
            total_calculated = sum(m.token_count for m in mgr._messages)
            total_reported = mgr.get_total_tokens_used()
            
            total_error = abs(total_calculated - total_reported) / max(total_calculated, 1)
            
            # 计算得分
            error_count = len(counting_errors)
            score = max(0, 1.0 - error_count * 0.2 - total_error)
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=error_count == 0 and total_error < 0.1,
                score=score,
                details=(
                    f"{'✅' if error_count == 0 else '⚠️'} "
                    f"测试了{len(test_texts)}种文本类型, "
                    f"计数误差: {error_count}处, "
                    f"总计数误差: {total_error:.2%}"
                ),
                execution_time_ms=elapsed_ms,
                artifacts={
                    "tested_types": len(test_texts),
                    "counting_errors": counting_errors,
                    "total_error_rate": total_error,
                },
            ))
            status = "✅ PASS" if (error_count == 0 and total_error < 0.1) else "⚠️ PARTIAL"
            print(f"  [{test_id}] {test_name}: {status} ({elapsed_ms:.1f}ms) - 误差{error_count}处")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")
    
    def test_temporal_ordering(self):
        """测试1.4: 时间顺序正确性验证。"""
        test_id = "T1.4"
        test_name = "时间顺序正确性验证"
        start = time.time()
        
        try:
            mgr = create_context_manager(session_id="ordering_test")
            
            # 快速连续添加消息（间隔很短）
            timestamps = []
            for i in range(15):
                start_add = time.time()
                mgr.add_message("user" if i % 2 == 0 else "assistant", f"消息{i}")
                end_add = time.time()
                timestamps.append((i, end_add))
                
                # 故意添加小延迟确保时间戳不同
                time.sleep(0.001)
            
            # 验证时间戳单调递增
            messages = mgr._messages
            ordering_correct = True
            violations = []
            
            for i in range(len(messages) - 1):
                if messages[i].timestamp > messages[i+1].timestamp:
                    ordering_correct = False
                    violations.append(i)
            
            # 验证消息顺序与添加顺序一致
            order_matches = all(
                f"消息{i}" in messages[i].content 
                for i in range(len(messages))
            )
            
            score = 1.0 if (ordering_correct and order_matches) else 0.5
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=ordering_correct and order_matches,
                score=score,
                details=(
                    f"{'✅' if ordering_correct and order_matches else '⚠️'} "
                    f"时间顺序{'正确' if ordering_correct else f'异常(违规点: {violations})'}, "
                    f"消息顺序{'匹配' if order_matches else '不匹配'}"
                ),
                execution_time_ms=elapsed_ms,
                artifacts={
                    "total_messages": len(messages),
                    "ordering_violations": len(violations),
                    "order_matches": order_matches,
                },
            ))
            status = "✅ PASS" if (ordering_correct and order_matches) else "❌ FAIL"
            print(f"  [{test_id}] {test_name}: {status} ({elapsed_ms:.1f}ms)")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")
    
    def test_early_conversation_recall(self):
        """测试1.5: 早期对话内容的可召回性。"""
        test_id = "T1.5"
        test_name = "早期对话内容可召回性"
        start = time.time()
        
        try:
            mgr = create_context_manager(
                session_id="recall_test",
                total_budget_tokens=128000,
            )
            
            # 构建一个有明确知识点的对话
            key_facts = [
                ("user", "我想学习积分的基础知识"),
                ("assistant", "积分是微积分的核心概念，分为不定积分和定积分"),
                ("user", "不定积分和定积分有什么区别？"),
                ("assistant", "不定积分求原函数族（+C），定积分求数值（牛顿-莱布尼茨公式）"),
                ("user", "牛顿-莱布尼茨公式的具体内容是什么？"),
                ("assistant", "∫[a,b]f(x)dx = F(b) - F(a)，连接了积分与导数"),
                ("user", "这个公式太重要了！请记住这个知识点"),
                ("assistant", "已记住！这是微积分基本定理的核心公式"),
            ]
            
            for role, content in key_facts:
                mgr.add_message(role, content)
            
            # 再添加一些后续对话（可能触发压缩）
            for i in range(10):
                mgr.add_message("user" if i % 2 == 0 else "assistant", 
                              f"后续讨论{i}: 关于其他数学主题的内容")
            
            # 尝试搜索早期的关键知识点
            recall_tests = [
                ("牛顿-莱布尼茨公式", "应找到包含此公式的消息"),
                ("不定积分和定积分的区别", "应找到对比说明"),
                ("微积分基本定理", "应找到相关讨论"),
            ]
            
            successful_recalls = 0
            recall_details = []
            
            for query, expectation in recall_tests:
                results = mgr.search_messages(query, limit=3)
                if len(results) > 0:
                    successful_recalls += 1
                    recall_details.append(f"✅ '{query}': 找到{len(results)}条")
                else:
                    recall_details.append(f"❌ '{query}': 未找到")
            
            recall_rate = successful_recalls / len(recall_tests)
            
            # 验证即使被压缩，原始内容仍可通过恢复获得
            compressed_msgs = [m for m in mgr._messages if m.is_compressed]
            can_restore = True
            for msg in compressed_msgs[:3]:  # 测试前3个压缩消息
                original = msg.original_content
                if original:
                    msg.restore_from_compression()
                    if msg.content != original:
                        can_restore = False
                        break
            
            score = recall_rate * (0.8 if can_restore else 0.6)
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=recall_rate >= 0.67,  # 至少2/3能召回
                score=score,
                details=(
                    f"{'✅' if recall_rate >= 0.67 else '⚠️'} "
                    f"召回率: {recall_rate:.1%} ({successful_recalls}/{len(recall_tests)}), "
                    f"压缩消息恢复: {'正常' if can_restore else '异常'}"
                ),
                execution_time_ms=elapsed_ms,
                artifacts={
                    "recall_tests": len(recall_tests),
                    "successful_recalls": successful_recalls,
                    "recall_details": recall_details,
                    "compressed_count": len(compressed_msgs),
                    "can_restore": can_restore,
                },
            ))
            status = "✅ PASS" if recall_rate >= 0.67 else "⚠️ PARTIAL"
            print(f"  [{test_id}] {test_name}: {status} ({elapsed_ms:.1f}ms) - 召回率{recall_rate:.1%}")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")
    
    def test_message_metadata_persistence(self):
        """测试1.6: 消息元数据持久化验证。"""
        test_id = "T1.6"
        test_name = "消息元数据持久化"
        start = time.time()
        
        try:
            mgr = create_context_manager(session_id="metadata_test")
            
            # 添加带丰富元数据的消息
            test_metadata = [
                {"topic": "积分", "difficulty": "hard", "user_level": "beginner"},
                {"source": "follow_up_question", "previous_msg_id": "msg_001"},
                {"tags": ["important", "exam_related"], "priority": "high"},
                {"session_phase": "practice", "attempt_number": 3},
            ]
            
            metadata_preserved = []
            
            for i, meta in enumerate(test_metadata):
                mgr.add_message(
                    "user",
                    f"带元数据的消息{i}",
                    metadata=meta,
                )
                
                # 立即验证元数据是否保存
                saved_msg = mgr._messages[-1]
                match_count = sum(
                    1 for k, v in meta.items() 
                    if k in saved_msg.metadata and saved_msg.metadata[k] == v
                )
                preservation_rate = match_count / len(meta) if meta else 1.0
                metadata_preserved.append(preservation_rate)
            
            # 经过一些操作后再次验证
            for i in range(5):
                mgr.add_message("assistant", f"填充消息{i}")
            
            # 再次检查元数据
            final_preservation = []
            for i, meta in enumerate(test_metadata):
                if i < len(mgr._messages):
                    saved_msg = mgr._messages[i]
                    match_count = sum(
                        1 for k, v in meta.items() 
                        if k in saved_msg.metadata and saved_msg.metadata[k] == v
                    )
                    final_preservation.append(match_count / len(meta) if meta else 1.0)
            
            avg_preservation = sum(final_preservation) / len(final_preservation) if final_preservation else 0
            score = avg_preservation
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=avg_preservation >= 0.9,
                score=score,
                details=(
                    f"{'✅' if avg_preservation >= 0.9 else '⚠️'} "
                    f"元数据平均保持率: {avg_preservation:.1%}, "
                    f"测试了{len(test_metadata)}组元数据"
                ),
                execution_time_ms=elapsed_ms,
                artifacts={
                    "metadata_groups": len(test_metadata),
                    "initial_preservation": metadata_preserved,
                    "final_preservation": final_preservation,
                    "avg_preservation": avg_preservation,
                },
            ))
            status = "✅ PASS" if avg_preservation >= 0.9 else "⚠️ PARTIAL"
            print(f"  [{test_id}] {test_name}: {status} ({elapsed_ms:.1f}ms) - 保持率{avg_preservation:.1%}")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")


# ============================================================================
# Test Suite 2: 跨话题讨论上下文关联能力测试
# ============================================================================

class TestCrossTopicContextAssociation:
    """
    测试场景2：跨话题讨论时的上下文关联能力。
    
    验证要点：
    1. 话题切换时的记忆保持
    2. 跨话题知识点的关联搜索
    3. 重要性评分的合理性
    4. 上下文重建时的信息完整性
    """
    
    def __init__(self):
        self.results: List[TestCaseResult] = []
        self.start_time = time.time()
    
    def run_all_tests(self) -> TestSuiteResult:
        """执行所有跨话题关联测试。"""
        print("\n" + "="*70)
        print("🔗 Test Suite 2: 跨话题讨论上下文关联能力测试")
        print("="*70)
        
        self.test_topic_switching_memory()
        self.test_cross_topic_knowledge_association()
        self.test_importance_scoring_rationality()
        self.test_context_reconstruction_quality()
        self.test_mixed_topic_search_precision()
        
        elapsed = time.time() - self.start_time
        passed = sum(1 for r in self.results if r.passed)
        total_score = sum(r.score for r in self.results) / len(self.results) if self.results else 0
        
        return TestSuiteResult(
            suite_name="跨话题讨论上下文关联能力",
            total_tests=len(self.results),
            passed_tests=passed,
            failed_tests=len(self.results) - passed,
            total_score=total_score,
            results=self.results,
            execution_time_seconds=elapsed,
        )
    
    def test_topic_switching_memory(self):
        """测试2.1: 话题切换时的记忆保持能力。"""
        test_id = "T2.1"
        test_name = "话题切换时的记忆保持"
        start = time.time()
        
        try:
            mgr = create_context_manager(
                session_id="topic_switch_test",
                total_budget_tokens=128000,
                strategy=ContextStrategy.IMPORTANCE_WEIGHTED,
                importance_scoring_enabled=True,
            )
            
            # 模拟话题切换：积分 → 导数 → 极限 → 回到积分
            topics_sequence = ["积分", "导数", "极限", "积分"]
            topic_markers = {}  # 记录每个话题的关键信息位置
            
            for topic_idx, topic in enumerate(topics_sequence):
                conversation = generate_math_conversation(topic, turns=5)
                
                for role, content in conversation:
                    # 标记每个话题的第一条和最后一条用户消息
                    if role == "user":
                        if topic not in topic_markers:
                            topic_markers[topic] = {
                                "first_msg_idx": mgr.get_message_count(),
                                "first_content_preview": content[:50],
                            }
                        topic_markers[topic]["last_msg_idx"] = mgr.get_message_count()
                        topic_markers[topic]["last_content_preview"] = content[:50]
                    
                    mgr.add_message(role, content)
            
            # 验证第一个话题（积分）的信息仍可检索
            integral_topic = topic_markers.get("积分")
            assert integral_topic is not None, "积分话题标记缺失"
            
            # 搜索第一个话题的关键词
            search_results = mgr.search_messages("积分", limit=5)
            found_integral = len(search_results) > 0
            
            # 搜索第二个话题（导数）
            derivative_results = mgr.search_messages("导数", limit=5)
            found_derivative = len(derivative_results) > 0
            
            # 搜索第三个话题（极限）
            limit_results = mgr.search_messages("极限", limit=5)
            found_limit = len(limit_results) > 0
            
            # 计算综合得分
            topics_found = sum([found_integral, found_derivative, found_limit])
            retention_rate = topics_found / 3
            
            # 验证话题切换后回到原话题时，旧信息仍可用
            cross_reference_possible = (
                found_integral and 
                "积分" in " ".join(m.content for m in mgr._messages[-10:])  # 最近的消息中
            )
            
            score = retention_rate * (1.2 if cross_reference_possible else 0.8)
            score = min(1.0, max(0.0, score))
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=retention_rate >= 0.67,
                score=score,
                details=(
                    f"{'✅' if retention_rate >= 0.67 else '⚠️'} "
                    f"话题序列: {' → '.join(topics_sequence)}, "
                    f"话题保持: 积分={'✅' if found_integral else '❌'} "
                    f"导数={'✅' if found_derivative else '❌'} "
                    f"极限={'✅' if found_limit else '❌'}, "
                    f"跨话题引用: {'可用' if cross_reference_possible else '受限'}"
                ),
                execution_time_ms=elapsed_ms,
                artifacts={
                    "topics_sequence": topics_sequence,
                    "topics_found": {
                        "积分": found_integral,
                        "导数": found_derivative,
                        "极限": found_limit,
                    },
                    "retention_rate": retention_rate,
                    "cross_reference": cross_reference_possible,
                },
            ))
            status = "✅ PASS" if retention_rate >= 0.67 else "⚠️ PARTIAL"
            print(f"  [{test_id}] {test_name}: {status} ({elapsed_ms:.1f}ms) - 保持率{retention_rate:.1%}")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")
    
    def test_cross_topic_knowledge_association(self):
        """测试2.2: 跨话题知识点关联搜索能力。"""
        test_id = "T2.2"
        test_name = "跨话题知识点关联搜索"
        start = time.time()
        
        try:
            mgr = create_context_manager(
                session_id="association_test",
                total_budget_tokens=128000,
            )
            
            # 构建跨话题的知识网络
            knowledge_network = [
                # 话题1: 积分基础
                ("user", "积分的基本概念是什么？"),
                ("assistant", "积分是微积分的两大支柱之一，分为不定积分和定积分。不定积分求原函数，定积分求面积。"),
                
                # 话题2: 导数（与积分相关联）
                ("user", "导数和积分有什么关系？"),
                ("assistant", "它们互为逆运算！这就是著名的微积分基本定理。导数求变化率，积分求累积量。"),
                
                # 话题3: 具体例子（同时涉及两个概念）
                ("user", "举个例子说明这种关系"),
                ("assistant", "例如：f(x) = x² 的导数是 f'(x) = 2x；而 ∫2xdx = x² + C。完美体现互逆关系！"),
                
                # 话题4: 应用（综合运用）
                ("user", "这在实际问题中怎么用？"),
                ("assistant", "物理中：速度的导数是加速度，速度的积分是位移。经济学中：边际成本的积分是总成本。"),
            ]
            
            for role, content in knowledge_network:
                mgr.add_message(role, content)
            
            # 测试跨话题关联查询
            association_queries = [
                {
                    "query": "微积分基本定理",
                    "expected_topics": ["积分", "导数"],
                    "reason": "应同时找到积分和导数相关的讨论",
                },
                {
                    "query": "互逆运算",
                    "expected_topics": ["导数", "积分"],
                    "reason": "应找到两者关系的说明",
                },
                {
                    "query": "x²",
                    "expected_topics": ["具体例子"],
                    "reason": "应找到包含此例子的消息",
                },
            ]
            
            successful_associations = 0
            association_details = []
            
            for query_info in association_queries:
                query = query_info["query"]
                results = mgr.search_messages(query, limit=5)
                
                # 检查结果是否涵盖预期的多个话题
                result_topics = set()
                for msg, score in results:
                    if "积分" in msg.content:
                        result_topics.add("积分")
                    if "导数" in msg.content:
                        result_topics.add("导数")
                    if "例子" in msg.content or "x²" in msg.content:
                        result_topics.add("具体例子")
                
                coverage = len(result_topics & set(query_info["expected_topics"]))
                is_success = coverage >= 1  # 至少找到一个预期话题
                
                if is_success:
                    successful_associations += 1
                    association_details.append(f"✅ '{query}': 找到{len(results)}条, 覆盖{coverage}个话题")
                else:
                    association_details.append(f"⚠️ '{query}': 找到{len(results)}条, 但话题覆盖不足")
            
            association_rate = successful_associations / len(association_queries)
            score = association_rate
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=association_rate >= 0.67,
                score=score,
                details=(
                    f"{'✅' if association_rate >= 0.67 else '⚠️'} "
                    f"关联查询成功率: {association_rate:.1%} ({successful_associations}/{len(association_queries)})"
                ),
                execution_time_ms=elapsed_ms,
                artifacts={
                    "queries_tested": len(association_queries),
                    "successful_associations": successful_associations,
                    "association_details": association_details,
                },
            ))
            status = "✅ PASS" if association_rate >= 0.67 else "⚠️ PARTIAL"
            print(f"  [{test_id}] {test_name}: {status} ({elapsed_ms:.1f}ms) - 成功率{association_rate:.1%}")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")
    
    def test_importance_scoring_rationality(self):
        """测试2.3: 重要性评分的合理性。"""
        test_id = "T2.3"
        test_name = "重要性评分合理性"
        start = time.time()
        
        try:
            mgr = create_context_manager(
                session_id="importance_test",
                importance_scoring_enabled=True,
            )
            
            # 添加不同重要性的消息
            test_messages = [
                ("user", "普通问题：今天天气怎么样？", CompressionPriority.LOW),
                ("assistant", "普通回答：天气不错，适合学习。", CompressionPriority.LOW),
                ("user", "重要反馈：你之前的解答有错误！", CompressionPriority.CRITICAL),
                ("assistant", "错误修正：感谢指正，正确答案应该是...", CompressionPriority.HIGH),
                ("user", "重点标记：请记住这个公式 ∫x²dx = x³/3 + C", CompressionPriority.HIGH),
                ("tool", "工具输出：计算结果是42", CompressionPriority.NORMAL),
                ("user", "一般性问题：还有其他方法吗？", CompressionPriority.NORMAL),
                ("assistant", "常规回答：是的，还可以用换元法...", CompressionPriority.NORMAL),
            ]
            
            scores_by_priority = {
                "CRITICAL": [],
                "HIGH": [],
                "NORMAL": [],
                "LOW": [],
            }
            
            for role, content, priority in test_messages:
                mgr.add_message(role, content, priority=priority)
                msg = mgr._messages[-1]
                scores_by_priority[priority.value].append(msg.importance_score)
            
            # 验证评分顺序：CRITICAL > HIGH > NORMAL > LOW
            avg_scores = {
                p: sum(scores) / len(scores) if scores else 0
                for p, scores in scores_by_priority.items()
            }
            
            scoring_order_correct = (
                avg_scores["CRITICAL"] > avg_scores["HIGH"] > 
                avg_scores["NORMAL"] > avg_scores["LOW"]
            )
            
            # 验证CRITICAL消息确实得到高分
            critical_min = min(scores_by_priority["CRITICAL"]) if scores_by_priority["CRITICAL"] else 0
            low_max = max(scores_by_priority["LOW"]) if scores_by_priority["LOW"] else 1
            
            separation_clear = critical_min > low_max
            
            # 综合评分
            score = 0.7 if scoring_order_correct else 0.3
            if separation_clear:
                score += 0.3
            score = min(1.0, score)
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=scoring_order_correct or separation_clear,
                score=score,
                details=(
                    f"{'✅' if (scoring_order_correct and separation_clear) else '⚠️'} "
                    f"平均评分: CRITICAL={avg_scores['CRITICAL']:.3f}, "
                    f"HIGH={avg_scores['HIGH']:.3f}, "
                    f"NORMAL={avg_scores['NORMAL']:.3f}, "
                    f"LOW={avg_scores['LOW']:.3f}, "
                    f"排序{'正确' if scoring_order_correct else '异常'}, "
                    f"分离度{'清晰' if separation_clear else '不足'}"
                ),
                execution_time_ms=elapsed_ms,
                artifacts={
                    "scores_by_priority": {
                        k: [round(s, 3) for s in v] 
                        for k, v in scores_by_priority.items()
                    },
                    "average_scores": {k: round(v, 3) for k, v in avg_scores.items()},
                    "order_correct": scoring_order_correct,
                    "separation_clear": separation_clear,
                },
            ))
            status = "✅ PASS" if (scoring_order_correct and separation_clear) else "⚠️ PARTIAL"
            print(f"  [{test_id}] {test_name}: {status} ({elapsed_ms:.1f}ms)")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")
    
    def test_context_reconstruction_quality(self):
        """测试2.4: LLM上下文重建质量。"""
        test_id = "T2.4"
        test_name = "LLM上下文重建质量"
        start = time.time()
        
        try:
            mgr = create_context_manager(
                session_id="reconstruction_test",
                total_budget_tokens=128000,
            )
            
            # 添加多话题混合对话
            mixed_conversation = []
            topics = ["积分", "导数", "极限"]
            
            for round_idx in range(6):
                topic = topics[round_idx % len(topics)]
                conv = generate_math_conversation(topic, turns=2)
                for role, content in conv:
                    mgr.add_message(role, content)
                    mixed_conversation.append((role, content, topic))
            
            # 构建LLM上下文
            system_prompt = "你是数学助手，需要记住所有讨论过的知识点。"
            llm_ctx = mgr.build_llm_context(
                system_prompt=system_prompt,
                user_profile={"level": "intermediate"},
            )
            
            # 验证重建质量
            ctx_text = json.dumps(llm_ctx, ensure_ascii=False)
            
            # 检查各话题的关键信息是否都包含在内
            topic_coverage = {}
            for topic in topics:
                # 为每个话题选择代表性关键词
                keywords = {
                    "积分": ["积分", "原函数", "面积"],
                    "导数": ["导数", "变化率", "斜率"],
                    "极限": ["极限", "趋近", "收敛"],
                }
                found_keywords = sum(
                    1 for kw in keywords[topic] 
                    if kw in ctx_text
                )
                coverage_rate = found_keywords / len(keywords[topic])
                topic_coverage[topic] = coverage_rate
            
            # 验证system prompt完整性
            has_system_prompt = any(
                m.get("role") == "system" and "数学助手" in m.get("content", "")
                for m in llm_ctx
            )
            
            # 验证结构合法性
            valid_structure = all(
                m.get("role") in ("system", "user", "assistant", "tool") 
                for m in llm_ctx 
                if isinstance(m, dict)
            )
            
            # 综合评分
            avg_coverage = sum(topic_coverage.values()) / len(topic_coverage)
            structure_valid = has_system_prompt and valid_structure
            score = avg_coverage * (1.0 if structure_valid else 0.7)
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=avg_coverage >= 0.6 and structure_valid,
                score=score,
                details=(
                    f"{'✅' if (avg_coverage >= 0.6 and structure_valid) else '⚠️'} "
                    f"话题覆盖率: {', '.join([f'{k}:{v:.1%}' for k,v in topic_coverage.items()])}, "
                    f"System Prompt: {'✅' if has_system_prompt else '❌'}, "
                    f"结构有效性: {'✅' if valid_structure else '❌'}"
                ),
                execution_time_ms=elapsed_ms,
                artifacts={
                    "topic_coverage": topic_coverage,
                    "average_coverage": avg_coverage,
                    "has_system_prompt": has_system_prompt,
                    "valid_structure": valid_structure,
                    "llm_context_length": len(llm_ctx),
                },
            ))
            status = "✅ PASS" if (avg_coverage >= 0.6 and structure_valid) else "⚠️ PARTIAL"
            print(f"  [{test_id}] {test_name}: {status} ({elapsed_ms:.1f}ms) - 平均覆盖率{avg_coverage:.1%}")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")
    
    def test_mixed_topic_search_precision(self):
        """测试2.5: 混合话题环境下的搜索精度。"""
        test_id = "T2.5"
        test_name = "混合话题搜索精度"
        start = time.time()
        
        try:
            mgr = create_context_manager(
                session_id="precision_test",
                total_budget_tokens=128000,
            )
            
            # 创建混淆性测试数据
            # 包含相似但不完全相同的关键词
            confusing_data = [
                ("user", "我想学习不定积分", {"topic": "积分"}),
                ("assistant", "不定积分是求原函数的操作", {"topic": "积分"}),
                ("user", "那定积分呢？", {"topic": "积分"}),
                ("assistant", "定积分计算曲线下的面积", {"topic": "积分"}),
                ("user", "导数的定义是什么？", {"topic": "导数"}),
                ("assistant", "导数是函数瞬时变化率的度量", {"topic": "导数"}),
                ("user", "偏导数和多元函数的关系？", {"topic": "导数"}),
                ("assistant", "偏导数是多元函数对某一变量的导数", {"topic": "导数"}),
                ("user", "数列极限怎么求？", {"topic": "极限"}),
                ("assistant", "数列极限考察n→∞时的行为", {"topic": "极限"}),
                ("user", "函数极限和数列极限的区别", {"topic": "极限"}),
                ("assistant", "函数极限是连续变量，数列极限是离散的", {"topic": "极限"}),
            ]
            
            for role, content, meta in confusing_data:
                mgr.add_message(role, content, metadata=meta)
            
            # 测试精确搜索
            precision_tests = [
                {
                    "query": "不定积分",
                    "should_find": ["不定积分", "原函数"],
                    "should_not_find": ["定积分", "面积"],
                    "description": "精确匹配'不定积分'",
                },
                {
                    "query": "导数",
                    "should_find": ["变化率", "偏导数"],
                    "should_not_find": ["积分", "原函数"],
                    "description": "搜索'导数'应找到相关但排除无关",
                },
                {
                    "query": "极限",
                    "should_find": ["数列极限", "n→∞"],
                    "should_not_find": ["积分", "导数"],
                    "description": "搜索'极限'应聚焦极限话题",
                },
            ]
            
            precision_results = []
            
            for test in precision_tests:
                results = mgr.search_messages(test["query"], limit=5)
                
                found_contents = [msg.content for msg, _ in results]
                
                # 检查应该找到的内容
                should_found_count = sum(
                    1 for term in test["should_find"]
                    if any(term in content for content in found_contents)
                )
                
                # 检查不应该出现的内容
                should_not_found_leakage = sum(
                    1 for term in test["should_not_find"]
                    if any(term in content for content in found_contents)
                )
                
                precision = (
                    should_found_count / len(test["should_find"]) -
                    should_not_found_leakage * 0.3  # 泄漏惩罚
                )
                precision = max(0, min(1, precision))
                
                precision_results.append({
                    "test": test["description"],
                    "precision": precision,
                    "found_count": should_found_count,
                    "leakage": should_not_found_leakage,
                })
            
            avg_precision = sum(p["precision"] for p in precision_results) / len(precision_results)
            all_pass = all(p["precision"] >= 0.5 for p in precision_results)
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=all_pass,
                score=avg_precision,
                details=(
                    f"{'✅' if all_pass else '⚠️'} "
                    f"平均精度: {avg_precision:.1%}, "
                    f"测试数: {len(precision_tests)}"
                ),
                execution_time_ms=elapsed_ms,
                artifacts={
                    "precision_tests": precision_results,
                    "average_precision": avg_precision,
                },
            ))
            status = "✅ PASS" if all_pass else "⚠️ PARTIAL"
            print(f"  [{test_id}] {test_name}: {status} ({elapsed_ms:.1f}ms) - 平均精度{avg_precision:.1%}")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")


# ============================================================================
# Test Suite 3: 长时间对话稳定性测试
# ============================================================================

class TestLongTermStability:
    """
    测试场景3：长时间对话场景下的稳定性。
    
    验证要点：
    1. 内存使用稳定性（无泄漏）
    2. 超长对话（50-100轮）的系统鲁棒性
    3. 压缩策略的有效性和数据保持平衡
    4. 极端条件下的性能表现
    """
    
    def __init__(self):
        self.results: List[TestCaseResult] = []
        self.start_time = time.time()
    
    def run_all_tests(self) -> TestSuiteResult:
        """执行所有长期稳定性测试。"""
        print("\n" + "="*70)
        print("⏱️ Test Suite 3: 长时间对话稳定性测试")
        print("="*70)
        
        self.test_memory_stability_under_load()
        self.test_ultra_long_conversation_resilience()
        self.test_compression_strategy_effectiveness()
        self.test_extreme_condition_performance()
        self.test_resource_cleanup_and_gc()
        
        elapsed = time.time() - self.start_time
        passed = sum(1 for r in self.results if r.passed)
        total_score = sum(r.score for r in self.results) / len(self.results) if self.results else 0
        
        return TestSuiteResult(
            suite_name="长时间对话稳定性",
            total_tests=len(self.results),
            passed_tests=passed,
            failed_tests=len(self.results) - passed,
            total_score=total_score,
            results=self.results,
            execution_time_seconds=elapsed,
        )
    
    def test_memory_stability_under_load(self):
        """测试3.1: 高负载下的内存稳定性。"""
        test_id = "T3.1"
        test_name = "高负载下内存稳定性"
        start = time.time()
        
        try:
            import gc
            import tracemalloc
            
            # 开始跟踪内存分配
            tracemalloc.start()
            
            initial_snapshot = tracemalloc.take_snapshot()
            initial_mem = measure_memory_usage()
            
            # 创建管理器并进行大量操作
            managers = []
            operations_per_manager = 200
            
            for mgr_idx in range(5):  # 5个独立会话
                mgr = create_context_manager(
                    session_id=f"load_test_{mgr_idx}",
                    total_budget_tokens=128000,
                )
                managers.append(mgr)
                
                for op_idx in range(operations_per_manager):
                    role = "user" if op_idx % 2 == 0 else "assistant"
                    content = (
                        f"操作#{op_idx}: "
                        f"{'这是一个关于高等数学的问题，涉及复杂的公式推导和理论分析。' * 3}"
                    )
                    mgr.add_message(role, content)
                    
                    # 每50次操作强制GC
                    if op_idx % 50 == 0:
                        gc.collect()
            
            # 强制垃圾回收
            gc.collect()
            time.sleep(0.1)  # 等待异步清理完成
            
            final_snapshot = tracemalloc.take_snapshot()
            final_mem = measure_memory_usage()
            
            # 计算内存增长
            rss_growth_mb = final_mem["rss_mb"] - initial_mem["rss_mb"]
            vms_growth_mb = final_mem["vms_mb"] - initial_mem["vms_mb"]
            
            # 分析内存快照差异
            stats = final_snapshot.compare_to(initial_snapshot, 'lineno')
            top_stat = stats[0] if stats else None
            top_allocation = top_stat.size / 1024 if top_stat else 0  # KB
            
            # 判断内存是否稳定（RSS增长<50MB视为稳定）
            memory_stable = rss_growth_mb < 50
            
            # 清理资源
            managers.clear()
            gc.collect()
            tracemalloc.stop()
            
            score = 1.0 if rss_growth_mb < 20 else (0.7 if rss_growth_mb < 50 else 0.3)
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=memory_stable,
                score=score,
                details=(
                    f"{'✅' if memory_stable else '⚠️'} "
                    f"RSS增长: {rss_growth_mb:.1f}MB, VMS增长: {vms_growth_mb:.1f}MB, "
                    f"最大分配点: {top_allocation:.1f}KB, "
                    f"测试规模: {len(managers)}会话 × {operations_per_manager}操作"
                ),
                execution_time_ms=elapsed_ms,
                artifacts={
                    "initial_rss_mb": initial_mem["rss_mb"],
                    "final_rss_mb": final_mem["rss_mb"],
                    "rss_growth_mb": rss_growth_mb,
                    "vms_growth_mb": vms_growth_mb,
                    "managers_tested": len(managers),
                    "ops_per_manager": operations_per_manager,
                    "top_allocation_kb": top_allocation,
                },
            ))
            status = "✅ PASS" if memory_stable else "⚠️ WARNING"
            print(f"  [{test_id}] {test_name}: {status} ({elapsed_ms:.1f}ms) - RSS+{rss_growth_mb:.1f}MB")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")
    
    def test_ultra_long_conversation_resilience(self):
        """测试3.2: 超长对话（70轮）的鲁棒性。"""
        test_id = "T3.2"
        test_name = "超长对话鲁棒性（70轮）"
        start = time.time()
        
        try:
            mgr = create_context_manager(
                session_id="ultra_long_test",
                total_budget_tokens=128000,
                strategy=ContextStrategy.HYBRID,
                auto_optimize=True,
                summarize_threshold=0.75,
            )
            
            errors_encountered = []
            turn_details = []
            
            # 模拟70轮对话
            for turn in range(70):
                topic = ["积分", "导数", "极限"][turn % 3]
                
                try:
                    # 用户消息
                    user_content = (
                        f"[轮{turn+1}] 用户问关于{topic}的问题: "
                        f"{'这是一个需要详细解答的复杂问题。' * (2 if turn % 5 == 0 else 1)}"
                    )
                    user_success = mgr.add_message("user", user_content)
                    
                    # AI回复（交替长短）
                    assistant_content = (
                        f"[轮{turn+1}] AI回答关于{topic}的问题: "
                        f"{'详细解答如下...' + '这是完整的推导过程。' * 5 if turn % 3 == 0 else '简短回答。'}"
                    )
                    ai_success = mgr.add_message("assistant", assistant_content)
                    
                    turn_details.append({
                        "turn": turn + 1,
                        "user_added": user_success,
                        "ai_added": ai_success,
                        "total_messages": mgr.get_message_count(),
                        "utilization": mgr.get_utilization_rate(),
                    })
                    
                except Exception as turn_error:
                    errors_encountered.append({
                        "turn": turn + 1,
                        "error": str(turn_error),
                    })
            
            # 验证最终状态
            final_stats = mgr.get_stats()
            total_messages = final_stats["total_messages"]
            utilization = final_stats["utilization_rate"]
            compressed_count = final_stats.get("compressed_count", 0)
            
            # 关键断言：系统未崩溃且未超出预算
            no_crash = len(errors_encountered) == 0
            within_budget = utilization <= 1.0  # 允许达到100%
            still_functional = total_messages > 0
            
            # 即使部分消息因预算限制未能添加，只要系统稳定就算通过
            resilience_score = (
                (1.0 if no_crash else 0.3) *
                (1.0 if within_budget else 0.5) *
                (1.0 if still_functional else 0.0)
            )
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=no_crash and within_budget and still_functional,
                score=resilience_score,
                details=(
                    f"{'✅' if (no_crash and within_budget) else '⚠️'} "
                    f"完成{len(turn_details)}轮对话, "
                    f"最终消息数: {total_messages}, "
                    f"利用率: {utilization:.1%}, "
                    f"压缩消息: {compressed_count}, "
                    f"错误: {len(errors_encountered)}"
                ),
                execution_time_ms=elapsed_ms,
                artifacts={
                    "target_turns": 70,
                    "completed_turns": len(turn_details),
                    "final_total_messages": total_messages,
                    "final_utilization": utilization,
                    "compressed_count": compressed_count,
                    "errors": errors_encountered[:5],  # 最多显示5个错误
                    "sample_turns": turn_details[-5:],  # 最后5轮详情
                },
            ))
            status = "✅ PASS" if (no_crash and within_budget) else "⚠️ DEGRADED"
            print(f"  [{test_id}] {test_name}: {status} ({elapsed_ms:.1f}ms) - {len(turn_details)}轮, 利用率{utilization:.1%}")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")
    
    def test_compression_strategy_effectiveness(self):
        """测试3.3: 压缩策略的有效性评估。"""
        test_id = "T3.3"
        test_name = "压缩策略有效性"
        start = time.time()
        
        try:
            # 测试不同的压缩策略
            strategies = [
                (ContextStrategy.SLIDING_WINDOW, "滑动窗口"),
                (ContextStrategy.IMPORTANCE_WEIGHTED, "重要性加权"),
                (ContextStrategy.SUMMARIZATION, "摘要压缩"),
                (ContextStrategy.HYBRID, "混合策略"),
            ]
            
            strategy_results = []
            
            for strategy, name in strategies:
                mgr = create_context_manager(
                    session_id=f"compression_{strategy.value}",
                    total_budget_tokens=5000,  # 小预算以快速触发压缩
                    strategy=strategy,
                    auto_optimize=True,
                )
                
                # 添加足够多的消息以触发压缩
                initial_count = 0
                for i in range(40):
                    success = mgr.add_message(
                        "user" if i % 2 == 0 else "assistant",
                        f"[{name}] 消息{i}: {'这是一段较长的内容用于测试压缩效果。' * 3}"
                    )
                    if success and i == 0:
                        initial_count = 1
                
                final_stats = mgr.get_stats()
                compressed_count = final_stats.get("compressed_count", 0)
                final_messages = final_stats["total_messages"]
                utilization = final_stats["utilization_rate"]
                
                # 对于滑动窗口和重要性加权，消息会被删除而非压缩
                # 对于摘要和混合策略，消息会被压缩
                if strategy in (ContextStrategy.SUMMARIZATION, ContextStrategy.HYBRID):
                    effectiveness = compressed_count / max(final_messages, 1)
                else:
                    # 其他策略通过删除来控制大小
                    effectiveness = 1.0 if utilization < 1.0 else 0.5
                
                strategy_results.append({
                    "name": name,
                    "strategy": strategy.value,
                    "final_messages": final_messages,
                    "compressed": compressed_count,
                    "utilization": utilization,
                    "effectiveness": effectiveness,
                })
            
            # 评估哪种策略最有效
            best_strategy = max(strategy_results, key=lambda x: x["effectiveness"])
            avg_effectiveness = sum(s["effectiveness"] for s in strategy_results) / len(strategy_results)
            
            # 所有策略都应该能控制住预算（利用率不超过1.0太多）
            all_controlled = all(s["utilization"] <= 1.05 for s in strategy_results)
            
            score = avg_effectiveness * (1.0 if all_controlled else 0.7)
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=all_controlled and avg_effectiveness >= 0.5,
                score=score,
                details=(
                    f"{'✅' if (all_controlled and avg_effectiveness >= 0.5) else '⚠️'} "
                    f"最佳策略: {best_strategy['name']}({best_strategy['effectiveness']:.1%}), "
                    f"平均有效性: {avg_effectiveness:.1%}, "
                    f"全部受控: {'是' if all_controlled else '否'}"
                ),
                execution_time_ms=elapsed_ms,
                artifacts={
                    "strategies_tested": len(strategy_results),
                    "strategy_details": strategy_results,
                    "best_strategy": best_strategy["name"],
                    "average_effectiveness": avg_effectiveness,
                    "all_controlled": all_controlled,
                },
            ))
            status = "✅ PASS" if (all_controlled and avg_effectiveness >= 0.5) else "⚠️ PARTIAL"
            print(f"  [{test_id}] {test_name}: {status} ({elapsed_ms:.1f}ms) - 最佳:{best_strategy['name']}")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")
    
    def test_extreme_condition_performance(self):
        """测试3.4: 极端条件下的性能表现。"""
        test_id = "T3.4"
        test_name = "极端条件性能表现"
        start = time.time()
        
        try:
            performance_metrics = {}
            
            # 测试1: 单条超长消息（~10000字符）
            mgr1 = create_context_manager(session_id="extreme_long_msg")
            ultra_long_msg = "这是一个超长的数学问题描述，" * 1000  # ~14000字符
            
            start_op = time.perf_counter()
            success1 = mgr1.add_message("user", ultra_long_msg)
            time_long_msg = (time.perf_counter() - start_op) * 1000
            
            performance_metrics["ultra_long_message"] = {
                "success": success1,
                "time_ms": time_long_msg,
                "length_chars": len(ultra_long_msg),
            }
            
            # 测试2: 高频连续操作
            mgr2 = create_context_manager(session_id="high_frequency")
            ops_count = 500
            
            start_op = time.perf_counter()
            for i in range(ops_count):
                mgr2.add_message("user", f"高频消息{i}")
            time_high_freq = (time.perf_counter() - start_op) * 1000
            
            throughput = ops_count / (time_high_freq / 1000)  # ops/sec
            
            performance_metrics["high_frequency"] = {
                "ops_count": ops_count,
                "total_time_ms": time_high_freq,
                "throughput_ops_sec": throughput,
            }
            
            # 测试3: 大量消息后的构建延迟
            mgr3 = create_context_manager(session_id="build_latency")
            for i in range(100):
                mgr3.add_message("user" if i % 2 == 0 else "assistant", f"消息{i}")
            
            latencies = []
            for _ in range(20):
                start_build = time.perf_counter()
                mgr3.build_llm_context(system_prompt="Test prompt")
                latency = (time.perf_counter() - start_build) * 1000
                latencies.append(latency)
            
            latencies.sort()
            p50 = latencies[len(latencies)//2]
            p95 = latencies[int(len(latencies)*0.95)] if len(latencies) > 20 else latencies[-1]
            p99 = latencies[int(len(latencies)*0.99)] if len(latencies) > 100 else latencies[-1]
            
            performance_metrics["build_latency"] = {
                "p50_ms": p50,
                "p95_ms": p95,
                "p99_ms": p99,
                "message_count": 100,
            }
            
            # 评估标准
            long_msg_ok = success1 and time_long_msg < 100  # <100ms
            high_freq_ok = throughput > 500  # >500 ops/sec
            build_latency_ok = p99 < 200  # P99 <200ms
            
            passed_count = sum([long_msg_ok, high_freq_ok, build_latency_ok])
            score = passed_count / 3
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=passed_count >= 2,  # 至少2/3通过
                score=score,
                details=(
                    f"{'✅' if passed_count >= 2 else '⚠️'} "
                    f"超长消息: {'✅' if long_msg_ok else '❌'}({time_long_msg:.1f}ms), "
                    f"高频吞吐: {'✅' if high_freq_ok else '❌'}({throughput:.0f}/s), "
                    f"构建P99: {'✅' if build_latency_ok else '❌'}({p99:.1f}ms)"
                ),
                execution_time_ms=elapsed_ms,
                artifacts={
                    "performance_metrics": performance_metrics,
                    "tests_passed": passed_count,
                    "tests_total": 3,
                },
            ))
            status = "✅ PASS" if passed_count >= 2 else "⚠️ DEGRADED"
            print(f"  [{test_id}] {test_name}: {status} ({elapsed_ms:.1f}ms) - 通过{passed_count}/3")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")
    
    def test_resource_cleanup_and_gc(self):
        """测试3.5: 资源清理和垃圾回收。"""
        test_id = "T3.5"
        test_name = "资源清理与垃圾回收"
        start = time.time()
        
        try:
            import gc
            
            # 记录初始对象数
            gc.collect()
            initial_objects = len(gc.get_objects())
            
            # 创建并销毁大量ContextManager
            managers_created = []
            for i in range(50):
                mgr = create_context_manager(
                    session_id=f"gc_test_{i}",
                    total_budget_tokens=128000,
                )
                
                # 添加一些消息
                for j in range(20):
                    mgr.add_message("user", f"GC测试消息{j}")
                
                managers_created.append(mgr)
            
            mid_objects = len(gc.get_objects())
            
            # 显式删除所有引用
            for mgr in managers_created:
                mgr.clear(preserve_critical=False)
            
            managers_created.clear()
            del managers_created
            
            # 强制垃圾回收
            gc.collect()
            time.sleep(0.1)
            
            final_objects = len(gc.get_objects())
            
            # 计算对象增长
            growth_after_creation = mid_objects - initial_objects
            growth_after_cleanup = final_objects - initial_objects
            
            # 判断是否有明显内存泄漏（对象增长应<5000）
            no_significant_leak = growth_after_cleanup < 5000
            cleanup_effective = growth_after_cleanup < growth_after_creation * 0.3  # 清理后应大幅减少
            
            score = 0.7 if cleanup_effective else (0.4 if no_significant_leak else 0.1)
            
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=no_significant_leak and cleanup_effective,
                score=score,
                details=(
                    f"{'✅' if (no_significant_leak and cleanup_effective) else '⚠️'} "
                    f"创建后对象: +{growth_after_creation:,}, "
                    f"清理后对象: +{growth_after_cleanup:,}, "
                    f"清理有效率: {(1 - growth_after_cleanup/max(growth_after_creation, 1)):.1%}"
                ),
                execution_time_ms=elapsed_ms,
                artifacts={
                    "initial_objects": initial_objects,
                    "mid_objects": mid_objects,
                    "final_objects": final_objects,
                    "growth_after_creation": growth_after_creation,
                    "growth_after_cleanup": growth_after_cleanup,
                    "managers_created": 50,
                    "msgs_per_manager": 20,
                },
            ))
            status = "✅ PASS" if (no_significant_leak and cleanup_effective) else "⚠️ WARNING"
            print(f"  [{test_id}] {test_name}: {status} ({elapsed_ms:.1f}ms) - 对象增长+{growth_after_cleanup:,}")
            
        except Exception as e:
            elapsed_ms = (time.time() - start) * 1000
            self.results.append(TestCaseResult(
                test_id=test_id,
                test_name=test_name,
                passed=False,
                score=0.0,
                details=f"❌ 测试失败: {str(e)}",
                execution_time_ms=elapsed_ms,
            ))
            print(f"  [{test_id}] {test_name}: ❌ FAIL ({elapsed_ms:.1f}ms) - {e}")


# ============================================================================
# 主测试执行器
# ============================================================================

class ComprehensiveTestRunner:
    """全面测试执行器。"""
    
    def __init__(self):
        self.all_suites: List[TestSuiteResult] = []
        self.start_time = time.time()
    
    def run_all_suites(self) -> Dict[str, Any]:
        """执行所有测试套件。"""
        print("\n" + "="*80)
        print("[TEST] 上下文记忆功能全面测试")
        print("="*80)
        print(f"\n[INFO] 测试范围:")
        print("   1. 连续多轮对话记忆准确性（6项测试）")
        print("   2. 跨话题讨论上下文关联能力（5项测试）")
        print("   3. 长时间对话稳定性（5项测试）")
        print(f"\n[TIME] 开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 运行各个测试套件
        suite1 = TestContinuousConversationMemory()
        result1 = suite1.run_all_tests()
        self.all_suites.append(result1)
        
        suite2 = TestCrossTopicContextAssociation()
        result2 = suite2.run_all_tests()
        self.all_suites.append(result2)
        
        suite3 = TestLongTermStability()
        result3 = suite3.run_all_tests()
        self.all_suites.append(result3)
        
        # 生成汇总报告
        report = self.generate_final_report()
        
        return report
    
    def generate_final_report(self) -> Dict[str, Any]:
        """生成最终的测试报告。"""
        total_elapsed = time.time() - self.start_time
        
        # 汇总统计
        total_tests = sum(s.total_tests for s in self.all_suites)
        total_passed = sum(s.passed_tests for s in self.all_suites)
        total_failed = sum(s.failed_tests for s in self.all_suites)
        overall_score = sum(s.total_score for s in self.all_suites) / len(self.all_suites)
        
        # 输出报告
        print("\n" + "="*80)
        print("[REPORT] 全面测试报告")
        print("="*80)

        print(f"\n[STATS] 总体统计:")
        print(f"   总测试数: {total_tests}")
        print(f"   [PASS] 通过: {total_passed} ({total_passed/total_tests*100:.1f}%)")
        print(f"   [FAIL] 失败: {total_failed} ({total_failed/total_tests*100:.1f}%)")
        print(f"   [SCORE] 总评分: {overall_score:.1%}")
        print(f"   [TIME] 总耗时: {total_elapsed:.1f}秒")

        print(f"\n[DETAIL] 各套件详情:")
        for suite in self.all_suites:
            status_icon = "[OK]" if suite.passed_tests == suite.total_tests else "[WARN]"
            print(f"   {status_icon} {suite.suite_name}:")
            print(f"      通过: {suite.passed_tests}/{suite.total_tests} "
                  f"({suite.passed_tests/suite.total_tests*100:.1f}%), "
                  f"评分: {suite.total_score:.1%}, "
                  f"耗时: {suite.execution_time_seconds:.1f}s")

        # 收集所有失败的测试
        failures = []
        for suite in self.all_suites:
            for result in suite.results:
                if not result.passed:
                    failures.append(result)

        if failures:
            print(f"\n[WARN] 失败测试详情 ({len(failures)}项):")
            for fail in failures:
                print(f"   [FAIL] [{fail.test_id}] {fail.test_name}")
                print(f"      得分: {fail.score:.1%} | 详情: {fail.details}")

        # 收集发现的问题和建议
        issues_and_recommendations = self.analyze_issues()

        if issues_and_recommendations:
            print(f"\n[ISSUE] 发现的问题与改进建议:")
            for issue in issues_and_recommendations:
                print(f"   - {issue}")

        print("\n" + "="*80)
        if overall_score >= 0.9:
            verdict = "[EXCELLENT] 优秀 - 上下文记忆功能完全正常"
        elif overall_score >= 0.7:
            verdict = "[GOOD] 良好 - 上下文记忆功能基本正常，有小幅改进空间"
        elif overall_score >= 0.5:
            verdict = "[PASS] 及格 - 存在一些问题需要关注和修复"
        else:
            verdict = "[FAIL] 不合格 - 发现严重缺陷，需要立即修复"
        
        print(f"[VERDICT] 最终评定: {verdict}")
        print("="*80)
        
        return {
            "summary": {
                "total_tests": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "pass_rate": total_passed / total_tests,
                "overall_score": overall_score,
                "execution_time_seconds": total_elapsed,
                "verdict": verdict,
            },
            "suites": [
                {
                    "name": s.suite_name,
                    "total": s.total_tests,
                    "passed": s.passed_tests,
                    "score": s.total_score,
                    "results": [
                        {
                            "id": r.test_id,
                            "name": r.test_name,
                            "passed": r.passed,
                            "score": r.score,
                            "details": r.details,
                        }
                        for r in s.results
                    ],
                }
                for s in self.all_suites
            ],
            "failures": [
                {
                    "id": f.test_id,
                    "name": f.test_name,
                    "details": f.details,
                    "score": f.score,
                }
                for f in failures
            ],
            "issues": issues_and_recommendations,
        }
    
    def analyze_issues(self) -> List[str]:
        """分析测试中发现的问题并提供改进建议。"""
        issues = []
        
        for suite in self.all_suites:
            for result in suite.results:
                if result.score < 0.7:  # 得分低于70%的测试
                    if "T1." in result.test_id:
                        if "保持" in result.test_name or "召回" in result.test_name:
                            issues.append(
                                f"[记忆准确性] {result.test_name}: {result.details[:80]}... "
                                f"建议：增加历史消息保护机制，提高关键信息的优先级"
                            )
                        elif "计数" in result.test_name:
                            issues.append(
                                f"[Token精度] {result.test_name}: {result.details[:80]}... "
                                f"建议：优化tokenizer配置，考虑使用更精确的编码器"
                            )
                    
                    elif "T2." in result.test_id:
                        if "切换" in result.test_name or "关联" in result.test_name:
                            issues.append(
                                f"[跨话题能力] {result.test_name}: {result.details[:80]}... "
                                f"建议：增强语义搜索引擎，引入向量嵌入提升关联质量"
                            )
                        elif "搜索" in result.test_name:
                            issues.append(
                                f"[搜索精度] {result.test_name}: {result.details[:80]}... "
                                f"建议：实现混合检索（关键词+语义），降低误报率"
                            )
                    
                    elif "T3." in result.test_id:
                        if "内存" in result.test_name or "泄漏" in result.test_name:
                            issues.append(
                                f"[资源管理] {result.test_name}: {result.details[:80]}... "
                                f"建议：检查循环引用，优化数据结构，增强GC友好性"
                            )
                        elif "压缩" in result.test_name:
                            issues.append(
                                f"[压缩策略] {result.test_name}: {result.details[:80]}... "
                                f"建议：调优摘要算法，平衡压缩率与信息保持率"
                            )
        
        # 去重
        seen = set()
        unique_issues = []
        for issue in issues:
            issue_key = issue.split("]")[0] if "]" in issue else issue[:50]
            if issue_key not in seen:
                seen.add(issue_key)
                unique_issues.append(issue)
        
        return unique_issues


# ============================================================================
# 入口点
# ============================================================================

if __name__ == "__main__":
    runner = ComprehensiveTestRunner()
    report = runner.run_all_suites()
    
    # 可选：保存报告到JSON文件
    output_file = "context_memory_test_report.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n[SAVE] 详细报告已保存至: {output_file}")
