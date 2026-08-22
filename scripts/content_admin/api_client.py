"""api_client.py — Step 1.1-D 内容审核工具 API Client（纯 httpx，不依赖 streamlit）。

只负责：base URL / Authorization / timeout / JSON 解码 / 错误归一化。
这样 API client 本身可独立单测，Streamlit 页面不散落 requests 调用。

登录：复用正式 /api/auth/login（access token 仅保存在调用方 st.session_state，
本模块不写文件、不写 .env）。
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
TIMEOUT_SECONDS = 60.0


class ContentAdminError(Exception):
    """结构化错误：status_code + code + message + errors。"""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        errors: Optional[List[str]] = None,
        response: Optional[httpx.Response] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.errors = errors or []
        self.response = response


def default_base_url() -> str:
    """API Base URL：优先环境变量，不得 hardcode 用户机器绝对地址。"""
    return os.environ.get("ZHIWEI_API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _extract_detail(resp: httpx.Response) -> Dict[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        return {"code": "HTTP_ERROR", "message": resp.text[:500]}
    if isinstance(data, dict):
        detail = data.get("detail", data)
        if isinstance(detail, dict):
            return detail
        if isinstance(detail, str):
            return {"code": "HTTP_ERROR", "message": detail}
    return {"code": "HTTP_ERROR", "message": "HTTP " + str(resp.status_code)}


class ContentAdminClient:
    def __init__(self, base_url: Optional[str] = None, timeout: float = TIMEOUT_SECONDS):
        self.base_url = (base_url or default_base_url()).rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    # ── 底层请求 ──
    def _request(
        self,
        method: str,
        path: str,
        *,
        token: Optional[str] = None,
        json_body: Any = None,
        files: Any = None,
        params: Any = None,
    ) -> httpx.Response:
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            resp = self._client.request(
                method,
                f"{self.base_url}{path}",
                headers=headers,
                json=json_body,
                files=files,
                params=params,
            )
        except httpx.HTTPError as exc:  # 连接失败/超时
            raise ContentAdminError(0, "CONNECTION", f"无法连接 API（{self.base_url}）: {exc}") from exc
        if resp.status_code >= 400:
            detail = _extract_detail(resp)
            raise ContentAdminError(
                resp.status_code,
                detail.get("code", "HTTP_ERROR"),
                detail.get("message", resp.text[:500]),
                detail.get("errors") or [],
                response=resp,
            )
        return resp

    def _unwrap(self, resp: httpx.Response) -> Any:
        try:
            payload = resp.json()
        except ValueError:
            raise ContentAdminError(resp.status_code, "BAD_JSON", "API 返回了非 JSON 内容") from None
        if isinstance(payload, dict):
            code = payload.get("code")
            status = payload.get("status")
            if code is not None and code != 0:
                raise ContentAdminError(
                    resp.status_code,
                    str(code),
                    str(payload.get("message", "API 返回错误")),
                )
            if status is not None and status != "success":
                raise ContentAdminError(
                    resp.status_code,
                    str(status),
                    str(payload.get("message", "API 返回错误")),
                )
            if code is None and status is None:
                # 兼容裸对象（无包裹）响应
                return payload
            return payload.get("data")
        return payload

    def _request_json(self, method: str, path: str, **kw) -> Any:
        return self._unwrap(self._request(method, path, **kw))

    def _request_raw(self, method: str, path: str, **kw) -> bytes:
        return self._request(method, path, **kw).content

    # ── 认证（复用现有 /api/auth/login）──
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """返回 {user_id, username, access_token, refresh_token, token_type}。"""
        return self._request_json("POST", "/api/auth/login", json_body={"username": username, "password": password})

    # ── Import Jobs ──
    def list_imports(self, token: str) -> List[Dict[str, Any]]:
        return self._request_json("GET", "/api/admin/content/imports", token=token)

    def get_import(self, token: str, batch_id: str) -> Dict[str, Any]:
        return self._request_json("GET", f"/api/admin/content/imports/{batch_id}", token=token)

    def create_import(self, token: str, filename: str, content: bytes, mode: str) -> Dict[str, Any]:
        files = {"file": (filename, content, "application/pdf")}
        return self._request_json(
            "POST", "/api/admin/content/imports", token=token, files=files, params={"mode": mode}
        )

    # ── Candidates ──
    def list_candidates(self, token: str, batch_id: str) -> List[Dict[str, Any]]:
        return self._request_json("GET", f"/api/admin/content/imports/{batch_id}/candidates", token=token)

    def update_candidate(self, token: str, batch_id: str, candidate_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        return self._request_json(
            "PATCH", f"/api/admin/content/imports/{batch_id}/candidates/{candidate_id}", token=token, json_body=patch
        )

    def reject_candidate(self, token: str, batch_id: str, candidate_id: str) -> Dict[str, Any]:
        return self._request_json(
            "POST", f"/api/admin/content/imports/{batch_id}/candidates/{candidate_id}/reject", token=token
        )

    def create_drafts(self, token: str, batch_id: str, candidate_ids: List[str]) -> Dict[str, Any]:
        return self._request_json(
            "POST", f"/api/admin/content/imports/{batch_id}/drafts", token=token, json_body={"candidate_ids": candidate_ids}
        )

    # ── Source Document / PDF preview ──
    def get_source_document(self, token: str, document_id: str) -> Dict[str, Any]:
        return self._request_json("GET", f"/api/admin/content/source-documents/{document_id}", token=token)

    def preview_page(self, token: str, document_id: str, page: int) -> bytes:
        return self._request_raw(
            "GET", f"/api/admin/content/source-documents/{document_id}/pages/{page}/preview", token=token
        )

    # ── KnowledgePoints ──
    def list_knowledge_points(self, token: str) -> List[Dict[str, Any]]:
        return self._request_json("GET", "/api/admin/content/knowledge-points", token=token)

    # ── Question Review Queue ──
    def list_questions(self, token: str, review_status: Optional[str] = None) -> List[Dict[str, Any]]:
        params = None if review_status is None else {"review_status": review_status}
        return self._request_json("GET", "/api/admin/content/questions", token=token, params=params)

    def get_question(self, token: str, question_id: str) -> Dict[str, Any]:
        return self._request_json("GET", f"/api/admin/content/questions/{question_id}", token=token)

    def update_question(self, token: str, question_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        return self._request_json("PATCH", f"/api/admin/content/questions/{question_id}", token=token, json_body=patch)

    def mark_reviewed(self, token: str, question_id: str) -> Dict[str, Any]:
        return self._request_json("POST", f"/api/admin/content/questions/{question_id}/review", token=token)

    def publish_question(self, token: str, question_id: str) -> Dict[str, Any]:
        return self._request_json("POST", f"/api/admin/content/questions/{question_id}/publish", token=token)

    # ── Content Coverage / Stats（Step 1.1-E1，只读）──
    def get_content_coverage(self, token: str) -> Dict[str, Any]:
        return self._request_json("GET", "/api/admin/content/coverage", token=token)

    def get_content_stats(self, token: str) -> Dict[str, Any]:
        return self._request_json("GET", "/api/admin/content/stats", token=token)

    # ── AI Analysis 阶段（Step 1.1-E2-A0）──
    def provider_status(self, token: str) -> Dict[str, Any]:
        return self._request_json("GET", "/api/admin/content/ai-analysis/provider-status", token=token)

    def analyze_batch(self, token: str, batch_id: str) -> Dict[str, Any]:
        return self._request_json(
            "POST", f"/api/admin/content/imports/{batch_id}/ai-analysis", token=token
        )

    def analyze_batch_async(self, token: str, batch_id: str) -> Dict[str, Any]:
        """启动后台批量分析任务，返回 {task_id, batch_id}。"""
        return self._request_json(
            "POST", f"/api/admin/content/imports/{batch_id}/ai-analysis/async", token=token
        )

    def get_analyze_batch_task(self, token: str, task_id: str) -> Dict[str, Any]:
        """查询异步批量分析任务状态与进度。"""
        return self._request_json(
            "GET", f"/api/admin/content/ai-analysis/tasks/{task_id}", token=token
        )

    def batch_stats(self, token: str, batch_id: str) -> Dict[str, Any]:
        return self._request_json(
            "GET", f"/api/admin/content/imports/{batch_id}/ai-analysis/stats", token=token
        )

    def analyze_candidate(self, token: str, candidate_id: str) -> Dict[str, Any]:
        return self._request_json(
            "POST", f"/api/admin/content/candidates/{candidate_id}/ai-analysis", token=token
        )

    def reanalyze_candidate(
        self, token: str, candidate_id: str, reanalyze_reason: Optional[str] = None
    ) -> Dict[str, Any]:
        return self._request_json(
            "POST",
            f"/api/admin/content/candidates/{candidate_id}/ai-analysis/reanalyze",
            token=token,
            json_body={"reanalyze_reason": reanalyze_reason},
        )

    def candidate_analysis(self, token: str, candidate_id: str) -> Dict[str, Any]:
        return self._request_json(
            "GET", f"/api/admin/content/candidates/{candidate_id}/ai-analysis", token=token
        )

    def set_disposition(
        self, token: str, candidate_id: str, disposition: str, note: Optional[str] = None
    ) -> Dict[str, Any]:
        return self._request_json(
            "POST",
            f"/api/admin/content/candidates/{candidate_id}/ai-analysis/disposition",
            token=token,
            json_body={"disposition": disposition, "note": note},
        )

    def create_draft_from_approved(self, token: str, candidate_id: str) -> Dict[str, Any]:
        return self._request_json(
            "POST", f"/api/admin/content/candidates/{candidate_id}/ai-analysis/create-draft", token=token
        )

    def batch_set_disposition(
        self, token: str, candidate_ids: List[str], disposition: str, note: Optional[str] = None
    ) -> Dict[str, Any]:
        return self._request_json(
            "POST",
            "/api/admin/content/candidates/ai-analysis/batch-disposition",
            token=token,
            json_body={"candidate_ids": candidate_ids, "disposition": disposition, "note": note},
        )

    def batch_create_drafts(self, token: str, candidate_ids: List[str]) -> Dict[str, Any]:
        return self._request_json(
            "POST",
            "/api/admin/content/candidates/ai-analysis/batch-create-drafts",
            token=token,
            json_body={"candidate_ids": candidate_ids},
        )

    def batch_publish_questions(self, token: str, question_ids: List[str]) -> Dict[str, Any]:
        return self._request_json(
            "POST",
            "/api/admin/content/questions/batch-publish",
            token=token,
            json_body={"question_ids": question_ids},
        )
