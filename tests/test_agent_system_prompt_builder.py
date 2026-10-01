from types import SimpleNamespace

from agent_core.agent import MathAgent
from agent_core.system_prompt_builder import build_system_prompt
from tools.ask_student_tool import AskStudentTool


def test_agent_prompt_method_matches_standalone_builder():
    tools = [AskStudentTool()]
    agent = MathAgent.__new__(MathAgent)
    agent._registry = SimpleNamespace(get_all_tools=lambda: tools)

    standalone = build_system_prompt(
        tools,
        style="简洁",
        skill_profile="【用户学习档案】测试画像",
    )
    legacy = agent._build_system_prompt(
        style="简洁",
        skill_profile="【用户学习档案】测试画像",
    )

    assert legacy == standalone
    assert "ask_student" in standalone
    assert "测试画像" in standalone


def test_prompt_builder_handles_explicit_empty_tool_list():
    prompt = build_system_prompt([])

    assert "当前无可用工具" in prompt
    assert "ask_student" not in prompt
