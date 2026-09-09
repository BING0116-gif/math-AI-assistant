"""MathVerifier 的 Agent 工具壳；数学逻辑位于 app.services.math_verifier。"""

from __future__ import annotations

import json
from typing import Any, Dict

from tools.base_tool import BaseTool, ToolCapability, ToolInput, ToolOutput


class MathVerifyTool(BaseTool):
    name = "math_verify"
    description = (
        "验证即将发布的关键数学结论。支持 equation、system、derivative、integral、"
        "limit、function_value、matrix、probability。必须传结构化 parameters；"
        "failed 时重新推导最多一次，inconclusive 时保留答案并明确提示未完全验证。"
    )
    version = "1.0.0"
    capabilities = [ToolCapability.SYMBOLIC_COMPUTATION, ToolCapability.VERIFICATION]

    def get_info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "capabilities": [cap.value for cap in self.capabilities],
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "待验证结论的简短说明，不要传推理过程"},
                    "parameters": {
                        "type": "object",
                        "description": "结构化验证请求，必须包含 type 与该类型所需字段",
                    },
                },
                "required": ["query", "parameters"],
            },
        }

    async def execute(self, input_data: ToolInput) -> ToolOutput:
        from app.services.math_verifier import get_math_verifier

        request = dict(input_data.parameters or {})
        # LangChainToolConverter 会把通用 parameters 字段放入 kwargs，因而这里
        # 同时兼容直接 ToolInvoker 调用与 Agent 的一层 parameters 包装。
        nested = request.get("request")
        if not isinstance(nested, dict):
            nested = request.get("parameters")
        if isinstance(nested, dict):
            request = nested
        result = get_math_verifier().verify(request)
        payload = result.to_dict()
        return ToolOutput(
            success=True,
            result=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            data=payload,
            tool_name=self.name,
            metadata={"verification_type": str(request.get("type") or "")[:40]},
        )
