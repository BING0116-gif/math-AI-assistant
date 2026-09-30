"""临时脚本：提取 pytest 日志中的 warnings summary。用完即删。"""
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
path = sys.argv[1] if len(sys.argv) > 1 else ".test_health_regress1.log"
data = open(path, encoding="utf-8", errors="replace").read()
lines = data.splitlines()
start = None
for i, ln in enumerate(lines):
    if "warnings summary" in ln:
        start = i
        break
if start is None:
    print("(no warnings summary found)")
else:
    print("\n".join(lines[start : start + 120]))
