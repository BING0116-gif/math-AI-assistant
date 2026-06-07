"""E2E test: Register user via API, get token, call recommendation API."""
import json
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8000"

# Step 1: Register
print("=== Step 1: Register ===")
try:
    data = json.dumps({"username": "testuser", "password": "test123456"}).encode('utf-8')
    req = urllib.request.Request(f"{BASE_URL}/api/auth/register", data=data,
        headers={'Content-Type': 'application/json'})
    resp = urllib.request.urlopen(req)
    print(f"Register: {json.loads(resp.read())}")
except urllib.error.HTTPError as e:
    print(f"Register (may already exist): {e.code} - {e.read().decode()}")

# Step 2: Login
print("\n=== Step 2: Login ===")
data = json.dumps({"username": "testuser", "password": "test123456"}).encode('utf-8')
req = urllib.request.Request(f"{BASE_URL}/api/auth/login", data=data,
    headers={'Content-Type': 'application/json'})
resp = urllib.request.urlopen(req)
login_result = json.loads(resp.read())
print(f"Login status: {login_result.get('status')}")
token = login_result.get('data', {}).get('access_token', '')
user_id = login_result.get('data', {}).get('user_id', '')
print(f"User ID: {user_id}")
print(f"Token: {token[:50]}...{token[-20:]}")

if not token:
    print("ERROR: Failed to get token!")
    exit(1)

# Step 3: Call health check
print("\n=== Step 3: Health Check ===")
req = urllib.request.Request(f"{BASE_URL}/api/recommend/health")
resp = urllib.request.urlopen(req)
health = json.loads(resp.read())
print(f"Health: {json.dumps(health, indent=2, ensure_ascii=False)}")

# Step 4: Call recommendation API
print("\n=== Step 4: Recommend Questions ===")
data = json.dumps({
    "target_category": "导数",
    "count": 3,
    "context": "practice"
}).encode('utf-8')
req = urllib.request.Request(f"{BASE_URL}/api/recommend/questions", data=data,
    headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    })
try:
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    print(f"Success: {result.get('success')}")
    questions = result.get('data', {}).get('questions', [])
    print(f"Questions count: {len(questions)}")
    for q in questions:
        print(f"  - [{q['id']}] {q['content'][:60]}... (difficulty: {q['difficulty']})")
    meta = result.get('data', {}).get('meta', {})
    print(f"\nMeta: {json.dumps(meta, indent=2, ensure_ascii=False)}")
    ai = result.get('data', {}).get('ai_analysis', {})
    if ai:
        print(f"\nAI Analysis: {json.dumps(ai, indent=2, ensure_ascii=False)}")
    print(f"\nProcessing time: {result.get('processing_time_ms', 0):.0f}ms")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} - {e.read().decode()}")

# Step 5: Vector search
print("\n=== Step 5: Vector Search ===")
data = json.dumps({
    "query": "求导数的链式法则",
    "category": "导数",
    "n_results": 3
}).encode('utf-8')
req = urllib.request.Request(f"{BASE_URL}/api/recommend/vector-search", data=data,
    headers={
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    })
try:
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    print(f"Success: {result.get('success')}")
    results = result.get('data', {}).get('results', [])
    print(f"Results count: {len(results)}")
    for r in results:
        print(f"  - [{r['id']}] {r['content'][:50]}... (score: {r['score']})")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} - {e.read().decode()}")

print("\n=== E2E Test Complete ===")