"""真实系统API调用测试 — 验证RAG日志是否在终端显示"""
import urllib.request
import json
import time

BASE = "http://localhost:8000"

def api(method, path, data=None, token=None):
    body = json.dumps(data).encode() if data else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{BASE}{path}", data=body, headers=headers, method=method)
    resp = urllib.request.urlopen(req, timeout=60)
    return json.loads(resp.read())

print("=" * 50)
print("  真实系统 API 测试")
print("=" * 50)

# 注册
try:
    r = api("POST", "/api/auth/register", {"username": "ragtest2", "password": "test123456"})
    print(f"注册: {r.get('success', r)}")
except:
    pass

# 登录
r = api("POST", "/api/auth/login", {"username": "ragtest2", "password": "test123456"})
token = r.get("data", {}).get("access_token", "")
print(f"登录: {'OK' if token else 'FAIL'}")

# 调用推荐API (这是真实请求，会触发完整RAG链路)
print("\n--- 发送推荐请求: 给我出两道导数题 ---")
t0 = time.time()
r = api("POST", "/api/recommend/questions",
       {"target_category": "导数", "count": 2, "context": "practice"},
       token=token)
elapsed = time.time() - t0

print(f"\n推荐结果 ({elapsed:.1f}s):")
print(f"  success: {r.get('success')}")
data = r.get("data", {})
questions = data.get("questions", [])
meta = data.get("meta", {})
print(f"  题目数:   {len(questions)}")
print(f"  SQL检索:  {meta.get('sql_result_count')} 道")
print(f"  向量搜索: {meta.get('vector_result_count')} 道")
print(f"  检索方法: {meta.get('retrieval_method')}")
for i, q in enumerate(questions):
    print(f"\n  --- 第{i+1}题 ---")
    print(f"      ID:     {q.get('id')}")
    print(f"      来源:   {q.get('source')}")
    print(f"      难度:   {q.get('difficulty')}")
ai = data.get("ai_analysis", {})
if ai:
    print(f"  AI分析: {list(ai.keys())}")
    if ai.get("recommendation_reason"):
        print(f"  推荐理由: {ai['recommendation_reason'][:100]}...")

print("\n" + "=" * 50)
print("  请查看运行 python main.py 的终端窗口中的日志输出!")
print("=" * 50)
