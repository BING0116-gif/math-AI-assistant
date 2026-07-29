"""
TaskPlanner 模块完整测试套件。

覆盖：
- TaskDAG: 有向无环图（纯逻辑，无外部依赖）
- TaskPlanner: 核心规划器（需mock LLM）
- ExecutionPlan: 计划管理与状态机
- PlannedStrategy: 执行策略（需mock较多组件）
- PlanCache: 缓存
- Security: 安全功能
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

from agent_core.task_planner import (
    Task,
    TaskStatus,
    TaskPriority,
    PlanStatus,
    TaskDAG,
    ExecutionPlan,
    PlanningContext,
    PlannerConfig,
    ProblemAnalysis,
    TaskPlanner,
    PlanCache,
    PlanningError,
    CircularDependencyError,
    PlanningTimeoutError,
    PlanValidationError,
    SecurityConfig,
    RateLimiter,
    DataPrivacyManager,
    SecureErrorHandler,
    _estimate_complexity,
    _count_math_symbols,
    _extract_problem_type,
)
from agent_core.strategies.planned import PlannedStrategy
from tools.hybrid_registry import HybridToolRegistry as ToolRegistry
from tools.base_tool import BaseTool, ToolInput, ToolOutput, ToolCapability


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_llm():
    """Mock LLM 实例。"""
    llm = MagicMock()
    llm.ainvoke = AsyncMock()
    return llm


@pytest.fixture
def sample_registry():
    """包含预注册工具的 ToolRegistry。"""
    registry = ToolRegistry()
    return registry


@pytest.fixture
def default_config():
    """默认 PlannerConfig。"""
    return PlannerConfig()


@pytest.fixture
def sample_context():
    """示例 PlanningContext。"""
    return PlanningContext(
        session_id="test_session",
        user_id="test_user",
        user_level="高中",
        weak_points=["不定积分"],
    )


@pytest.fixture
def analysis_response():
    """标准的 LLM 问题分析响应 JSON。"""
    return json.dumps({
        "problem_type": "综合",
        "knowledge_points": ["导数", "极值"],
        "complexity": 3,
        "suggested_tools": ["math_solver"],
        "sub_steps_count": 4,
        "has_visualization_need": False,
        "reasoning": "需要求导后分析极值",
    }, ensure_ascii=False)


@pytest.fixture
def generation_response():
    """标准的 LLM 任务生成响应 JSON。"""
    return json.dumps({
        "tasks": [
            {"id": "t1", "name": "求导", "tool_name": "math_solver",
             "parameters": {"query": "求导"}, "dependencies": [], "priority": "high",
             "estimated_time": 2.0, "required_capabilities": []},
            {"id": "t2", "name": "求驻点", "tool_name": "math_solver",
             "parameters": {"query": "解方程"}, "dependencies": ["t1"], "priority": "high",
             "estimated_time": 2.0, "required_capabilities": []},
            {"id": "t3", "name": "整合答案", "tool_name": None,
             "parameters": {}, "dependencies": ["t2"], "priority": "critical",
             "estimated_time": 3.0, "required_capabilities": []},
        ]
    }, ensure_ascii=False)


@pytest.fixture
def sample_dag():
    """示例 DAG: t1 → t2 → t4, t1 → t3 → t4。"""
    dag = TaskDAG()
    for tid, name in [("t1", "分析"), ("t2", "计算A"), ("t3", "计算B"), ("t4", "汇总")]:
        task = Task(id=tid, name=name, description=name)
        dag.add_node(tid, task)
    dag.add_edge("t1", "t2")
    dag.add_edge("t1", "t3")
    dag.add_edge("t2", "t4")
    dag.add_edge("t3", "t4")
    return dag


@pytest.fixture
def sample_plan(sample_dag):
    """示例 ExecutionPlan。"""
    return ExecutionPlan(
        plan_id="test_plan_001",
        problem="求f(x)=x³-3x的最值",
        tasks=sample_dag.nodes,
        dag=sample_dag,
    )


# ============================================================================
# TestTaskDAG — 纯逻辑测试，无外部依赖
# ============================================================================

class TestTaskDAG:
    """TaskDAG 单元测试。"""

    def test_dg01_empty_dag(self):
        """空图操作。"""
        dag = TaskDAG()
        assert dag.size == 0
        assert dag.topological_sort() == []
        assert dag.get_parallel_groups() == []

    def test_dg02_single_node(self):
        """单节点无依赖。"""
        dag = TaskDAG()
        task = Task(id="t1", name="测试", description="测试")
        dag.add_node("t1", task)
        assert dag.size == 1
        assert dag.topological_sort() == ["t1"]
        assert dag.get_parallel_groups() == [["t1"]]
        assert not dag.has_cycle()

    def test_dg03_linear_chain(self):
        """线性链 A→B→C→D。"""
        dag = TaskDAG()
        for tid in ["A", "B", "C", "D"]:
            dag.add_node(tid, Task(id=tid, name=tid, description=tid))
        dag.add_edge("A", "B")
        dag.add_edge("B", "C")
        dag.add_edge("C", "D")
        assert dag.topological_sort() == ["A", "B", "C", "D"]
        groups = dag.get_parallel_groups()
        assert len(groups) == 4
        assert groups == [["A"], ["B"], ["C"], ["D"]]

    def test_dg04_diamond_dependency(self):
        """菱形依赖 A→[B,C]→D。"""
        dag = TaskDAG()
        for tid in ["A", "B", "C", "D"]:
            dag.add_node(tid, Task(id=tid, name=tid, description=tid))
        dag.add_edge("A", "B")
        dag.add_edge("A", "C")
        dag.add_edge("B", "D")
        dag.add_edge("C", "D")
        groups = dag.get_parallel_groups()
        assert groups[0] == ["A"]
        assert set(groups[1]) == {"B", "C"}
        assert groups[2] == ["D"]

    def test_dg05_cycle_detection(self):
        """循环检测 A→B→C→A。"""
        dag = TaskDAG()
        for tid in ["A", "B", "C"]:
            dag.add_node(tid, Task(id=tid, name=tid, description=tid))
        dag.add_edge("A", "B")
        dag.add_edge("B", "C")
        dag.add_edge("C", "A")
        assert dag.has_cycle()
        with pytest.raises(CircularDependencyError):
            dag.topological_sort()

    def test_dg06_self_loop(self):
        """自环检测 A→A。"""
        dag = TaskDAG()
        dag.add_node("A", Task(id="A", name="A", description="A"))
        dag.add_edge("A", "A")
        assert dag.has_cycle()

    def test_dg07_isolated_node(self):
        """孤立节点。"""
        dag = TaskDAG()
        dag.add_node("A", Task(id="A", name="A", description="A"))
        dag.add_node("B", Task(id="B", name="B", description="B"))
        dag.add_node("D", Task(id="D", name="D", description="D"))
        dag.add_edge("A", "B")
        topo = dag.topological_sort()
        assert "D" in topo
        assert len(topo) == 3

    def test_dg08_multiple_incoming_edges(self):
        """多入边 C←A, C←B。"""
        dag = TaskDAG()
        for tid in ["A", "B", "C"]:
            dag.add_node(tid, Task(id=tid, name=tid, description=tid))
        dag.add_edge("A", "C")
        dag.add_edge("B", "C")
        topo = dag.topological_sort()
        assert topo.index("C") > topo.index("A")
        assert topo.index("C") > topo.index("B")

    def test_dg09_multiple_outgoing_edges(self):
        """多出边 A→B, A→C。"""
        dag = TaskDAG()
        for tid in ["A", "B", "C"]:
            dag.add_node(tid, Task(id=tid, name=tid, description=tid))
        dag.add_edge("A", "B")
        dag.add_edge("A", "C")
        groups = dag.get_parallel_groups()
        assert groups[0] == ["A"]
        assert set(groups[1]) == {"B", "C"}

    def test_dg10_large_dag(self):
        """大规模 DAG(20节点)。"""
        dag = TaskDAG()
        for i in range(20):
            dag.add_node(f"t{i}", Task(id=f"t{i}", name=f"Task{i}", description=f"t{i}"))
        for i in range(19):
            dag.add_edge(f"t{i}", f"t{i+1}")
        for i in range(0, 18, 2):
            dag.add_edge(f"t{i}", f"t{i+2}")
        start = time.perf_counter()
        topo = dag.topological_sort()
        elapsed = (time.perf_counter() - start) * 1000
        assert len(topo) == 20
        assert elapsed < 50, f"拓扑排序耗时{elapsed:.1f}ms超过50ms"

    def test_dg11_remove_node(self):
        """删除节点后的DAG。"""
        dag = TaskDAG()
        for tid in ["A", "B", "C"]:
            dag.add_node(tid, Task(id=tid, name=tid, description=tid))
        dag.add_edge("A", "B")
        dag.add_edge("B", "C")
        dag.remove_node("B")
        assert dag.size == 2
        assert ("B", "C") not in dag.edges

    def test_dg12_critical_path(self):
        """关键路径正确性。"""
        dag = TaskDAG()
        t1 = Task(id="t1", name="A", description="A", estimated_time=1.0)
        t2 = Task(id="t2", name="B", description="B", estimated_time=10.0)
        t3 = Task(id="t3", name="C", description="C", estimated_time=1.0)
        t4 = Task(id="t4", name="D", description="D", estimated_time=1.0)
        dag.add_node("t1", t1)
        dag.add_node("t2", t2)
        dag.add_node("t3", t3)
        dag.add_node("t4", t4)
        dag.add_edge("t1", "t2")
        dag.add_edge("t1", "t3")
        dag.add_edge("t2", "t4")
        dag.add_edge("t3", "t4")
        path = dag.get_critical_path()
        assert "t2" in path

    def test_dg13_get_ready_nodes(self):
        """就绪节点获取。"""
        dag = TaskDAG()
        for tid in ["A", "B", "C"]:
            dag.add_node(tid, Task(id=tid, name=tid, description=tid))
        dag.add_edge("A", "B")
        dag.add_edge("A", "C")
        ready = dag.get_ready_nodes(set())
        assert ready == ["A"]
        ready = dag.get_ready_nodes({"A"})
        assert set(ready) == {"B", "C"}

    def test_dg14_dag_validation(self):
        """DAG 合法性验证。"""
        dag = TaskDAG()
        dag.add_node("A", Task(id="A", name="A", description="A", dependencies=["B"]))
        is_valid, error = dag.validate()
        assert not is_valid
        assert "B" in error


# ============================================================================
# TestTaskPlanner — 需mock LLM
# ============================================================================

class TestTaskPlanner:
    """TaskPlanner 单元测试。"""

    def test_tp01_simple_problem_no_planning(self, mock_llm, sample_registry):
        """简单问题不触发规划。"""
        planner = TaskPlanner(llm=mock_llm, registry=sample_registry)
        assert not planner.should_plan("1+1=?")
        assert not planner.should_plan("什么是导数？")

    def test_tp02_complex_problem_triggers_planning(self, mock_llm, sample_registry):
        """复杂问题触发规划。"""
        planner = TaskPlanner(llm=mock_llm, registry=sample_registry)
        assert planner.should_plan("求f(x)=x³-3x的极值并且判断单调性然后画出图像最后验证")

    def test_tp03_plan_normal_flow(
        self, mock_llm, sample_registry, analysis_response, generation_response
    ):
        """plan()正常流程。"""
        mock_llm.ainvoke = AsyncMock(side_effect=[
            MagicMock(content=analysis_response),
            MagicMock(content=generation_response),
        ])

        planner = TaskPlanner(llm=mock_llm, registry=sample_registry)
        plan = asyncio.run(planner.plan("求f(x)=x³-3x的极值并判断单调性"))

        assert plan.total_tasks == 3
        assert "t1" in plan.tasks
        assert "t2" in plan.tasks
        assert "t3" in plan.tasks
        assert plan.tasks["t1"].name == "求导"

    def test_tp04_plan_llm_returns_invalid_json(
        self, mock_llm, sample_registry
    ):
        """plan()LLM返回非法JSON。"""
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="这不是有效的JSON"))

        planner = TaskPlanner(llm=mock_llm, registry=sample_registry)
        plan = asyncio.run(planner.plan("求f(x)=x³-3x的极值并判断单调性"))
        assert plan.metadata.get("is_fallback") is True

    def test_tp05_plan_timeout(self, mock_llm, sample_registry):
        """plan()超时处理。"""
        async def slow_response(*args, **kwargs):
            await asyncio.sleep(2.0)
            return MagicMock(content="{}")

        mock_llm.ainvoke = slow_response

        config = PlannerConfig(planning_timeout_seconds=0.5)
        planner = TaskPlanner(llm=mock_llm, registry=sample_registry, config=config)
        plan = asyncio.run(planner.plan("求f(x)=x³-3x的极值并判断单调性"))
        assert plan.metadata.get("is_fallback") is True

    def test_tp06_plan_task_limit_exceeded(
        self, mock_llm, sample_registry
    ):
        """plan()任务数超限。"""
        tasks = [{"id": f"t{i}", "name": f"Task{i}", "tool_name": None,
                  "parameters": {}, "dependencies": [], "priority": "normal"}
                 for i in range(15)]
        response = json.dumps({"tasks": tasks}, ensure_ascii=False)

        mock_llm.ainvoke = AsyncMock(side_effect=[
            MagicMock(content=json.dumps({
                "problem_type": "综合", "complexity": 3,
                "sub_steps_count": 15, "has_visualization_need": False,
                "knowledge_points": [], "suggested_tools": [], "reasoning": ""
            }, ensure_ascii=False)),
            MagicMock(content=response),
        ])

        config = PlannerConfig(max_tasks_per_plan=10)
        planner = TaskPlanner(llm=mock_llm, registry=sample_registry, config=config)
        plan = asyncio.run(planner.plan("复杂综合题"))
        assert plan.total_tasks <= 10

    def test_tp07_should_plan_disabled(self, mock_llm, sample_registry):
        """规划器禁用时不触发规划。"""
        planner = TaskPlanner(llm=mock_llm, registry=sample_registry)
        planner.enabled = False
        assert not planner.should_plan("求f(x)=x³-3x的极值并判断单调性然后画出图像")

    def test_tp08_cache_hit(
        self, mock_llm, sample_registry, analysis_response, generation_response
    ):
        """缓存命中。"""
        mock_llm.ainvoke = AsyncMock(side_effect=[
            MagicMock(content=analysis_response),
            MagicMock(content=generation_response),
        ])

        planner = TaskPlanner(llm=mock_llm, registry=sample_registry)
        problem = "求f(x)=x³-3x的极值"

        plan1 = asyncio.run(planner.plan(problem))
        plan2 = asyncio.run(planner.plan(problem))

        assert plan1.plan_id == plan2.plan_id
        stats = planner.get_cache_stats()
        assert stats["hits"] >= 1

    def test_tp09_cache_clear(self, mock_llm, sample_registry):
        """缓存清空。"""
        planner = TaskPlanner(llm=mock_llm, registry=sample_registry)
        planner.clear_cache()
        stats = planner.get_cache_stats()
        assert stats["size"] == 0

    def test_tp10_fallback_plan(self, mock_llm, sample_registry):
        """降级方案创建。"""
        planner = TaskPlanner(llm=mock_llm, registry=sample_registry)
        plan = planner._create_fallback_plan("测试问题")
        assert plan.total_tasks == 1
        assert plan.metadata.get("is_fallback") is True


# ============================================================================
# TestExecutionPlan
# ============================================================================

class TestExecutionPlan:
    """ExecutionPlan 单元测试。"""

    def test_ep01_empty_plan(self):
        """空计划。"""
        dag = TaskDAG()
        plan = ExecutionPlan(plan_id="p1", problem="", tasks={}, dag=dag)
        assert plan.task_list == []
        assert plan.is_complete()

    def test_ep02_mark_completed(self, sample_plan):
        """标记任务完成。"""
        sample_plan.mark_completed("t1", "结果1")
        assert sample_plan.tasks["t1"].status == TaskStatus.COMPLETED
        assert sample_plan.tasks["t1"].result == "结果1"

    def test_ep03_mark_failed(self, sample_plan):
        """标记任务失败。"""
        sample_plan.mark_failed("t1", "错误信息")
        assert sample_plan.tasks["t1"].status == TaskStatus.FAILED
        assert sample_plan.tasks["t1"].error == "错误信息"

    def test_ep04_get_ready_tasks(self, sample_plan):
        """就绪任务获取。"""
        sample_plan.mark_completed("t1", "完成")
        ready = sample_plan.get_ready_tasks()
        ready_ids = {t.id for t in ready}
        assert "t2" in ready_ids
        assert "t3" in ready_ids

    def test_ep05_all_complete(self, sample_plan):
        """全部完成判断。"""
        for tid in ["t1", "t2", "t3", "t4"]:
            sample_plan.mark_completed(tid, f"result_{tid}")
        assert sample_plan.is_complete()

    def test_ep06_serialization(self, sample_plan):
        """序列化/反序列化。"""
        data = sample_plan.to_dict()
        assert data["plan_id"] == "test_plan_001"
        assert len(data["tasks"]) == 4
        assert len(data["dag_edges"]) == 4

    def test_ep07_summary(self, sample_plan):
        """summary()格式。"""
        s = sample_plan.summary()
        assert "解题计划" in s
        assert "4" in s

    def test_ep08_parallel_groups(self, sample_plan):
        """并行分组。"""
        groups = sample_plan.parallel_groups
        assert groups[0] == ["t1"]
        assert set(groups[1]) == {"t2", "t3"}
        assert groups[2] == ["t4"]


# ============================================================================
# TestPlannedStrategy — 集成测试
# ============================================================================

class TestPlannedStrategy:
    """PlannedStrategy 测试。"""

    def _make_strategy(self, mock_llm, registry, task_planner=None):
        """构建测试用 PlannedStrategy。"""
        from agent_core.thought import ThoughtRecorder
        planner = task_planner or TaskPlanner(llm=mock_llm, registry=registry)
        return PlannedStrategy(
            llm_chain=mock_llm,
            registry=registry,
            task_planner=planner,
            thought_recorder=ThoughtRecorder(),
        )

    def test_ps01_serial_execution(self, mock_llm, sample_registry):
        """串行计划执行。"""
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="推理结果"))

        dag = TaskDAG()
        for tid, name in [("t1", "步骤1"), ("t2", "步骤2"), ("t3", "步骤3")]:
            dag.add_node(tid, Task(id=tid, name=name, description=name, tool_name=None))
        dag.add_edge("t1", "t2")
        dag.add_edge("t2", "t3")

        plan = ExecutionPlan(plan_id="p_seq", problem="测试", tasks=dag.nodes, dag=dag)

        strategy = self._make_strategy(mock_llm, sample_registry)
        result = asyncio.run(strategy.execute("测试", "s1", {}, plan))
        assert result is not None

    def test_ps02_parallel_execution(self, mock_llm, sample_registry):
        """并行计划执行。"""
        mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="推理结果"))

        dag = TaskDAG()
        for tid in ["A", "B", "C", "D"]:
            dag.add_node(tid, Task(id=tid, name=tid, description=tid, tool_name=None))
        dag.add_edge("A", "B")
        dag.add_edge("A", "C")
        dag.add_edge("B", "D")
        dag.add_edge("C", "D")

        plan = ExecutionPlan(plan_id="p_par", problem="测试", tasks=dag.nodes, dag=dag)

        strategy = self._make_strategy(mock_llm, sample_registry)
        result = asyncio.run(strategy.execute("测试", "s1", {}, plan))
        assert result is not None

    def test_ps03_no_plan_provided(self, mock_llm, sample_registry):
        """未提供执行计划。"""
        async def collect():
            chunks = []
            strategy = self._make_strategy(mock_llm, sample_registry)
            async for chunk in strategy.stream("测试", "s1", {}):
                chunks.append(chunk)
            return "".join(chunks)
        result = asyncio.run(collect())
        assert "错误" in result


# ============================================================================
# TestPlanCache
# ============================================================================

class TestPlanCache:
    """PlanCache 单元测试。"""

    def test_cache_set_get(self, sample_plan):
        """缓存存取。"""
        cache = PlanCache(max_size=10, ttl_seconds=3600)
        cache.set("测试问题", sample_plan)
        result = cache.get("测试问题")
        assert result is not None
        assert result.plan_id == "test_plan_001"

    def test_cache_miss(self):
        """缓存未命中。"""
        cache = PlanCache()
        assert cache.get("不存在") is None

    def test_cache_invalidate(self, sample_plan):
        """缓存失效。"""
        cache = PlanCache()
        cache.set("测试", sample_plan)
        cache.invalidate("测试")
        assert cache.get("测试") is None

    def test_cache_ttl_expiry(self, sample_plan):
        """TTL过期。"""
        cache = PlanCache(ttl_seconds=0.01)
        cache.set("测试", sample_plan)
        time.sleep(0.02)
        assert cache.get("测试") is None

    def test_cache_max_size(self):
        """缓存最大容量。"""
        cache = PlanCache(max_size=2, ttl_seconds=3600)
        dag = TaskDAG()
        for i in range(5):
            plan = ExecutionPlan(plan_id=f"p{i}", problem=f"q{i}", tasks={}, dag=dag)
            cache.set(f"q{i}", plan)
        assert cache.stats["size"] <= 2

    def test_cache_clear(self, sample_plan):
        """缓存清空。"""
        cache = PlanCache()
        cache.set("测试", sample_plan)
        cache.clear()
        assert cache.stats["size"] == 0
        assert cache.stats["hits"] == 0

    def test_cache_stats(self, sample_plan):
        """缓存统计。"""
        cache = PlanCache()
        cache.set("测试", sample_plan)
        cache.get("测试")
        cache.get("不存在")
        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1


# ============================================================================
# TestSecurity
# ============================================================================

class TestSecurity:
    """安全功能测试。"""

    def test_sec01_input_length_limit(self, mock_llm, sample_registry):
        """超长输入截断。"""
        planner = TaskPlanner(llm=mock_llm, registry=sample_registry)
        long_input = "x" * 3000
        sanitized = planner._sanitize_problem_input(long_input)
        assert len(sanitized) <= 2000

    def test_sec02_control_characters_filtered(self, mock_llm, sample_registry):
        """控制字符过滤。"""
        planner = TaskPlanner(llm=mock_llm, registry=sample_registry)
        result = planner._sanitize_problem_input("test\x00\x1fhello")
        assert "\x00" not in result
        assert "\x1f" not in result

    def test_sec03_empty_input_raises(self, mock_llm, sample_registry):
        """空输入抛异常。"""
        planner = TaskPlanner(llm=mock_llm, registry=sample_registry)
        with pytest.raises(ValueError):
            planner._sanitize_problem_input("")

    def test_sec04_rate_limiter(self):
        """频率限制。"""
        rl = RateLimiter()
        for _ in range(30):
            assert rl.check_rate_limit("user1")
        assert not rl.check_rate_limit("user1")

    def test_sec05_privacy_sanitization(self):
        """隐私数据脱敏。"""
        text = "我的手机号是13812345678，邮箱是test@example.com"
        sanitized = DataPrivacyManager.sanitize_user_input(text)
        assert "13812345678" not in sanitized
        assert "test@example.com" not in sanitized

    def test_sec06_error_handler(self):
        """错误信息安全处理。"""
        result = SecureErrorHandler.handle_error(ValueError("测试错误"))
        assert not result["success"]
        assert "error" in result
        assert "id" in result["error"]
        assert "INTERNAL_ERROR" not in result["error"]["message"]

    def test_sec07_context_validation(self, mock_llm, sample_registry):
        """上下文验证。"""
        planner = TaskPlanner(llm=mock_llm, registry=sample_registry)
        ctx = PlanningContext(user_level="小学")
        planner._validate_context(ctx)
        assert ctx.user_level == "小学"

    def test_sec08_invalid_user_level_defaults(self, mock_llm, sample_registry):
        """无效用户水平使用默认值。"""
        planner = TaskPlanner(llm=mock_llm, registry=sample_registry)
        ctx = PlanningContext(user_level="博士")
        planner._validate_context(ctx)
        assert ctx.user_level == "高中"


# ============================================================================
# TestHelpers
# ============================================================================

class TestHelpers:
    """辅助函数测试。"""

    def test_estimate_complexity_simple(self):
        """简单问题复杂度。"""
        score = _estimate_complexity("1+1=?")
        assert score < 0.6

    def test_estimate_complexity_complex(self):
        """复杂问题复杂度。"""
        score = _estimate_complexity("求积分并画图然后验证结果")
        assert score >= 0.3

    def test_count_math_symbols(self):
        """数学符号计数。"""
        count = _count_math_symbols("∫∑∂√±∞")
        assert count == 6
        count = _count_math_symbols("hello world")
        assert count == 0

    def test_extract_problem_type(self):
        """问题类型提取。"""
        assert _extract_problem_type("求不定积分") == "积分"
        assert _extract_problem_type("求导数") == "微分"
        assert _extract_problem_type("证明题") == "证明"

    def test_should_plan_with_learning_keywords(self):
        """含学习关键词触发规划。"""
        planner = TaskPlanner(MagicMock(), ToolRegistry())
        assert planner.should_plan("第一步求导，然后求极值，最后验证")

    def test_should_plan_short_concept_question(self):
        """短概念问题不规划。"""
        planner = TaskPlanner(MagicMock(), ToolRegistry())
        assert not planner.should_plan("导数定义")


# ============================================================================
# TestTaskDataModel
# ============================================================================

class TestTaskDataModel:
    """Task 数据模型测试。"""

    def test_task_creation(self):
        """Task 创建。"""
        task = Task(id="t1", name="测试任务", description="测试")
        assert task.id == "t1"
        assert task.status == TaskStatus.PENDING
        assert task.priority == TaskPriority.NORMAL
        assert task.dependencies == []
        assert task.retry_count == 0

    def test_task_can_retry(self):
        """重试判断。"""
        task = Task(id="t1", name="测试", description="测试", max_retries=2)
        assert task.can_retry
        task.retry_count = 2
        assert not task.can_retry

    def test_task_elapsed_ms(self):
        """耗时计算。"""
        task = Task(id="t1", name="测试", description="测试")
        assert task.elapsed_ms == 0
        task.started_at = time.time() - 1
        assert task.elapsed_ms >= 900

    def test_task_to_dict(self):
        """序列化。"""
        task = Task(id="t1", name="测试", description="测试", tool_name="math_solver")
        data = task.to_dict()
        assert data["id"] == "t1"
        assert data["status"] == "pending"

    def test_task_from_dict(self):
        """反序列化。"""
        data = {"id": "t1", "name": "测试", "description": "测试",
                "tool_name": "math_solver", "status": "completed", "priority": "high"}
        task = Task.from_dict(data)
        assert task.id == "t1"
        assert task.status == TaskStatus.COMPLETED
        assert task.priority == TaskPriority.HIGH


# ============================================================================
# TestPlanningContext
# ============================================================================

class TestPlanningContext:
    """PlanningContext 测试。"""

    def test_to_prompt_context(self):
        """Prompt上下文生成。"""
        ctx = PlanningContext(
            user_level="高中",
            weak_points=["不定积分", "定积分"],
            preferred_style="详细",
        )
        result = ctx.to_prompt_context()
        assert "高中" in result
        assert "不定积分" in result
        assert "详细" in result

    def test_empty_context(self):
        """空上下文（所有字段为空的上下文）。"""
        ctx = PlanningContext(user_level="", preferred_style="")
        result = ctx.to_prompt_context()
        assert "无特殊上下文" in result


# ============================================================================
# TestPlannerConfig
# ============================================================================

class TestPlannerConfig:
    """PlannerConfig 测试。"""

    def test_default_config(self):
        """默认配置。"""
        config = PlannerConfig()
        assert config.max_tasks_per_plan == 10
        assert config.max_depth == 8
        assert config.enable_parallelism is True
        assert config.cache_enabled is True

    def test_custom_config(self):
        """自定义配置。"""
        config = PlannerConfig(
            max_tasks_per_plan=20,
            complexity_threshold=0.8,
        )
        assert config.max_tasks_per_plan == 20
        assert config.complexity_threshold == 0.8


# ============================================================================
# 性能基准测试
# ============================================================================

class TestPerformance:
    """性能基准测试。"""

    def test_should_plan_speed(self, mock_llm, sample_registry):
        """should_plan() < 5ms。"""
        planner = TaskPlanner(llm=mock_llm, registry=sample_registry)
        start = time.perf_counter()
        for _ in range(100):
            planner.should_plan("求积分并画图然后验证")
        elapsed = (time.perf_counter() - start) * 1000 / 100
        assert elapsed < 5, f"should_plan平均耗时{elapsed:.2f}ms超过5ms"

    def test_dag_topological_sort_speed(self):
        """DAG拓扑排序 < 10ms (20节点)。"""
        dag = TaskDAG()
        for i in range(20):
            dag.add_node(f"t{i}", Task(id=f"t{i}", name=f"T{i}", description=f"T{i}"))
        for i in range(19):
            dag.add_edge(f"t{i}", f"t{i+1}")
        for i in range(0, 18, 2):
            dag.add_edge(f"t{i}", f"t{i+2}")
        start = time.perf_counter()
        topo = dag.topological_sort()
        elapsed = (time.perf_counter() - start) * 1000
        assert len(topo) == 20
        assert elapsed < 10, f"拓扑排序耗时{elapsed:.1f}ms超过10ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])