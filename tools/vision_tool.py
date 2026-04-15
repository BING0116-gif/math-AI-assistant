"""
通义千问 VL（视觉-语言）多模态识别工具。
截图直接发给 Qwen-VL，由模型端到端理解图片内容（文字+公式+图形），
返回结构化的「题目描述 + LaTeX 公式 + 空间关系」。
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

import requests

# API 配置（与现有 DashScope key 复用）
_DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _load_api_key(file_path: str = ".env") -> Optional[str]:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if api_key:
        return api_key
    if not os.path.exists(file_path):
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == "DASHSCOPE_API_KEY":
                return v.strip()
    return None


def _img_to_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _data_url_to_base64(data_url: str) -> str:
    """data:image/png;base64,XXXX → base64 字符串"""
    if ";base64," in data_url:
        return data_url.split(";base64,", 1)[1]
    raise ValueError(f"非法的 data URL: {data_url[:30]}...")


# VL 模型名称（按能力从高到低，可按需替换）
_VL_MODELS = [
    "qwen-vl-plus",   # 优先：数学理解强，支持流式
    "qwen-vl-max",    # 备选：更大规模
    "qwen2-vl-72b-instruct",  # 最新一代（若账号支持）
]


class VisionTool:
    """
    将截图直接发给 Qwen-VL，返回题目结构化描述。
    """

    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None):
        self.name = "vision_tool"
        self.description = (
            "多模态图片理解：截图直接发给 Qwen-VL，"
            "输出题目文字、LaTeX 公式、图形空间关系的结构化描述。"
        )
        self._api_key = api_key or _load_api_key(".env")
        self._model = model or _VL_MODELS[0]
        self._base_url = _DASHSCOPE_BASE

    def _post(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        stream: bool = False,
        **params,
    ) -> requests.Response:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            **params,
        }
        resp = requests.post(
            f"{self._base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        return resp

    def recognize(
        self,
        image_source: Union[str, Tuple[str, bytes]],
        user_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        将图片发给 VL 模型，获取题目结构化描述。

        Args:
            image_source:
                - str: 图片文件路径
                - (data_url_prefix, base64_bytes): Streamlit 粘贴过来的 data URL (tuple)
            user_prompt: 可选的自定义 prompt，默认用内置的「数学题目结构化」prompt
            model: 可选，指定 VL 模型名称

        Returns:
            {
                "success": bool,
                "llm_description": str,   # 发给解题 agent 的完整描述
                "raw_response": str,     # 模型原始输出（方便调试）
                "error": Optional[str],
                "model_used": str,       # 实际使用的模型名
            }
        """
        if not self._api_key:
            return {
                "success": False,
                "llm_description": "",
                "raw_response": "",
                "error": "未找到 DASHSCOPE_API_KEY，请在 .env 或环境变量中配置。",
                "model_used": "",
            }

        # ---------- 构造图片 content ----------
        try:
            if isinstance(image_source, tuple):
                # (data_url_prefix, base64_bytes) → data URL
                mime, b64 = image_source
                image_url = f"data:{mime};base64,{b64}"
            else:
                path = image_source
                if not os.path.exists(path):
                    return {
                        "success": False,
                        "llm_description": "",
                        "raw_response": "",
                        "error": f"图片文件不存在: {path}",
                        "model_used": "",
                    }
                # 本地文件 → base64 data URL
                mime = _guess_mime(path)
                b64 = _img_to_base64(path)
                image_url = f"data:{mime};base64,{b64}"
        except Exception as e:
            return {
                "success": False,
                "llm_description": "",
                "raw_response": "",
                "error": f"图片读取失败: {e}",
                "model_used": "",
            }

        # ---------- 构造 system + user ----------
        system = (
            "你是一个高数题目图像理解专家。用户会发来一张截图，"
            "请完成以下两步：\n\n"
            "【步骤 1：结构化提取】\n"
            "仔细阅读截图，提取题目中的所有信息，包括：\n"
            "- 题干文字（中文叙述）\n"
            "- 数学公式（用 LaTeX 表示，例如 $x^2+1$）\n"
            "- 几何图形描述（如坐标系、曲线、点、线段）\n"
            "- 选项内容（如 A/B/C/D）\n\n"
            "【步骤 2：输出格式】\n"
            "将提取结果按以下格式返回（不要加任何额外说明）：\n\n"
            "【题目】\n<题干文字>\n\n"
            "【公式】\n<LaTeX 公式，重要公式用独立段落 $$...$$>\n\n"
            "【图形描述】（如有）\n<坐标系、关键点位置等>\n\n"
            "【选项】（如有）\n<选项内容>\n\n"
            "【其他说明】（如有）\n<图注、补充条件等>\n"
        )

        user_content: List[Dict[str, Any]] = [
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
        if user_prompt:
            user_content.insert(0, {"type": "text", "text": user_prompt})

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

        # ---------- 逐模型尝试 ----------
        models_to_try = [model or self._model] + [
            m for m in _VL_MODELS if m != (model or self._model)
        ]
        last_error = ""
        for try_model in models_to_try:
            try:
                resp = self._post(
                    messages,
                    model=try_model,
                    temperature=0.3,
                    max_tokens=2048,
                )
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    last_error = f"API 返回无 choices: {data}"
                    continue
                msg = choices[0].get("message", {})
                raw = msg.get("content", "")
                return {
                    "success": True,
                    "llm_description": _build_llm_input(raw),
                    "raw_response": raw,
                    "error": None,
                    "model_used": try_model,
                }
            except Exception as e:
                last_error = str(e)
                continue

        return {
            "success": False,
            "llm_description": "",
            "raw_response": "",
            "error": f"所有 VL 模型调用均失败: {last_error}",
            "model_used": "",
        }

    def recognize_from_base64(
        self,
        mime: str,
        b64_data: str,
        user_prompt: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """直接从 base64 调用（Streamlit 粘贴图片走此路径）。"""
        return self.recognize(
            image_source=(mime, b64_data),
            user_prompt=user_prompt,
            model=model,
        )


def _guess_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(ext, "image/png")


def _build_llm_input(vl_output: str) -> str:
    """
    把 VL 的原始输出整理为发给解题 Agent 的用户输入。
    保留 LaTeX 原文，去掉多余解释。
    """
    # 去掉 VL 可能带的前缀说明（如 "以下是..."）
    lines = vl_output.strip().splitlines()
    cleaned = []
    skip_marker = False
    for line in lines:
        if line.strip().startswith("【题目】"):
            skip_marker = True
        if skip_marker:
            cleaned.append(line)
    result = "\n".join(cleaned) if cleaned else vl_output.strip()
    return (
        "请解答以下高等数学题目（图片识别结果）：\n\n"
        + result
        + "\n\n解答时尽量使用 LaTeX 公式（行内 $...$，独立段落 $$...$$）。"
    )