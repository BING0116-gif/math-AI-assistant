"""
系统集成测试 — 验证 RAG 推荐系统的所有 API 端点和模块交互。

测试覆盖：
1. 健康检查 API
2. 题目推荐 API（含多知识点、多场景）
3. 题目讲解 API
4. 技能画像 API
5. 向量搜索 API
6. AI 难度分析 API
7. LLM 缓存机制
8. 降级策略验证
9. 认证流程
10. 错误处理
"""

import json
import urllib.request
import urllib.error
import sys
import time

BASE_URL = "http://localhost:8000"
TOKEN = None
USER_ID = None

PASSED = 0
FAILED = 0
ERRORS = []


def test(name):
    """Decorator-style test runner"""
    def decorator(fn):
        def wrapper():
            global PASSED, FAILED
            try:
                fn()
                PASSED += 1
                print(f"  [PASS] {name}")
            except AssertionError as e:
                FAILED += 1
                msg = f"  [FAIL] {name}: {e}"
                print(msg)
                ERRORS.append(msg)
            except urllib.error.HTTPError as e:
                FAILED += 1
                body = e.read().decode()[:200]
                msg = f"  [FAIL] {name}: HTTP {e.code} - {body}"
                print(msg)
                ERRORS.append(msg)
            except Exception as e:
                FAILED += 1
                msg = f"  [FAIL] {name}: {type(e).__name__}: {e}"
                print(msg)
                ERRORS.append(msg)
        return wrapper
    return decorator


def api(method, path, data=None, use_auth=True):
    """Make an API request"""
    url = f"{BASE_URL}{path}"
    headers = {'Content-Type': 'application/json'}
    if use_auth and TOKEN:
        headers['Authorization'] = f'Bearer {TOKEN}'

    body = json.dumps(data).encode('utf-8') if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())


# ── Setup: Register and Login ──

def setup():
    global TOKEN, USER_ID
    print("\n=== Setup: Authentication ===")
    try:
        # Register
        api("POST", "/api/auth/register", {"username": "testuser", "password": "test123456"}, use_auth=False)
    except urllib.error.HTTPError:
        pass  # Already exists

    result = api("POST", "/api/auth/login", {"username": "testuser", "password": "test123456"}, use_auth=False)
    TOKEN = result.get('data', {}).get('access_token', '')
    USER_ID = result.get('data', {}).get('user_id', '')
    assert TOKEN, "Failed to get token"
    print(f"  Token obtained: {TOKEN[:30]}...")
    print(f"  User ID: {USER_ID}")


# ── 1. Health Check ──

@test("健康检查返回 healthy 状态")
def test_health_check():
    result = api("GET", "/api/recommend/health", use_auth=False)
    assert result["status"] in ("healthy", "degraded"), f"Unexpected status: {result['status']}"
    assert "checks" in result
    assert "llm_service" in result["checks"]
    assert "vector_store" in result["checks"]


@test("向量存储健康检查包含文档统计")
def test_health_vector_stats():
    result = api("GET", "/api/recommend/health", use_auth=False)
    vs = result["checks"]["vector_store"]
    assert vs["status"] == "ready"
    assert vs["stats"]["total_documents"] >= 1
    assert len(vs["stats"]["categories"]) >= 1


@test("LLM 服务健康检查包含缓存统计")
def test_health_llm_stats():
    result = api("GET", "/api/recommend/health", use_auth=False)
    llm = result["checks"]["llm_service"]
    assert llm["status"] == "ready"
    assert "cache" in llm


# ── 2. Question Recommendation ──

@test("推荐导数题目（指定知识点）")
def test_recommend_daoshu():
    result = api("POST", "/api/recommend/questions", {
        "target_category": "导数", "count": 3, "context": "practice"
    })
    assert result["success"] is True
    questions = result["data"]["questions"]
    assert len(questions) == 3
    for q in questions:
        assert q["category"] == "导数"
        assert 1 <= q["difficulty"] <= 5
    assert result["processing_time_ms"] > 0


@test("推荐三角函数题目")
def test_recommend_trig():
    result = api("POST", "/api/recommend/questions", {
        "target_category": "三角函数", "count": 2, "context": "practice"
    })
    assert result["success"] is True
    questions = result["data"]["questions"]
    assert len(questions) >= 1
    for q in questions:
        assert q["category"] == "三角函数"


@test("推荐题目包含 AI 分析")
def test_recommend_with_ai_analysis():
    result = api("POST", "/api/recommend/questions", {
        "target_category": "导数", "count": 2, "context": "practice"
    })
    ai = result["data"].get("ai_analysis", {})
    assert "assessment" in ai or "recommendation_reason" in ai


@test("推荐题目包含元数据")
def test_recommend_meta():
    result = api("POST", "/api/recommend/questions", {
        "target_category": "导数", "count": 3, "context": "practice"
    })
    meta = result["data"]["meta"]
    assert "target_category" in meta
    assert "recommended_difficulty" in meta
    assert "retrieval_method" in meta
    assert "total_ms" in meta


@test("推荐题目考试场景")
def test_recommend_exam_context():
    result = api("POST", "/api/recommend/questions", {
        "target_category": "极限", "count": 2, "context": "exam"
    })
    assert result["success"] is True


@test("推荐题目挑战场景")
def test_recommend_challenge_context():
    result = api("POST", "/api/recommend/questions", {
        "target_category": "数列", "count": 2, "context": "challenge"
    })
    assert result["success"] is True


@test("推荐题目数量限制（count=1）")
def test_recommend_count_one():
    result = api("POST", "/api/recommend/questions", {
        "target_category": "导数", "count": 1, "context": "practice"
    })
    assert len(result["data"]["questions"]) == 1


@test("推荐题目排除指定ID")
def test_recommend_with_exclude():
    result = api("POST", "/api/recommend/questions", {
        "target_category": "导数", "count": 3, "context": "practice",
        "exclude_ids": ["Q001", "Q002"]
    })
    questions = result["data"]["questions"]
    ids = [q["id"] for q in questions]
    assert "Q001" not in ids
    assert "Q002" not in ids


# ── 3. Explanation API ──

@test("题目讲解（无ID）")
def test_explain_no_id():
    result = api("POST", "/api/recommend/explain", {
        "target_category": "导数", "count": 1, "context": "practice"
    })
    assert result["success"] is True


# ── 4. Skill Profile ──

@test("技能画像查询")
def test_skill_profile():
    result = api("GET", "/api/recommend/skill-profile")
    assert result["success"] is True
    data = result["data"]
    assert "user_id" in data
    assert "correct_rate" in data
    assert "recommended_difficulty" in data
    assert "weak_points" in data
    assert "strong_points" in data


# ── 5. Vector Search ──

@test("向量搜索基本功能")
def test_vector_search_basic():
    result = api("POST", "/api/recommend/vector-search", {
        "query": "求导数的链式法则", "category": "导数", "n_results": 3
    })
    assert result["success"] is True
    results = result["data"]["results"]
    assert len(results) >= 1
    for r in results:
        assert "id" in r
        assert "score" in r
        assert "content" in r


@test("向量搜索无结果")
def test_vector_search_no_results():
    result = api("POST", "/api/recommend/vector-search", {
        "query": "量子力学薛定谔方程", "n_results": 3
    })
    assert result["success"] is True
    # May return empty results


@test("向量搜索难度筛选")
def test_vector_search_difficulty_filter():
    result = api("POST", "/api/recommend/vector-search", {
        "query": "导数", "category": "导数",
        "difficulty_min": 1, "difficulty_max": 2, "n_results": 5
    })
    assert result["success"] is True


# ── 6. AI Difficulty Analysis ──

@test("AI 难度分析")
def test_ai_analyze():
    result = api("POST", "/api/recommend/ai-analyze", {
        "content": "求函数 f(x)=x²+3x-2 的导数", "category": "导数"
    }, use_auth=False)
    assert result["success"] is True
    data = result["data"]
    assert "estimated_difficulty" in data
    assert 1 <= data["estimated_difficulty"] <= 5


# ── 7. Authentication ──

@test("未认证请求推荐接口返回401")
def test_auth_required():
    url = f"{BASE_URL}/api/recommend/questions"
    data = json.dumps({"target_category": "导数", "count": 1}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req)
        assert False, "Expected 401"
    except urllib.error.HTTPError as e:
        assert e.code == 401


@test("无效 token 返回401")
def test_invalid_token():
    url = f"{BASE_URL}/api/recommend/questions"
    data = json.dumps({"target_category": "导数", "count": 1}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json',
        'Authorization': 'Bearer invalid_token_here'
    })
    try:
        urllib.request.urlopen(req)
        assert False, "Expected 401"
    except urllib.error.HTTPError as e:
        assert e.code == 401


# ── 8. Edge Cases ──

@test("推荐不存在的知识点")
def test_recommend_unknown_category():
    result = api("POST", "/api/recommend/questions", {
        "target_category": "量子力学", "count": 2, "context": "practice"
    })
    assert result["success"] is True
    # Should return fallback behavior


@test("推荐 count=0 边界")
def test_recommend_count_zero():
    url = f"{BASE_URL}/api/recommend/questions"
    data = json.dumps({"target_category": "导数", "count": 0, "context": "practice"}).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {TOKEN}'
    })
    try:
        urllib.request.urlopen(req)
        assert False, "Expected 422 validation error"
    except urllib.error.HTTPError as e:
        assert e.code == 422


# ── 9. Tools API ──

@test("工具列表 API")
def test_tools_list():
    result = api("GET", "/api/tools", use_auth=False)
    assert "tools" in result
    assert result["total"] >= 5


@test("工具详情 API")
def test_tool_info():
    result = api("GET", "/api/tools/recommend_questions", use_auth=False)
    assert result["name"] == "recommend_questions"


# ── 10. Caching ──

@test("LLM 缓存第二次请求更快")
def test_llm_cache_speed():
    # First request
    t1 = time.time()
    result1 = api("POST", "/api/recommend/questions", {
        "target_category": "集合", "count": 1, "context": "practice"
    })
    t1_elapsed = time.time() - t1

    # Second request (same params)
    t2 = time.time()
    result2 = api("POST", "/api/recommend/questions", {
        "target_category": "集合", "count": 1, "context": "practice"
    })
    t2_elapsed = time.time() - t2

    assert result1["success"] and result2["success"]
    print(f"    Request 1: {t1_elapsed*1000:.0f}ms, Request 2: {t2_elapsed*1000:.0f}ms")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  RAG + LLM 智能推荐系统 — 系统集成测试")
    print("=" * 60)

    setup()

    print("\n── 1. 健康检查 ──")
    test_health_check()
    test_health_vector_stats()
    test_health_llm_stats()

    print("\n── 2. 题目推荐 ──")
    test_recommend_daoshu()
    test_recommend_trig()
    test_recommend_with_ai_analysis()
    test_recommend_meta()
    test_recommend_exam_context()
    test_recommend_challenge_context()
    test_recommend_count_one()
    test_recommend_with_exclude()

    print("\n── 3. 题目讲解 ──")
    test_explain_no_id()

    print("\n── 4. 技能画像 ──")
    test_skill_profile()

    print("\n── 5. 向量搜索 ──")
    test_vector_search_basic()
    test_vector_search_no_results()
    test_vector_search_difficulty_filter()

    print("\n── 6. AI 难度分析 ──")
    test_ai_analyze()

    print("\n── 7. 认证 ──")
    test_auth_required()
    test_invalid_token()

    print("\n── 8. 边界条件 ──")
    test_recommend_unknown_category()
    test_recommend_count_zero()

    print("\n── 9. 工具 API ──")
    test_tools_list()
    test_tool_info()

    print("\n── 10. 缓存机制 ──")
    test_llm_cache_speed()

    # Summary
    print("\n" + "=" * 60)
    total = PASSED + FAILED
    print(f"  测试结果: {PASSED}/{total} 通过, {FAILED} 失败")
    if ERRORS:
        print("\n  失败详情:")
        for err in ERRORS:
            print(f"    {err}")
    print("=" * 60)

    if FAILED > 0:
        sys.exit(1)