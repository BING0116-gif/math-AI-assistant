"""T02 端到端验证：做错一题 → 错题自动进入复习排期 → 出现在 /learning/reviews/due。"""
import json
import urllib.request

BASE = "http://localhost:8000"


def call(method, path, token=None, body=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(req, data=data) as resp:
        return json.loads(resp.read())


# 1. 登录
r = call("POST", "/api/auth/login", body={"username": "phaseb_student", "password": "PhaseB#2026"})
token = (r.get("data") or r).get("access_token") or (r.get("data") or r).get("token")
print("login ok:", bool(token))


def _data(r):
    """learning API 部分端点返回裸 payload，部分返回 {code,data}，做兼容。"""
    return r.get("data") if isinstance(r, dict) and "data" in r and "items" not in r else r


# 2. due 快照（练习前）
before = _data(call("GET", "/api/learning/reviews/due?include_upcoming=true", token=token))
print("due items before practice:", len(before["items"]))

# 3. 找 course/version 与知识点
from_db = call("GET", "/api/practice/options", token=token)
opts = _data(from_db)
course_id = opts["course_id"] or opts["courses"][0]["id"]
version_id = opts["version_id"] or opts["courses"][0]["default_version_id"]
print("course:", course_id, "version:", version_id)
kps = [k["code"] for k in opts.get("knowledge_points", [])][:3]
print("kp candidates:", kps)

# 4. 建会话（5 题）
s = call("POST", "/api/practice/sessions", token=token, body={
    "course_id": course_id, "version_id": version_id,
    "knowledge_point_codes": kps[:1] if kps else [],
    "question_count": 5, "idempotency_key": "t02-e2e-session-0005",
})
sid = _data(s)["session_id"]
print("session:", sid)
call("POST", f"/api/practice/sessions/{sid}/start", token=token)
qs = _data(call("GET", f"/api/practice/sessions/{sid}", token=token))["questions"]
print("questions:", [q["question_id"] for q in qs])

# 5. 第一题故意答错
q1 = qs[0]
wrong = "T02-e2e-故意答错-$$无意义答案$$"
a = call("POST", f"/api/practice/sessions/{sid}/attempts", token=token, body={
    "question_id": q1["question_id"], "answer": wrong,
    "idempotency_key": "t02-e2e-attempt-0003",
})
print("attempt1 correct:", _data(a)["correct"], "(应为 False)")

# 6. 练习后查 due：错题应带 source=error_item 出现
after = call("GET", "/api/learning/reviews/due?include_upcoming=true", token=token)
items = _data(after)["items"]
err_items = [i for i in items if i.get("source") == "error_item"]
print("due items after practice:", len(items), "| error_item sourced:", len(err_items))
for i in err_items:
    print("  ->", json.dumps(i, ensure_ascii=False)[:220])

ok = len(err_items) >= 1 and not _data(a)["correct"]
print("E2E RESULT:", "PASS" if ok else "FAIL")
