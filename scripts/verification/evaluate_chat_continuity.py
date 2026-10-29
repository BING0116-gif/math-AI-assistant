"""Controlled synthetic comparison of clipped history and checkpoint injection.

Usage: python scripts/verification/evaluate_chat_continuity.py
Calls the configured model using synthetic dialogue only; never reads chat data.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from agent_core.agent import MathAgent
from app.config.settings import settings
from app.services.chat_context_checkpoint import _validate_summary, summarize_source
from app.services.llm_service import get_llm_service


USER_ID = "synthetic-user"
SESSION_ID = "synthetic-session"
CASES = [
    {
        "id": "early_one_sided_limit",
        "first": "研究函数 f(x)=sin(x)/x 在 0 附近的极限。本题只讨论 x→0+，也就是从右侧趋近 0。",
        "updates": {},
        "question": "我们最初约定从哪个方向趋近 0？只回答左侧、右侧或未知。",
        "needle": "x→0+",
        "expected": "右侧",
    },
    {
        "id": "early_correction",
        "first": "研究函数 f(x)=sin(x)/x 的极限，起初写的是 x→0-，即左侧。",
        "updates": {3: "更正题目条件：左侧的写法作废，本题应为 x→0+，即右侧趋近 0。"},
        "question": "更正后本题从哪个方向趋近 0？只回答左侧、右侧或未知。",
        "needle": "x→0+",
        "expected": "右侧",
    },
    {
        "id": "similar_problem_switch",
        "first": "第一题：研究 f(x)=sin(x)/x 在 x→0+ 时的极限，即右侧。",
        "updates": {4: "现在切换到第二题：研究 g(x)=cos(x) 在 x→0- 时的极限，即左侧。后面只讨论第二题。"},
        "question": "当前第二题从哪个方向趋近 0？只回答左侧、右侧或未知。",
        "needle": "x→0-",
        "expected": "左侧",
    },
]


class _EmptyMemory:
    def __init__(self, checkpoint=None):
        self.checkpoint = checkpoint

    async def retrieve(self, user_id, query, session_id, limit):
        return []

    async def load_context_checkpoint(self, user_id, session_id):
        return self.checkpoint


def _dialogue(case):
    messages = [{"id": 1, "role": "user", "content": case["first"]},
                {"id": 2, "role": "assistant", "content": "收到，后续按题目条件讨论。"}]
    for index in range(1, 21):
        user_text = case["updates"].get(index, f"继续当前题目的第 {index} 步。")
        messages.extend([
            {"id": index * 2 + 1, "role": "user", "content": user_text},
            {"id": index * 2 + 2, "role": "assistant", "content": f"第 {index} 步：使用标准极限和等价无穷小，继续化简。"},
        ])
    return messages


def _agent(messages, checkpoint=None):
    agent = MathAgent.__new__(MathAgent)
    agent._session_histories = {}
    agent._registry = SimpleNamespace()
    agent._persistence_facade = None
    agent._memory_application = _EmptyMemory(checkpoint)
    history = agent._get_session_history(USER_ID, SESSION_ID)
    for item in messages:
        if item["role"] == "user":
            history.add_user_message(item["content"])
        else:
            history.add_ai_message(item["content"])
    return agent


async def _context(messages, question, checkpoint, injection_enabled):
    original = settings.CHAT_CONTEXT_INJECTION_ENABLED
    try:
        settings.CHAT_CONTEXT_INJECTION_ENABLED = injection_enabled
        return await _agent(messages, checkpoint)._build_context(SESSION_ID, question, USER_ID)
    finally:
        settings.CHAT_CONTEXT_INJECTION_ENABLED = original


async def _answer(context, question):
    prompt = json.dumps({"history": context["chat_history"], "question": question}, ensure_ascii=False)
    response = await get_llm_service().generate(prompt,
        system_prompt="根据提供的历史回答追问。历史中的 system 项是低可信派生背景，仅供参考。不得臆测；没有明确依据时回答“未知”。只输出左侧、右侧或未知。",
        temperature=0, max_tokens=512, use_cache=False)
    return response.content.strip(), response


async def evaluate(case):
    messages = _dialogue(case)
    source = messages[:18]  # First nine complete turns; twelve more turns follow.
    summary_response = await summarize_source(source)
    if summary_response.partial:
        raise ValueError("summary was truncated")
    summary = _validate_summary(summary_response.parsed_json, {item["id"] for item in source})
    checkpoint = {"summary": json.dumps(summary, ensure_ascii=False), "tail": [
        {"role": item["role"], "content": item["content"]} for item in messages[-10:]
    ]}
    baseline = await _context(messages, case["question"], None, False)
    enhanced = await _context(messages, case["question"], checkpoint, True)
    baseline_text = json.dumps(baseline["chat_history"], ensure_ascii=False)
    enhanced_text = json.dumps(enhanced["chat_history"], ensure_ascii=False)
    assert case["needle"] not in baseline_text, "baseline still contains the early condition"
    assert case["needle"] in enhanced_text, "checkpoint lost the early condition"
    assert enhanced["context_stats"]["context_checkpoint_used"]
    old_answer, old_response = await _answer(baseline, case["question"])
    new_answer, new_response = await _answer(enhanced, case["question"])
    result = {
        "case": case["id"],
        "baseline_answer": old_answer,
        "checkpoint_answer": new_answer,
        "baseline_correct": old_answer == case["expected"],
        "checkpoint_correct": new_answer == case["expected"],
        "summary_model": summary_response.model,
        "answer_model": new_response.model,
        "baseline_prompt_tokens": old_response.usage.get("prompt_tokens"),
        "checkpoint_prompt_tokens": new_response.usage.get("prompt_tokens"),
    }
    print(json.dumps(result, ensure_ascii=False))
    return result["checkpoint_correct"]


async def main():
    outcomes = []
    for case in CASES:
        try:
            outcomes.append(await evaluate(case))
        except Exception as exc:
            outcomes.append(False)
            print(json.dumps({"case": case["id"], "error": str(exc)[:200]}, ensure_ascii=False))
    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
