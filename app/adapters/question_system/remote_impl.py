"""
出题系统 Remote 适配器。

联调/生产阶段使用，通过 HTTP 事件接口与真实出题系统交互。
"""

import logging
import hashlib
import hmac
import json
import time
from urllib.parse import urljoin
import httpx
import threading
from typing import Any, Dict, List

from app.adapters.question_system.base import BaseQuestionSystemAdapter

logger = logging.getLogger(__name__)


class RemoteQuestionSystemAdapter(BaseQuestionSystemAdapter):
    """Remote 出题系统适配器，对接真实出题系统 HTTP 接口。"""

    def __init__(self, api_key: str = "", base_url: str = "", *, timeout: float = 5.0, max_retries: int = 2, signing_secret: str = ""):
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        self._max_retries = max(0, max_retries)
        self._signing_secret = signing_secret or api_key
        self._rate_lock = threading.Lock(); self._last_request = 0.0
        self._min_interval = 1.0 / max(1.0, float(__import__('os').getenv('QUESTION_SYSTEM_RPS', '5')))
        logger.info("[Remote适配器] 初始化完成，对接真实出题系统")

    def _request(self, path: str, *, params: dict | None = None) -> dict | list:
        if not self._base_url or not self._api_key:
            raise RuntimeError("question system remote credentials are not configured")
        url = urljoin(self._base_url.rstrip("/") + "/", path.lstrip("/"))
        body = json.dumps(params or {}, separators=(",", ":"), ensure_ascii=False)
        headers = {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json", "Content-Type": "application/json"}
        if self._signing_secret:
            headers["X-Signature"] = hmac.new(self._signing_secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        last = None
        for attempt in range(self._max_retries + 1):
            try:
                with self._rate_lock:
                    wait = self._min_interval - (time.monotonic() - self._last_request)
                    if wait > 0: time.sleep(wait)
                    self._last_request = time.monotonic()
                response = httpx.request("GET", url, params=params, headers=headers, timeout=self._timeout)
                response.raise_for_status(); value = response.json()
                if not isinstance(value, (dict, list)): raise ValueError("invalid JSON response")
                return value
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
                if attempt < self._max_retries: time.sleep(0.1 * (2 ** attempt))
        raise RuntimeError(f"question system request failed: {last}")

    @staticmethod
    def _question(value: Any, question_id: str) -> Dict[str, Any]:
        if not isinstance(value, dict) or not value.get("id"): raise ValueError("invalid question response")
        return {"id": str(value["id"]), "content": str(value.get("content") or ""), "high_category": str(value.get("high_category") or ""), "category": str(value.get("category") or ""), "knowledge_points": value.get("knowledge_points") or [], "difficulty": int(value.get("difficulty") or 3), "is_active": bool(value.get("is_active", True))}

    def get_question_info(self, question_id: str) -> Dict[str, Any]:
        return self._question(self._request(f"/questions/{question_id}"), question_id)

    def get_user_mastery(self, user_id: str, category: str) -> Dict[str, Any]:
        value = self._request(f"/users/{user_id}/mastery/{category}")
        if not isinstance(value, dict): raise ValueError("invalid mastery response")
        return {"mastery_score": float(value.get("mastery_score", 0)), "correct_rate": float(value.get("correct_rate", 0)), "total_questions": int(value.get("total_questions", 0))}

    def get_user_mastery_all(self, user_id: str) -> Dict[str, Any]:
        value = self._request(f"/users/{user_id}/mastery")
        if not isinstance(value, dict): raise ValueError("invalid mastery response")
        return value

    def get_user_chapter_progress(self, user_id: str, high_category: str) -> List[Dict[str, Any]]:
        value = self._request(f"/users/{user_id}/chapters", params={"high_category": high_category})
        if not isinstance(value, list): raise ValueError("invalid chapter response")
        return value

    def get_user_recent_questions(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        value = self._request(f"/users/{user_id}/recent-questions", params={"limit": max(1, min(limit, 200))})
        if not isinstance(value, list): raise ValueError("invalid recent questions response")
        return value

    def check_health(self) -> bool:
        try: self._request("/health"); return True
        except Exception: return False

    def delete_question(self, question_id: str) -> bool:
        self._request(f"/questions/{question_id}/delete"); return True

    def retract_question(self, question_id: str) -> bool:
        self._request(f"/questions/{question_id}/retract"); return True
