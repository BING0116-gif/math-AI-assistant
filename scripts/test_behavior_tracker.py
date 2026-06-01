import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.behavior_tracker import LearningBehaviorTracker

t = LearningBehaviorTracker()

tests = [
    ("求极限 lim(x->0) sin(x)/x", "problem_solving", "极限"),
    ("什么是导数的几何意义", "concept_inquiry", "导数"),
    ("这题做错了，求积分 x^2 dx", "error_analysis", "积分"),
    ("帮我复习一下三角函数公式", "review", "三角函数"),
    ("你好今天天气不错", "casual_chat", ""),
    ("解方程 x^2-5x+6=0", "problem_solving", "代数"),
    ("求 ∫ e^x cos(x) dx 用分部积分法", "problem_solving", "积分"),
]

print("=" * 60)
print("BehaviorTracker Intent + Category Classification Test")
print("=" * 60)
for text, expected_intent, expected_cat in tests:
    r = t.track("test_user", text, source="test")
    intent_ok = r["event_type"] == expected_intent
    cat_ok = r["category"] == expected_cat
    status = "PASS" if (intent_ok and cat_ok) else "PARTIAL" if (intent_ok or cat_ok) else "FAIL"
    print(f"  [{status}] intent={r['event_type']:18s} (expect {expected_intent:18s}) | "
          f"cat={r['category']:6s} (expect {expected_cat:6s}) | sub={r['sub_categories']}")
print("=" * 60)
print("Done")