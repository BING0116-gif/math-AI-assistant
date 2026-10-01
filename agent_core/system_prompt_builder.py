"""Stateless system-prompt assembly for the math agent."""

from __future__ import annotations

from collections.abc import Sequence

from prompts.react_prompt import ReActPromptTemplate
from prompts.system_prompt import SystemPromptManager
from tools.base_tool import BaseTool
from tools.tool_description import ToolDescriptionGenerator


def build_system_prompt(
    tools: Sequence[BaseTool],
    style: str = "详细",
    skill_profile: str = "",
) -> str:
    """Build the layered system prompt from an explicit tool collection."""

    tool_list = list(tools)
    prompt_manager = SystemPromptManager()
    prompt_manager.update_tools(
        ToolDescriptionGenerator().generate_for_registry(tool_list)
    )
    prompt_manager.update_react_instruction(
        ReActPromptTemplate.build_instruction(
            tool_names=[tool.name for tool in tool_list]
        )
    )
    prompt_manager.update_style_instruction(style)
    if skill_profile:
        prompt_manager.update_skill_profile(skill_profile)
    return prompt_manager.get_prompt()


__all__ = ["build_system_prompt"]
