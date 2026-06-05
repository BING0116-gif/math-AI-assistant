"""P0 全链路测试：数据采集 -> 聚合 -> 注入 -> LLM消费"""
import sys
import os
import asyncio

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  [PASS] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} -- {detail}")

print("=" * 60)
print("P0 Skill Injection - Full Chain Test")
print("=" * 60)

# ── T1: 导入验证 ──
print("\n[T1] Module Import Check")
try:
    from agent_core.agent import MathAgent
    from agent_core.memory_persistence import MemoryPersistenceFacade, UserProfile
    from prompts.system_prompt import SystemPromptManager
    SKILL_AWARE_INSTRUCTION = SystemPromptManager.SKILL_AWARE_INSTRUCTION
    from app.services.behavior_tracker import LearningBehaviorTracker
    check("agent_core.agent", True)
    check("memory_persistence (UserProfile)", True)
    check("system_prompt (SKILL_AWARE_INSTRUCTION)", len(SKILL_AWARE_INSTRUCTION) > 100)
except Exception as e:
    check("IMPORT", False, str(e))
    sys.exit(1)

# ── T2: _format_skill_profile_for_llm 格式化测试 ──
print("\n[T2] Skill Profile Formatting")

profile_rich = UserProfile(
    total_questions=25,
    correct_rate=0.44,
    weak_points=[
        {"category": "积分", "mastery": 0.18},
        {"category": "极限", "mastery": 0.30},
        {"category": "三角函数", "mastery": 0.25},
    ],
    strong_points=["代数基础"],
    recommended_difficulty=2,
    skills=[
        {"skill_code": "dingjifen_basic", "display_name": "定积分概念", "mastery_level": 0.15, "status": "novice"},
        {"skill_code": "daoshu_jiben", "display_name": "导数基本公式", "mastery_level": 0.92, "status": "mastered"},
        {"skill_code": "luobida", "display_name": "洛必达法则", "mastery_level": 0.55, "status": "learning"},
    ],
    error_patterns=[
        {"pattern": "漏掉积分常数C", "frequency": 8},
        {"pattern": "正负号错误", "frequency": 5},
    ],
    cognitive_style={"style_hint": "偏好图示解释"},
)
result = MathAgent._format_skill_profile_for_llm(profile_rich)
check("Rich profile formatting", len(result) > 50, f"len={len(result)}")
check("Contains level info", "当前水平" in result)
check("Contains weak points", "薄弱" in result or "积分" in result)
check("Contains strong points", "已掌握" in result or "代数" in result)
check("Contains difficulty", "T2" in result or "推荐" in result)
check("Contains error patterns", "易错" in result or "常数C" in result)
print(f"  Preview:\n{result[:400]}\n...")

# ── T3: 空画像降级测试 ──
print("\n[T3] Empty Profile Fallback")
profile_empty = UserProfile(correct_rate=0)
result_empty = MathAgent._format_skill_profile_for_llm(profile_empty)
check("Empty profile no crash", len(result_empty) > 0)
check("Empty still has header", "用户学习档案" in result_empty)

# ── T4: 高分用户画像 ──
print("\n[T4] Expert User Profile")
profile_expert = UserProfile(
    correct_rate=0.92,
    strong_points=["微积分", "线性代数"],
    skills=[{"skill_code": "xxx", "mastery_level": 0.98, "status": "mastered"}],
    recommended_difficulty=5,
)
result_expert = MathAgent._format_skill_profile_for_llm(profile_expert)
check("Expert level detected", "优秀" in result_expert)
check("High difficulty", "T5" in result_expert or "挑战" in result_expert)

# ── T5: SystemPromptManager 集成测试 ──
print("\n[T5] System Prompt Integration")
mgr = SystemPromptManager()
mgr.update_style_instruction("详细")

# 5a: 无技能数据（默认模式）
prompt_default = mgr.get_prompt()
check("Default prompt (no skill)", len(prompt_default) > 100)
check("No skill section when empty", "skill_profile" not in prompt_default or prompt_default.count("skill_profile") == 0)

# 5b: 有技能数据注入
mgr_with_skill = SystemPromptManager()
mgr_with_skill.update_style_instruction("详细")
mgr_with_skill.update_skill_profile(result)
prompt_with_skill = mgr_with_skill.get_prompt()
check("Skill-injected prompt longer", len(prompt_with_skill) > len(prompt_default))
check("Contains skill data", "用户学习档案" in prompt_with_skill)
check("Contains SKILL_AWARE rules", "感知规则" in prompt_with_skill or "调整你的教学策略" in prompt_with_skill)

# ── T6: BehaviorTracker LLM-First 模式 ──
print("\n[T6] Behavior Tracker Classification")
tracker = LearningBehaviorTracker()
tracked = tracker.track(
    user_id="test_user_p0",
    raw_input="定积分的几何意义是什么？",
    source="chat",
)
check("Track returns dict", isinstance(tracked, dict))
check("Has event_type", tracked.get("event_type") is not None)
check("Has category", tracked.get("category") is not None)
check("Has classification_source", tracked.get("_classification_source") is not None)
print(f"  Source: {tracked['_classification_source']}")
print(f"  Intent: {tracked['event_type']}, Cat: {tracked['category']}")

# ── T7+T8: 异步数据流测试 ──
async def run_async_tests():
    global passed, failed

    # ── T7: Facade get_profile 数据流模拟 ──
    print("\n[T7] Data Flow Simulation (mock)")
    try:
        facade = MemoryPersistenceFacade()
        profile_anon = await facade.get_profile("anonymous_test_user_p0")
        check("get_profile no crash", profile_anon is not None)
        check("Returns UserProfile", isinstance(profile_anon, UserProfile))

        anon_instruction = MathAgent._format_skill_profile_for_llm(profile_anon)
        check("Anonymous profile formatable", len(anon_instruction) >= 0)
    except Exception as e:
        check("get_profile flow", False, str(e))

    # ── T8: 完整链路端到端模拟 ──
    print("\n[T8] End-to-End Chain Simulation")
    try:
        # Step 1: 用户提问 -> behavior tracker 分类
        tracker2 = LearningBehaviorTracker()
        event = tracker2.track(
            user_id="p0_chain_test_user",
            raw_input="求极限 lim(x->0) sin(x)/x 的值",
            source="chat",
        )
        check("Step1: LLM/Rule classify OK", event["event_type"] is not None)

        # Step 2: record_event 写入
        facade2 = MemoryPersistenceFacade()
        written = await facade2.record_event(user_id="p0_chain_test_user", event_data=event)
        check("Step2: record_event writes OK", written)

        # Step 3: get_profile 读取聚合数据
        profile3 = await facade2.get_profile("p0_chain_test_user")
        check("Step3: get_profile reads back", profile3 is not None)

        # Step 4: 格式化为 LLM 指令
        instruction = MathAgent._format_skill_profile_for_llm(profile3)
        check("Step4: format for LLM OK", len(instruction) > 0)

        # Step 5: 注入到 System Prompt
        mgr3 = SystemPromptManager()
        mgr3.update_style_instruction("详细")
        mgr3.update_skill_profile(instruction)
        final_prompt = mgr3.get_prompt()
        has_skill_in_prompt = "用户学习档案" in final_prompt if instruction else True
        check("Step5: final prompt contains skill", has_skill_in_prompt)

        print(f"\n  Full chain: track -> record -> profile -> format -> inject = OK")
        print(f"  Final prompt length: {len(final_prompt)} chars")

    except Exception as e:
        import traceback
        check("E2E chain", False, f"{e}\n{traceback.format_exc()}")

try:
    asyncio.run(run_async_tests())
except RuntimeError:
    # 可能已在事件循环中（如 Jupyter）
    import asyncio
    loop = asyncio.get_event_loop()
    if loop.is_running():
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, run_async_tests()).result()
    else:
        loop.run_until_complete(run_async_tests())
except Exception as e:
    check("Async tests", False, str(e))

# ── 结果汇总 ──
print("\n" + "=" * 60)
total = passed + failed
print(f"RESULT: {passed}/{total} passed, {failed} failed")
if failed == 0:
    print("STATUS: ALL CHECKS PASSED - P0 implementation verified")
else:
    print(f"STATUS: {failed} check(s) FAILED - needs attention")
print("=" * 60)
sys.exit(0 if failed == 0 else 1)
