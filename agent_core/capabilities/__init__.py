"""第一版教学任务 Capability。

Capability 只描述一次教学任务的边界；具体推理由既有 MathAgent 策略完成。
"""

from agent_core.capabilities.base import Capability, CapabilityManifest
from agent_core.capabilities.diagnose_error import DiagnoseErrorCapability
from agent_core.capabilities.solve import SolveCapability

__all__ = [
    "Capability",
    "CapabilityManifest",
    "DiagnoseErrorCapability",
    "SolveCapability",
]
