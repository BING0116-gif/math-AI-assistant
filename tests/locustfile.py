"""
Locust 性能测试脚本。

测试目标 API 端点的响应时间和并发性能。

用法:
    pip install locust
    locust -f tests/locustfile.py --host=http://localhost:8000

目标指标:
    - P95 响应时间 < 500ms
    - 流式响应首字节 < 1s
"""

from locust import HttpUser, task, between


class MathAIAssistantUser(HttpUser):
    """模拟数学AI助手用户行为"""

    wait_time = between(1, 3)

    def on_start(self):
        """初始化会话"""
        self.session_id = "perf-test-session"
        self.headers = {"Content-Type": "application/json"}

    @task(3)
    def health_check(self):
        """健康检查端点"""
        self.client.get("/api/health")

    @task(2)
    def chat_message(self):
        """发送聊天消息"""
        self.client.post(
            "/api/chat",
            json={
                "message": "1+1等于几？",
                "session_id": self.session_id,
            },
            headers=self.headers,
            timeout=30,
        )

    @task(2)
    def get_agent_stats(self):
        """获取 Agent 统计"""
        self.client.get("/api/agent/stats")

    @task(1)
    def list_tools(self):
        """获取工具列表"""
        self.client.get("/api/tools")

    @task(1)
    def list_error_books(self):
        """获取错题本列表"""
        self.client.get("/api/error-book")

    @task(1)
    def get_thought_history(self):
        """获取思考历史"""
        self.client.get(f"/api/agent/thought/{self.session_id}")

    @task(1)
    def recommend_questions(self):
        """推荐题目"""
        self.client.post(
            "/api/recommendation",
            json={
                "user_id": "test_user",
                "count": 3,
            },
            headers=self.headers,
            timeout=30,
        )