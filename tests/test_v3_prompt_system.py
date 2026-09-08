"""
test_v3_prompt_system.py — v3.0 四层架构 Prompt 系统完整验证测试。

测试目标：
1. SystemPromptManager v3.0 四层架构正确生成
2. TaskClassifier T1-T5 意图分类准确性
3. 动态参数映射正确性
4. ReActPromptTemplate 精简版指令无冲突
5. agent.py 集成正确性（模拟初始化）
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prompts.system_prompt import SystemPromptManager, SystemPromptVersion
from prompts.react_prompt import ReActPromptTemplate
from prompts.dynamic_params import (
    TaskClassifier,
    ClassificationResult,
    TaskType,
    LLMParams,
    get_params_for_task,
    get_classifier,
    TASK_PARAMS_MAP,
)

SEPARATOR = "=" * 60
PASS = "[PASS]"
FAIL = "[FAIL]"


def test_system_prompt_manager_v3():
    """测试 v3.0 SystemPromptManager 四层架构。"""
    print(f"\n{SEPARATOR}")
    print("测试 1: SystemPromptManager v3.0 四层架构")
    print(SEPARATOR)

    manager = SystemPromptManager()

    # 测试 LAYER0 元指令层存在
    prompt = manager.get_prompt()
    assert "LAYER0" not in prompt  # 代码中的常量名不应出现在最终输出
    assert "贸大数助" in prompt, "角色定义未出现"
    assert "禁止用语" in prompt, "角色铁律未出现"
    assert "安全边界" in prompt, "安全边界未出现"
    print(f"{PASS} LAYER0 元指令层正确生成")

    # 测试 LAYER1 路由层存在
    assert "任务路由" in prompt, "任务路由层未出现"
    assert "T1-知识点问询" in prompt, "T1路由规则未出现"
    assert "T2-快速答案" in prompt, "T2路由规则未出现"
    assert "T3-概念讲解" in prompt, "T3路由规则未出现"
    assert "T4-图片+提问" in prompt, "T4路由规则未出现"
    assert "T5-完整解题" in prompt, "T5路由规则未出现"
    print(f"{PASS} LAYER1 任务路由层正确生成（T1-T5全部存在）")

    # 测试 LAYER2 场景模板存在
    assert "模板A：知识点简洁型" in prompt, "T1模板未出现"
    assert "模板B：快速答案型" in prompt, "T2模板未出现"
    assert "模板C：概念教学型" in prompt, "T3模板未出现"
    assert "模板D：多模态适配型" in prompt, "T4模板未出现"
    assert "模板E：详细解题型" in prompt, "T5模板未出现"
    print(f"{PASS} LAYER2 场景模板层正确生成（5个模板全部存在）")

    # 测试排版规范存在
    assert "排版规范" in prompt, "排版规范未出现"
    assert "$...$" in prompt, "LaTeX规范未出现"
    print(f"{PASS} LAYER3 排版规范正确生成")

    # 测试工具注入
    test_tools = "可用工具：calculator、search_knowledge、vision_tool"
    manager.update_tools(test_tools)
    prompt_with_tools = manager.get_prompt()
    assert "calculator" in prompt_with_tools, "工具描述未注入"
    assert "search_knowledge" in prompt_with_tools, "工具描述未注入"
    print(f"{PASS} 工具描述动态注入正确")

    # 测试 ReAct 指令注入
    manager.update_react_instruction("【精简ReAct指令 - 测试】")
    prompt_with_react = manager.get_prompt()
    assert "精简ReAct指令 - 测试" in prompt_with_react, "ReAct指令未注入"
    print(f"{PASS} ReAct指令动态注入正确")

    # 测试场景化 Prompt
    t1_prompt = manager.get_prompt_for_task_type("T1")
    assert "模板A：知识点简洁型" in t1_prompt, "T1场景模板缺失"
    assert "示例" not in t1_prompt or t1_prompt.count("模板") < 3, "T1场景应只包含T1模板"
    assert "calculator" not in t1_prompt, "T1场景不应包含工具描述"

    t2_prompt = manager.get_prompt_for_task_type("T2")
    assert "模板B：快速答案型" in t2_prompt, "T2场景模板缺失"

    t5_prompt = manager.get_prompt_for_task_type("T5")
    assert "模板E：详细解题型" in t5_prompt, "T5场景模板缺失"
    assert "calculator" in t5_prompt, "T5场景应包含工具描述"
    print(f"{PASS} 场景化 Prompt (T1/T2/T5) 正确生成")

    # 测试版本管理
    assert manager.version.startswith("v3.0"), f"版本号格式错误: {manager.version}"
    assert len(manager.tool_hash) > 0, "工具哈希应为非空字符串"
    print(f"{PASS} 版本管理正确 (version={manager.version})")

    print(f"\n{PASS} 测试 1 全部通过: SystemPromptManager v3.0 四层架构正确\n")
    return True


def test_task_classifier():
    """测试 TaskClassifier T1-T5 意图分类准确性。"""
    print(f"\n{SEPARATOR}")
    print("测试 2: TaskClassifier 意图分类准确性")
    print(SEPARATOR)

    classifier = get_classifier()

    # T1 - 知识点查询
    test_cases_t1 = [
        "这道题考的是什么知识点？",
        "这道题属于哪章的内容？",
        "这个题涉及什么概念？",
        "这考的是什么？",
        "这个涉及的考点是什么？",
    ]
    for case in test_cases_t1:
        result = classifier.classify(case)
        assert result.task_type == TaskType.KNOWLEDGE_QUERY, (
            f"T1分类失败: '{case}' → {result.task_type.value} "
            f"(期望: knowledge), confidence={result.confidence}"
        )
    print(f"{PASS} T1知识点查询: 5/5 正确分类")

    # T2 - 快速答案
    test_cases_t2 = [
        "这道题选什么？",
        "答案是多少？",
        "对还是错？",
        "等于多少？",
        "哪个选项是正确的？",
        "结果是多少？",
    ]
    for case in test_cases_t2:
        result = classifier.classify(case)
        assert result.task_type == TaskType.QUICK_ANSWER, (
            f"T2分类失败: '{case}' → {result.task_type.value} "
            f"(期望: quick), confidence={result.confidence}"
        )
    print(f"{PASS} T2快速答案: 6/6 正确分类")

    # T3 - 概念讲解
    test_cases_t3 = [
        "什么是洛必达法则？",
        "怎么理解极限的定义？",
        "导数是什么意思？",
        "解释一下什么是积分中值定理",
    ]
    for case in test_cases_t3:
        result = classifier.classify(case)
        assert result.task_type == TaskType.CONCEPT_TEACHING, (
            f"T3分类失败: '{case}' → {result.task_type.value} "
            f"(期望: concept), confidence={result.confidence}"
        )
    print(f"{PASS} T3概念讲解: 4/4 正确分类")

    # T5 - 完整解题
    test_cases_t5 = [
        "帮我解一下这道题",
        "求∫x²dx的详细过程",
        "帮我写出全部步骤",
        "帮我详细解一解",
        "求这个极限的详细推导过程",
        "计算f(x)=x³-3x在[0,2]上的最值",
        "证明这个定理",
    ]
    for case in test_cases_t5:
        result = classifier.classify(case)
        assert result.task_type == TaskType.FULL_SOLUTION, (
            f"T5分类失败: '{case}' → {result.task_type.value} "
            f"(期望: solution), confidence={result.confidence}"
        )
    print(f"{PASS} T5完整解题: 7/7 正确分类")

    # 测试默认回退
    result = classifier.classify("你好")
    assert result.task_type == TaskType.DEFAULT, "模糊输入应回退到DEFAULT"
    print(f"{PASS} 模糊输入正确回退到 DEFAULT (confidence={result.confidence:.2f})")

    # 测试置信度
    result = classifier.classify("这道题考什么知识点")
    assert result.confidence > 0.3, "高置信度T1输入应有较高分"
    print(f"{PASS} 置信度计算正常")

    # 测试缓存
    result1 = classifier.classify("这道题考什么知识点")
    result2 = classifier.classify("这道题考什么知识点")
    assert result1.task_type == result2.task_type, "缓存后的分类结果应一致"
    print(f"{PASS} 分类缓存正确")

    print(f"\n{PASS} 测试 2 全部通过: TaskClassifier 意图分类准确\n")
    return True


def test_dynamic_params():
    """测试动态参数调整模块。"""
    print(f"\n{SEPARATOR}")
    print("测试 3: 动态参数映射")
    print(SEPARATOR)

    # 测试参数映射表完整性
    assert len(TASK_PARAMS_MAP) == 5, f"规则意图参数表应只包含 T1-T5: {len(TASK_PARAMS_MAP)} 条目"
    print(f"{PASS} 参数映射表完整 ({len(TASK_PARAMS_MAP)} 条目)")

    # 测试各场景参数
    params_t1 = get_params_for_task(TaskType.KNOWLEDGE_QUERY)
    assert params_t1.temperature == 0.0, "T1 temperature 应为 0.0"
    assert params_t1.max_tokens == 800, "T1 max_tokens 应为 800"
    print(f"{PASS} T1参数正确: temp={params_t1.temperature}, max_tokens={params_t1.max_tokens}")

    params_t2 = get_params_for_task(TaskType.QUICK_ANSWER)
    assert params_t2.temperature == 0.0, "T2 temperature 应为 0.0"
    assert params_t2.max_tokens == 300, "T2 max_tokens 应为 300"
    print(f"{PASS} T2参数正确: temp={params_t2.temperature}, max_tokens={params_t2.max_tokens}")

    params_t3 = get_params_for_task(TaskType.CONCEPT_TEACHING)
    assert params_t3.temperature == 0.1, "T3 temperature 应为 0.1"
    assert params_t3.max_tokens == 2000, "T3 max_tokens 应为 2000"
    print(f"{PASS} T3参数正确: temp={params_t3.temperature}, max_tokens={params_t3.max_tokens}")

    params_t5 = get_params_for_task(TaskType.FULL_SOLUTION)
    assert params_t5.temperature == 0.0, "T5 temperature 应为 0.0"
    assert params_t5.max_tokens == 4096, "T5 max_tokens 应为 4096"
    print(f"{PASS} T5参数正确: temp={params_t5.temperature}, max_tokens={params_t5.max_tokens}")

    # 测试 to_dict 方法
    params_dict = params_t5.to_dict()
    assert "temperature" in params_dict, "to_dict 缺少 temperature"
    assert "max_tokens" in params_dict, "to_dict 缺少 max_tokens"
    print(f"{PASS} LLMParams.to_dict() 正确")

    # 测试 TaskType 属性
    assert TaskType.KNOWLEDGE_QUERY.max_output_length == 200, "T1 输出字数应为 200"
    assert TaskType.QUICK_ANSWER.max_output_length == 100, "T2 输出字数应为 100"
    assert not TaskType.KNOWLEDGE_QUERY.needs_tools, "T1 不应需要工具"
    assert TaskType.FULL_SOLUTION.needs_tools, "T5 应需要工具"
    print(f"{PASS} TaskType 属性正确 (max_length, needs_tools, needs_profile)")

    # 测试中文标签
    assert TaskType.KNOWLEDGE_QUERY.to_chinese() == "知识点查询"
    assert TaskType.QUICK_ANSWER.to_chinese() == "快速答案"
    print(f"{PASS} TaskType 中文标签正确")

    print(f"\n{PASS} 测试 3 全部通过: 动态参数映射正确\n")
    return True


def test_react_prompt_template():
    """测试精简版 ReActPromptTemplate。"""
    print(f"\n{SEPARATOR}")
    print("测试 4: 精简版 ReActPromptTemplate")
    print(SEPARATOR)

    # 测试指令生成
    instruction = ReActPromptTemplate.build_instruction(
        tool_names=["calculator", "search_knowledge"]
    )

    # v2.0精简版不应包含角色定义内容
    assert "贸大数助" not in instruction, "精简版不应包含角色定义"
    assert "禁止用语" not in instruction, "精简版不应包含教学风格"
    assert "高数" not in instruction, "精简版不应包含业务领域"
    print(f"{PASS} 精简版不包含角色定义/教学风格/业务领域")

    # 应包含工具调用格式
    assert "Action:" in instruction, "精简版应包含Action格式"
    assert "calculator" in instruction, "精简版应列出工具名"
    assert "search_knowledge" in instruction, "精简版应列出工具名"
    print(f"{PASS} 精简版包含工具调用格式和工具名")

    # 指令长度应控制在合理范围
    lines = instruction.strip().split("\n")
    assert len(lines) <= 20, f"精简版指令应≤20行，实际{len(lines)}行"
    print(f"{PASS} 精简版指令长度合理 ({len(lines)} 行)")

    # 测试空工具列表
    empty_instruction = ReActPromptTemplate.build_instruction(tool_names=[])
    assert "无专用工具" in empty_instruction, "空工具列表应显示提示"
    print(f"{PASS} 空工具列表正确处理")

    # 测试 parse_action
    action_text = "(ACTION): calculator [[{\"query\": \"1+1\"}]]"
    tool_name, params = ReActPromptTemplate.parse_action(action_text)
    assert tool_name == "calculator", f"工具名解析错误: {tool_name!r}"
    assert params.get("query") == "1+1", f"参数解析错误: {params}"
    print(f"{PASS} parse_action 解析正确")

    # 测试不完整的格式
    action_text2 = "(ACTION): search_knowledge"
    tool_name2, params2 = ReActPromptTemplate.parse_action(action_text2)
    assert tool_name2 == "search_knowledge", f"工具名解析错误: {tool_name2!r}"
    print(f"{PASS} parse_action 简单格式正确")

    print(f"\n{PASS} 测试 4 全部通过: 精简版 ReActPromptTemplate 正确\n")
    return True


def test_agent_integration_simulation():
    """模拟测试 agent.py 集成正确性。"""
    print(f"\n{SEPARATOR}")
    print("测试 5: agent.py 集成模拟测试")
    print(SEPARATOR)

    # 模拟 agent.py 中的完整流程
    classifier = get_classifier()

    # 模拟用户输入
    test_inputs = {
        "这道题考什么知识点": TaskType.KNOWLEDGE_QUERY,
        "答案是多少": TaskType.QUICK_ANSWER,
        "什么是洛必达法则": TaskType.CONCEPT_TEACHING,
        "帮我解这道题": TaskType.FULL_SOLUTION,
        "求极限lim(x→0)sinx/x": TaskType.FULL_SOLUTION,
    }

    for user_input, expected_type in test_inputs.items():
        # Step 1: 意图分类
        intent = classifier.classify(user_input)

        # Step 2: 获取参数
        params = get_params_for_task(intent.task_type)

        # Step 3: 获取场景化 Prompt
        manager = SystemPromptManager()
        if intent.task_type.needs_tools:
            manager.update_tools("可用工具：calculator, search_knowledge")
        scenario_prompt = manager.get_prompt_for_task_type(
            intent.task_type.name.split(".")[-1].upper() if hasattr(intent.task_type, 'name') else "T5"
        )

        # 验证
        assert intent.task_type == expected_type, (
            f"集成模拟分类错误: '{user_input}' → {intent.task_type.value}"
        )
        assert isinstance(params, LLMParams), "params 应为 LLMParams 类型"
        assert len(scenario_prompt) > 0, "场景化Prompt不应为空"

        print(
            f"  {PASS} '{user_input}' → "
            f"type={intent.task_type.value} "
            f"({intent.task_type.to_chinese()}), "
            f"tokens={params.max_tokens}, "
            f"prompt_len={len(scenario_prompt)}"
        )

    # 验证 T1/T2 轻量级 Prompt 更短
    manager = SystemPromptManager()
    t1_prompt = manager.get_prompt_for_task_type("T1")
    t5_prompt = manager.get_prompt_for_task_type("T5")
    assert len(t1_prompt) < len(t5_prompt), (
        f"T1 Prompt({len(t1_prompt)}字)应短于T5 Prompt({len(t5_prompt)}字)"
    )
    print(f"\n{PASS} T1轻量Prompt ({len(t1_prompt)}字) 显著短于 T5完整Prompt ({len(t5_prompt)}字)")

    print(f"\n{PASS} 测试 5 全部通过: agent.py 集成正确\n")
    return True


def run_all_tests():
    """运行全部测试。"""
    print("\n" + "=" * 60)
    print("  v3.0 四层架构 Prompt 系统 — 完整验证测试")
    print("=" * 60)

    results = []

    try:
        results.append(("SystemPromptManager v3.0", test_system_prompt_manager_v3()))
    except Exception as e:
        print(f"\n{FAIL} SystemPromptManager v3.0: {e}")
        import traceback
        traceback.print_exc()
        results.append(("SystemPromptManager v3.0", False))

    try:
        results.append(("TaskClassifier", test_task_classifier()))
    except Exception as e:
        print(f"\n{FAIL} TaskClassifier: {e}")
        import traceback
        traceback.print_exc()
        results.append(("TaskClassifier", False))

    try:
        results.append(("动态参数映射", test_dynamic_params()))
    except Exception as e:
        print(f"\n{FAIL} 动态参数映射: {e}")
        import traceback
        traceback.print_exc()
        results.append(("动态参数映射", False))

    try:
        results.append(("ReActPromptTemplate", test_react_prompt_template()))
    except Exception as e:
        print(f"\n{FAIL} ReActPromptTemplate: {e}")
        import traceback
        traceback.print_exc()
        results.append(("ReActPromptTemplate", False))

    try:
        results.append(("agent.py 集成", test_agent_integration_simulation()))
    except Exception as e:
        print(f"\n{FAIL} agent.py 集成: {e}")
        import traceback
        traceback.print_exc()
        results.append(("agent.py 集成", False))

    # 汇总结果
    print("\n" + "=" * 60)
    print("  测试结果汇总")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = PASS if passed else FAIL
        print(f"  {status}  {name}")
        if not passed:
            all_passed = False

    print(f"\n总计: {sum(1 for _, p in results if p)}/{len(results)} 通过")
    
    if all_passed:
        print(f"\n*** {PASS} 全部测试通过！v3.0 四层架构 Prompt 系统验证成功！\n")
    else:
        print(f"\n[WARN] {FAIL} 部分测试未通过，请检查上述错误信息。\n")

    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
