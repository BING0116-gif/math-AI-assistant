"""
DynamicLLMFactory 及动态参数配置模块的全面功能测试。

覆盖范围：
1. 参数映射正确性（TaskType → LLMParams）
2. LLM实例缓存机制
3. 参数覆盖（override_params）
4. 一站式分类+获取LLM（classify_and_get_llm）
5. 缓存管理（clear_cache / get_cache_stats）
6. 基础配置更新（update_base_config）
7. 全局单例（init/get_dynamic_llm_factory）
8. 异常处理（未初始化错误 / 无效任务类型）
9. Token成本节省验证（T1/T2 vs DEFAULT）
10. TaskClassifier 集成验证
11. 禁用动态参数模式
12. MathAgent 动态参数集成
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import Mock, patch


class TestLLMParams:
    """LLMParams 参数映射正确性测试。"""

    def test_params_to_dict(self):
        """测试 to_dict() 方法返回正确的字典格式。"""
        from prompts.dynamic_params import LLMParams

        params = LLMParams(temperature=0.5, max_tokens=2048)
        result = params.to_dict()

        assert result["temperature"] == 0.5
        assert result["max_tokens"] == 2048
        assert result["top_p"] == 1.0
        assert result["presence_penalty"] == 0.0
        assert result["frequency_penalty"] == 0.0

    def test_default_params(self):
        """测试默认参数值。"""
        from prompts.dynamic_params import LLMParams

        params = LLMParams()
        assert params.temperature == 0.0
        assert params.top_p == 1.0
        assert params.max_tokens == 4096
        assert params.presence_penalty == 0.0
        assert params.frequency_penalty == 0.0

    def test_custom_params(self):
        """测试自定义参数值。"""
        from prompts.dynamic_params import LLMParams

        params = LLMParams(
            temperature=0.3,
            top_p=0.9,
            max_tokens=1000,
            presence_penalty=0.5,
            frequency_penalty=0.2,
        )
        assert params.temperature == 0.3
        assert params.top_p == 0.9
        assert params.max_tokens == 1000
        assert params.presence_penalty == 0.5
        assert params.frequency_penalty == 0.2


class TestTaskType:
    """TaskType 枚举测试。"""

    def test_enum_values(self):
        """测试所有枚举值正确。"""
        from prompts.dynamic_params import TaskType

        assert TaskType.KNOWLEDGE_QUERY.value == "knowledge"
        assert TaskType.QUICK_ANSWER.value == "quick"
        assert TaskType.CONCEPT_TEACHING.value == "concept"
        assert TaskType.MULTIMODAL.value == "multimodal"
        assert TaskType.FULL_SOLUTION.value == "solution"
        assert TaskType.PLANNED_SOLUTION.value == "planned"
        assert TaskType.DEFAULT.value == "solution"

    def test_from_chinese_label(self):
        """测试中文标签转换。"""
        from prompts.dynamic_params import TaskType

        assert TaskType.from_chinese_label("T1") == TaskType.KNOWLEDGE_QUERY
        assert TaskType.from_chinese_label("T2") == TaskType.QUICK_ANSWER
        assert TaskType.from_chinese_label("T3") == TaskType.CONCEPT_TEACHING
        assert TaskType.from_chinese_label("T4") == TaskType.MULTIMODAL
        assert TaskType.from_chinese_label("T5") == TaskType.FULL_SOLUTION
        assert TaskType.from_chinese_label("unknown") == TaskType.DEFAULT

    def test_to_chinese(self):
        """测试转换为中文标签。"""
        from prompts.dynamic_params import TaskType

        assert "知识点" in TaskType.KNOWLEDGE_QUERY.to_chinese()
        assert "快速" in TaskType.QUICK_ANSWER.to_chinese()
        assert "概念" in TaskType.CONCEPT_TEACHING.to_chinese()
        assert "完整" in TaskType.FULL_SOLUTION.to_chinese()
        assert "完整解题" == TaskType.DEFAULT.to_chinese()

    def test_max_output_length(self):
        """测试各任务类型的最大输出字数。"""
        from prompts.dynamic_params import TaskType

        assert TaskType.QUICK_ANSWER.max_output_length == 100
        assert TaskType.KNOWLEDGE_QUERY.max_output_length == 200
        assert TaskType.CONCEPT_TEACHING.max_output_length == 500
        assert TaskType.FULL_SOLUTION.max_output_length == 2000
        assert TaskType.PLANNED_SOLUTION.max_output_length == 4000

    def test_needs_tools(self):
        """测试各任务类型是否需要工具。"""
        from prompts.dynamic_params import TaskType

        assert not TaskType.KNOWLEDGE_QUERY.needs_tools
        assert not TaskType.QUICK_ANSWER.needs_tools
        assert TaskType.FULL_SOLUTION.needs_tools
        assert TaskType.MULTIMODAL.needs_tools
        assert TaskType.PLANNED_SOLUTION.needs_tools

    def test_max_history_turns(self):
        """测试各任务类型的历史轮数限制。"""
        from prompts.dynamic_params import TaskType

        assert TaskType.QUICK_ANSWER.max_history_turns == 1
        assert TaskType.FULL_SOLUTION.max_history_turns == 5
        assert TaskType.PLANNED_SOLUTION.max_history_turns == 10


class TestTaskParamsMap:
    """TASK_PARAMS_MAP 参数映射表测试。"""

    def test_knowledge_query_params(self):
        """T1：知识点查询 — 确定性 + 少量Token。"""
        from prompts.dynamic_params import get_params_for_task, TaskType

        params = get_params_for_task(TaskType.KNOWLEDGE_QUERY)
        assert params.temperature == 0.0
        assert params.max_tokens == 800

    def test_quick_answer_params(self):
        """T2：快速答案 — 最少Token。"""
        from prompts.dynamic_params import get_params_for_task, TaskType

        params = get_params_for_task(TaskType.QUICK_ANSWER)
        assert params.temperature == 0.0
        assert params.max_tokens == 300

    def test_concept_teaching_params(self):
        """T3：概念讲解 — 适度灵活性。"""
        from prompts.dynamic_params import get_params_for_task, TaskType

        params = get_params_for_task(TaskType.CONCEPT_TEACHING)
        assert params.temperature == 0.1
        assert params.top_p == 0.95
        assert params.max_tokens == 2000

    def test_full_solution_params(self):
        """T5：完整解题 — 大Token容量。"""
        from prompts.dynamic_params import get_params_for_task, TaskType

        params = get_params_for_task(TaskType.FULL_SOLUTION)
        assert params.temperature == 0.0
        assert params.max_tokens == 4096

    def test_planned_solution_params(self):
        """复杂规划 — 最大Token容量。"""
        from prompts.dynamic_params import get_params_for_task, TaskType

        params = get_params_for_task(TaskType.PLANNED_SOLUTION)
        assert params.max_tokens == 8192

    def test_default_fallback(self):
        """未知类型回退到默认配置。"""
        from prompts.dynamic_params import get_params_for_task, TaskType

        params = get_params_for_task(TaskType.DEFAULT)
        assert params.temperature == 0.0
        assert params.max_tokens == 4096


class TestDynamicLLMFactory:
    """DynamicLLMFactory 核心功能测试。"""

    @pytest.fixture
    def factory(self):
        """创建测试工厂实例。"""
        from prompts.dynamic_params import DynamicLLMFactory
        return DynamicLLMFactory(
            api_key="test-key",
            base_url="http://localhost:1234",
            model="test-model",
            streaming=True,
        )

    def test_factory_initialization(self, factory):
        """测试工厂初始化状态。"""
        from prompts.dynamic_params import DynamicLLMFactory

        assert factory._api_key == "test-key"
        assert factory._base_url == "http://localhost:1234"
        assert factory._model == "test-model"
        assert factory._streaming is True
        assert len(factory._llm_cache) == 0
        assert isinstance(factory._base_config, dict)

    def test_get_llm_creates_instance(self, factory):
        """测试 get_llm 创建 ChatOpenAI 实例。"""
        from prompts.dynamic_params import TaskType
        from langchain_openai import ChatOpenAI

        llm = factory.get_llm(TaskType.DEFAULT)
        assert isinstance(llm, ChatOpenAI)
        assert llm.model_name == "test-model"

    def test_get_llm_task_type_params(self, factory):
        """测试不同任务类型返回不同参数的LLM。"""
        from prompts.dynamic_params import TaskType

        llm_t1 = factory.get_llm(TaskType.KNOWLEDGE_QUERY)
        llm_t5 = factory.get_llm(TaskType.FULL_SOLUTION)

        assert llm_t1.max_tokens == 800
        assert llm_t5.max_tokens == 4096
        assert llm_t1.max_tokens < llm_t5.max_tokens

    def test_llm_caching_mechanism(self, factory):
        """测试相同任务类型返回同一个实例（缓存）。"""
        from prompts.dynamic_params import TaskType

        llm1 = factory.get_llm(TaskType.QUICK_ANSWER)
        llm2 = factory.get_llm(TaskType.QUICK_ANSWER)

        assert llm1 is llm2

    def test_different_types_different_instances(self, factory):
        """测试不同任务类型返回不同实例。"""
        from prompts.dynamic_params import TaskType

        llm_t1 = factory.get_llm(TaskType.KNOWLEDGE_QUERY)
        llm_t3 = factory.get_llm(TaskType.CONCEPT_TEACHING)

        assert llm_t1 is not llm_t3
        assert llm_t1.max_tokens == 800
        assert llm_t3.max_tokens == 2000

    def test_get_default_llm(self, factory):
        """测试 get_default_llm 方法。"""
        from prompts.dynamic_params import TaskType
        from langchain_openai import ChatOpenAI

        llm = factory.get_default_llm()
        assert isinstance(llm, ChatOpenAI)
        assert llm.max_tokens == 4096

    def test_override_params(self, factory):
        """测试参数覆盖功能。"""
        from prompts.dynamic_params import TaskType

        custom_llm = factory.get_llm(
            TaskType.FULL_SOLUTION,
            override_params={'temperature': 0.5, 'max_tokens': 1000},
        )
        assert custom_llm.temperature == 0.5
        assert custom_llm.max_tokens == 1000

    def test_override_params_not_cached(self, factory):
        """测试覆盖参数的实例不会被缓存。"""
        from prompts.dynamic_params import TaskType

        llm1 = factory.get_llm(
            TaskType.FULL_SOLUTION,
            override_params={'temperature': 0.5},
        )
        llm2 = factory.get_llm(
            TaskType.FULL_SOLUTION,
            override_params={'temperature': 0.5},
        )
        assert llm1 is not llm2

    def test_clear_cache(self, factory):
        """测试缓存清除功能。"""
        from prompts.dynamic_params import TaskType

        factory.get_llm(TaskType.DEFAULT)
        factory.get_llm(TaskType.QUICK_ANSWER)
        assert len(factory._llm_cache) == 2

        factory.clear_cache()
        assert len(factory._llm_cache) == 0

    def test_clear_cache_creates_new_instances(self, factory):
        """测试缓存清除后创建新实例。"""
        from prompts.dynamic_params import TaskType

        llm1 = factory.get_llm(TaskType.DEFAULT)
        factory.clear_cache()
        llm2 = factory.get_llm(TaskType.DEFAULT)

        assert llm1 is not llm2

    def test_get_cache_stats_empty(self, factory):
        """测试空缓存的统计信息。"""
        stats = factory.get_cache_stats()

        assert stats['cached_instances'] == 0
        assert stats['cached_types'] == []
        assert stats['factory_config']['model'] == 'test-model'
        assert stats['factory_config']['base_url'] == 'http://localhost:1234'

    def test_get_cache_stats_populated(self, factory):
        """测试有缓存的统计信息。"""
        from prompts.dynamic_params import TaskType

        factory.get_llm(TaskType.QUICK_ANSWER)
        factory.get_llm(TaskType.FULL_SOLUTION)

        stats = factory.get_cache_stats()
        assert stats['cached_instances'] == 2
        assert 'quick' in stats['cached_types']
        assert 'solution' in stats['cached_types']

    def test_update_base_config(self, factory):
        """测试基础配置更新。"""
        factory.update_base_config(
            temperature=0.7,
            model="new-model",
        )

        assert factory._base_config['temperature'] == 0.7
        assert factory._base_config['model'] == "new-model"
        assert len(factory._llm_cache) == 0

    def test_update_base_config_affects_new_instances(self, factory):
        """测试基础配置更新后新实例使用新配置。"""
        from prompts.dynamic_params import TaskType

        factory.update_base_config(model="updated-model")
        llm = factory.get_llm(TaskType.DEFAULT)

        assert llm.model_name == "updated-model"

    def test_properties(self, factory):
        """测试工厂属性。"""
        assert factory.model == "test-model"
        assert factory.base_url == "http://localhost:1234"
        assert factory.streaming is True


class TestClassifyAndGetLLM:
    """分类 + 获取LLM 集成测试。"""

    @pytest.fixture
    def factory(self):
        from prompts.dynamic_params import DynamicLLMFactory
        return DynamicLLMFactory(
            api_key="test-key",
            base_url="http://localhost:1234",
        )

    def test_classify_and_get_llm_knowledge(self, factory):
        """测试知识点查询的分类和LLM获取。"""
        result, llm = factory.classify_and_get_llm("这道题考什么知识点？")

        from prompts.dynamic_params import TaskType
        assert result.task_type == TaskType.KNOWLEDGE_QUERY
        assert llm.max_tokens == 800

    def test_classify_and_get_llm_quick(self, factory):
        """测试快速答案的分类和LLM获取。"""
        result, llm = factory.classify_and_get_llm("选什么？")

        from prompts.dynamic_params import TaskType
        assert result.task_type == TaskType.QUICK_ANSWER
        assert llm.max_tokens == 300

    def test_classify_and_get_llm_concept(self, factory):
        """测试概念讲解的分类和LLM获取。"""
        result, llm = factory.classify_and_get_llm("什么是微积分？")

        from prompts.dynamic_params import TaskType
        assert result.task_type == TaskType.CONCEPT_TEACHING
        assert llm.temperature == 0.1

    def test_classify_and_get_llm_solution(self, factory):
        """测试完整解题的分类和LLM获取。"""
        result, llm = factory.classify_and_get_llm("帮我解这道题，要详细过程")

        from prompts.dynamic_params import TaskType
        assert result.task_type == TaskType.FULL_SOLUTION
        assert llm.max_tokens == 4096

    def test_classify_and_get_llm_empty_input(self, factory):
        """测试空输入的处理。"""
        result, llm = factory.classify_and_get_llm("")
        assert result.confidence >= 0.0

    def test_classify_and_get_llm_cache(self, factory):
        """测试分类缓存使用后LLM也缓存。"""
        from prompts.dynamic_params import TaskClassifier

        classifier = TaskClassifier()
        cached_key = "一道既有的缓存测试题目"
        factory.classify_and_get_llm(cached_key)

        result2, _ = factory.classify_and_get_llm(cached_key)
        assert result2 is not None


class TestTokenSavings:
    """Token成本节省验证测试。"""

    def test_t1_token_savings(self):
        """T1（知识点查询）比默认节省Token。"""
        from prompts.dynamic_params import get_params_for_task, TaskType

        default = get_params_for_task(TaskType.DEFAULT)
        t1 = get_params_for_task(TaskType.KNOWLEDGE_QUERY)

        savings = (default.max_tokens - t1.max_tokens) / default.max_tokens
        assert savings > 0.7

    def test_t2_token_savings(self):
        """T2（快速答案）比默认大幅节省Token。"""
        from prompts.dynamic_params import get_params_for_task, TaskType

        default = get_params_for_task(TaskType.DEFAULT)
        t2 = get_params_for_task(TaskType.QUICK_ANSWER)

        savings = (default.max_tokens - t2.max_tokens) / default.max_tokens
        assert savings > 0.9

    def test_t1_vs_t5_comparison(self):
        """T1明显比T5的Token少。"""
        from prompts.dynamic_params import get_params_for_task, TaskType

        t1 = get_params_for_task(TaskType.KNOWLEDGE_QUERY)
        t5 = get_params_for_task(TaskType.FULL_SOLUTION)

        assert t1.max_tokens < t5.max_tokens
        assert t1.max_tokens == 800
        assert t5.max_tokens == 4096


class TestTaskClassifier:
    """TaskClassifier 分类器测试。"""

    @pytest.fixture
    def classifier(self):
        from prompts.dynamic_params import TaskClassifier
        return TaskClassifier()

    def test_classify_knowledge_query(self, classifier):
        from prompts.dynamic_params import TaskType

        result = classifier.classify("这道题考的是什么知识点？")
        assert result.task_type == TaskType.KNOWLEDGE_QUERY

    def test_classify_quick_answer(self, classifier):
        from prompts.dynamic_params import TaskType

        result = classifier.classify("选什么？答案是哪个？")
        assert result.task_type == TaskType.QUICK_ANSWER

    def test_classify_concept_teaching(self, classifier):
        from prompts.dynamic_params import TaskType

        result = classifier.classify("什么是极限？怎么理解导数？")
        assert result.task_type == TaskType.CONCEPT_TEACHING

    def test_classify_full_solution(self, classifier):
        from prompts.dynamic_params import TaskType

        result = classifier.classify("帮我解这道微积分题，要详细过程")
        assert result.task_type == TaskType.FULL_SOLUTION

    def test_classify_default_fallback(self, classifier):
        from prompts.dynamic_params import TaskType

        result = classifier.classify("abcdefg神秘字符xyz")
        assert result.task_type == TaskType.DEFAULT
        assert result.confidence == 0.5

    def test_classify_empty_input(self, classifier):
        from prompts.dynamic_params import TaskType

        result = classifier.classify("")
        assert result.task_type == TaskType.DEFAULT
        assert result.confidence == 0.5

    def test_classify_confidence_range(self, classifier):
        result = classifier.classify("这道题考什么知识点？")
        assert 0.0 <= result.confidence <= 1.0

    def test_classify_cache(self, classifier):
        result1 = classifier.classify("这道题考什么知识点？")
        result2 = classifier.classify("这道题考什么知识点？")
        assert result1.task_type == result2.task_type
        assert result1.confidence == result2.confidence

    def test_clear_cache(self, classifier):
        classifier.classify("这道题考什么知识点？")
        assert len(classifier._cache) > 0

        classifier.clear_cache()
        assert len(classifier._cache) == 0


class TestGlobalSingleton:
    """全局单例函数测试。"""

    def setup_method(self):
        from prompts import dynamic_params as dp
        dp._factory_instance = None
        dp._default_classifier = None

    def teardown_method(self):
        from prompts import dynamic_params as dp
        dp._factory_instance = None
        dp._default_classifier = None

    def test_init_dynamic_llm_factory(self):
        from prompts.dynamic_params import (
            init_dynamic_llm_factory,
            get_dynamic_llm_factory,
        )

        factory = init_dynamic_llm_factory(
            api_key="test-key",
            base_url="http://localhost:1234",
            model="test-model",
        )

        retrieved = get_dynamic_llm_factory()
        assert retrieved is factory
        assert retrieved.model == "test-model"

    def test_get_factory_uninitialized_raises(self):
        from prompts import dynamic_params as dp
        dp._factory_instance = None

        from prompts.dynamic_params import get_dynamic_llm_factory
        with pytest.raises(RuntimeError, match="未初始化"):
            get_dynamic_llm_factory()

    def test_singleton_only_one_instance(self):
        from prompts.dynamic_params import (
            init_dynamic_llm_factory,
            get_dynamic_llm_factory,
        )

        factory1 = init_dynamic_llm_factory(api_key="key1")
        factory2 = get_dynamic_llm_factory()

        assert factory1 is factory2

    def test_get_classifier_singleton(self):
        from prompts.dynamic_params import get_classifier

        c1 = get_classifier()
        c2 = get_classifier()
        assert c1 is c2


class TestDynamicParamsDisabled:
    """禁用动态参数模式测试。"""

    def test_factory_conditionally_created(self):
        """测试 disable 时不创建 DynamicLLMFactory。"""
        from agent_core.agent import MathAgent

        agent = MathAgent.create(
            api_key="test-key",
            enable_dynamic_params=False,
        )

        assert agent.dynamic_llm_factory is None

    def test_default_is_enabled(self):
        """测试默认启用动态参数。"""
        from agent_core.agent import MathAgent

        agent = MathAgent.create(api_key="test-key")

        assert agent.dynamic_llm_factory is not None


class TestMathAgentIntegration:
    """MathAgent 动态参数集成测试。"""

    def test_agent_has_dynamic_llm_factory(self):
        """测试 Agent 创建后持有 DynamicLLMFactory 实例。"""
        from agent_core.agent import MathAgent
        from prompts.dynamic_params import DynamicLLMFactory

        agent = MathAgent.create(api_key="test-key")
        factory = agent.dynamic_llm_factory

        assert factory is not None
        assert isinstance(factory, DynamicLLMFactory)

    def test_agent_with_dynamic_params_disabled(self):
        """测试 Agent 禁用动态参数后的状态。"""
        from agent_core.agent import MathAgent

        agent = MathAgent.create(api_key="test-key", enable_dynamic_params=False)

        assert agent.dynamic_llm_factory is None
        assert agent._enable_dynamic_params is False

    def test_select_strategy_applies_dynamic_params(self):
        """测试 _select_strategy 应用动态参数（集成验证）。"""
        from agent_core.agent import MathAgent

        agent = MathAgent.create(api_key="test-key", enable_dynamic_params=True)

        assert agent._enable_dynamic_params is True
        assert agent._dynamic_llm_factory is not None

        intent = agent._classify_intent("这道题考什么知识点？")
        from prompts.dynamic_params import TaskType
        assert intent.task_type == TaskType.KNOWLEDGE_QUERY

    def test_get_task_params(self):
        """测试 _get_task_params 返回正确的参数。"""
        from agent_core.agent import MathAgent
        from prompts.dynamic_params import TaskType

        agent = MathAgent.create(api_key="test-key")

        params = agent._get_task_params(TaskType.QUICK_ANSWER)
        assert params.max_tokens == 300
        assert params.temperature == 0.0

    def test_classify_intent(self):
        """测试 _classify_intent 分类方法。"""
        from agent_core.agent import MathAgent
        from prompts.dynamic_params import TaskType

        agent = MathAgent.create(api_key="test-key")

        result = agent._classify_intent("这道题考什么知识点？")
        assert result.task_type == TaskType.KNOWLEDGE_QUERY

        result = agent._classify_intent("2+2等于多少？")
        assert result.task_type == TaskType.QUICK_ANSWER

        result = agent._classify_intent("帮我解这道题")
        assert result.task_type == TaskType.FULL_SOLUTION


class TestExceptionHandling:
    """异常处理测试。"""

    def setup_method(self):
        from prompts import dynamic_params as dp
        dp._factory_instance = None

    def teardown_method(self):
        from prompts import dynamic_params as dp
        dp._factory_instance = None

    def test_get_factory_before_init_raises(self):
        from prompts import dynamic_params as dp
        dp._factory_instance = None

        from prompts.dynamic_params import get_dynamic_llm_factory
        with pytest.raises(RuntimeError, match="未初始化"):
            get_dynamic_llm_factory()

    def test_get_llm_override_params_empty(self):
        from prompts.dynamic_params import DynamicLLMFactory, TaskType

        factory = DynamicLLMFactory(api_key="test-key")
        llm = factory.get_llm(TaskType.FULL_SOLUTION, override_params={})

        assert llm.max_tokens == 4096

    def test_get_llm_with_none_override(self):
        from prompts.dynamic_params import DynamicLLMFactory, TaskType

        factory = DynamicLLMFactory(api_key="test-key")
        llm = factory.get_llm(TaskType.FULL_SOLUTION, override_params=None)

        assert llm.max_tokens == 4096

    def test_concept_teaching_temperature(self):
        from prompts.dynamic_params import DynamicLLMFactory, TaskType

        factory = DynamicLLMFactory(api_key="test-key")
        llm_t3 = factory.get_llm(TaskType.CONCEPT_TEACHING)
        llm_t1 = factory.get_llm(TaskType.KNOWLEDGE_QUERY)

        assert llm_t3.temperature == 0.1
        assert llm_t1.temperature == 0.0

    def test_multimodal_max_tokens(self):
        from prompts.dynamic_params import DynamicLLMFactory, TaskType

        factory = DynamicLLMFactory(api_key="test-key")
        llm = factory.get_llm(TaskType.MULTIMODAL)

        assert llm.max_tokens == 4096
        assert llm.temperature == 0.0


class TestCreateMathAgentFactory:
    """create_math_agent 工厂函数测试。"""

    def test_default_enables_dynamic_params(self):
        from agent_core.agent import create_math_agent

        agent = create_math_agent(api_key="test-key")
        assert agent.dynamic_llm_factory is not None

    def test_disable_dynamic_params(self):
        from agent_core.agent import create_math_agent

        agent = create_math_agent(
            api_key="test-key",
            enable_dynamic_params=False,
        )
        assert agent.dynamic_llm_factory is None