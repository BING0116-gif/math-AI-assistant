"""Tests for scripts/content_admin/ — 可测逻辑（API client / formatting / validation）。

Streamlit 入口做 import smoke（无 streamlit 时自动 skip）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 让 scripts/content_admin/ 下的模块可直接 import（不把 scripts 整体变成包）
CONTENT_ADMIN_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CONTENT_ADMIN_DIR))

from api_client import ContentAdminClient, ContentAdminError, default_base_url
from validation import (
    CHECKLIST_KEYS,
    REVIEW_CHECKLIST,
    SUPPORTED_TYPES,
    batch_status_label,
    blocking_warnings,
    candidate_status_label,
    checklist_ready,
    format_options_text,
    is_supported,
    is_unsupported,
    parse_options_text,
    parser_display_name,
    question_status_label,
    render_candidate_preview,
    type_display_name,
)


# ══════════════════════════════════════════════════════════════════
# Validation — display labels
# ══════════════════════════════════════════════════════════════════
class TestLabels:
    def test_parser_display_name(self):
        assert parser_display_name("quick") == "Quick 解析"
        assert parser_display_name("mineru") == "MinerU"
        assert parser_display_name(None) == "未知"
        assert parser_display_name("") == "未知"

    def test_batch_status_label(self):
        assert batch_status_label("parsed") == "已解析"
        assert batch_status_label("failed") == "失败"
        assert batch_status_label(None) == "未知"

    def test_candidate_status_label(self):
        assert candidate_status_label("parsed") == "已解析"
        assert candidate_status_label("rejected") == "已拒绝"
        assert candidate_status_label(None) == "未知"

    def test_question_status_label(self):
        assert question_status_label("draft") == "草稿"
        assert question_status_label("reviewed") == "已审核"
        assert question_status_label("published") == "已发布"
        assert question_status_label(None) == "未知"

    def test_type_display_name_supported(self):
        assert type_display_name("choice") == "选择题"
        assert type_display_name("judge") == "判断题"
        assert type_display_name("numeric_fill") == "数值填空题"
        assert type_display_name("expression_fill") == "表达式填空题"

    def test_type_display_name_unsupported(self):
        assert type_display_name("calculation") == "计算题（暂不支持）"
        assert type_display_name("proof") == "证明题（暂不支持）"
        assert type_display_name(None) == "未知"

    def test_is_supported(self):
        assert is_supported("choice") is True
        assert is_supported("judge") is True
        assert is_supported("numeric_fill") is True
        assert is_supported("expression_fill") is True
        assert is_supported("calculation") is False
        assert is_supported("proof") is False
        assert is_supported("subjective") is False

    def test_is_unsupported(self):
        assert is_unsupported("choice") is False
        assert is_unsupported("calculation") is True
        assert is_unsupported("proof") is True


# ══════════════════════════════════════════════════════════════════
# Validation — options text
# ══════════════════════════════════════════════════════════════════
class TestOptionsText:
    def test_format_options(self):
        opts = [{"id": "A", "text": "1"}, {"id": "B", "text": "2"}]
        assert format_options_text(opts) == "A. 1\nB. 2"

    def test_format_options_empty(self):
        assert format_options_text([]) == ""
        assert format_options_text(None) == ""

    def test_parse_options(self):
        text = "A. 1\nB. 2\nC. 3"
        result = parse_options_text(text)
        assert len(result) == 3
        assert result[0] == {"id": "A", "text": "1"}
        assert result[2] == {"id": "C", "text": "3"}

    def test_parse_options_various_separators(self):
        assert parse_options_text("A. x\nB．y\nC、z") == [
            {"id": "A", "text": "x"},
            {"id": "B", "text": "y"},
            {"id": "C", "text": "z"},
        ]

    def test_parse_options_empty(self):
        assert parse_options_text("") == []
        assert parse_options_text(None) == []


# ══════════════════════════════════════════════════════════════════
# Validation — blocking warnings
# ══════════════════════════════════════════════════════════════════
class TestBlockingWarnings:
    def test_no_warnings(self):
        assert blocking_warnings({}) == []

    def test_option_parse_uncertain(self):
        cand = {"warnings": ["option_parse_uncertain"]}
        q = {"options": []}
        assert "option_parse_uncertain" in blocking_warnings(cand, q)

    def test_option_parse_resolved(self):
        cand = {"warnings": ["option_parse_uncertain"]}
        q = {"options": [{"id": "A", "text": "1"}, {"id": "B", "text": "2"}]}
        assert "option_parse_uncertain" not in blocking_warnings(cand, q)

    def test_answer_match_missing_blocked(self):
        cand = {"warnings": ["answer_match_missing"]}
        q = {"answer": ""}
        assert "answer_match_missing" in blocking_warnings(cand, q)

    def test_answer_match_missing_resolved(self):
        cand = {"warnings": ["answer_match_missing"]}
        q = {"answer": "A"}
        assert "answer_match_missing" not in blocking_warnings(cand, q)

    def test_fill_type_needs_review(self):
        cand = {"warnings": ["fill_type_needs_review"]}
        q = {"question_type": "fill"}
        assert "fill_type_needs_review" in blocking_warnings(cand, q)

    def test_fill_type_resolved(self):
        cand = {"warnings": ["fill_type_needs_review"]}
        q = {"question_type": "numeric_fill"}
        assert "fill_type_needs_review" not in blocking_warnings(cand, q)

    def test_page_mapping_uncertain_missing(self):
        cand = {"warnings": ["page_mapping_uncertain"]}
        assert "page_mapping_uncertain" in blocking_warnings(cand)

    def test_page_mapping_uncertain_resolved(self):
        cand = {"warnings": ["page_mapping_uncertain"], "source_page_start": 1, "source_page_end": 1}
        assert "page_mapping_uncertain" not in blocking_warnings(cand)

    def test_contains_subquestions_advisory_not_blocking(self):
        """contains_subquestions 不作为阻塞（与服务端一致），仅提示。"""
        cand = {"warnings": ["contains_subquestions"]}
        assert "contains_subquestions" not in blocking_warnings(cand)


# ══════════════════════════════════════════════════════════════════
# Validation — checklist
# ══════════════════════════════════════════════════════════════════
class TestChecklist:
    def test_all_checked(self):
        checked = {k: True for k in CHECKLIST_KEYS}
        assert checklist_ready(checked) is True

    def test_one_unchecked(self):
        checked = {k: True for k in CHECKLIST_KEYS}
        checked["stem_matches_pdf"] = False
        assert checklist_ready(checked) is False

    def test_all_false(self):
        checked = {k: False for k in CHECKLIST_KEYS}
        assert checklist_ready(checked) is False


# ══════════════════════════════════════════════════════════════════
# Validation — candidate preview
# ══════════════════════════════════════════════════════════════════
class TestCandidatePreview:
    def test_basic_choice(self):
        cand = {
            "source_question_number": "1",
            "detected_question_type": "choice",
            "stem": "1+1=?",
            "options": [{"id": "A", "text": "1"}, {"id": "B", "text": "2"}],
            "original_answer": "B",
            "original_solution": "1+1=2",
            "source_page_start": 3,
            "source_page_end": 3,
        }
        preview = render_candidate_preview(cand)
        assert preview["source_question_number"] == "1"
        assert preview["type_display"] == "选择题"
        assert preview["supported"] == "支持"
        assert preview["answer"] == "B"
        assert preview["page"] == "第 3 页"

    def test_cross_page(self):
        cand = {"source_page_start": 3, "source_page_end": 5}
        preview = render_candidate_preview(cand)
        assert "跨页" in preview["page"]

    def test_unsupported(self):
        cand = {
            "detected_question_type": "proof",
            "stem": "证明...",
            "source_page_start": 1,
            "source_page_end": 1,
        }
        preview = render_candidate_preview(cand)
        assert preview["supported"] == "不支持"


# ══════════════════════════════════════════════════════════════════
# API Client — error handling
# ══════════════════════════════════════════════════════════════════
class TestApiClient:
    def test_default_base_url(self):
        url = default_base_url()
        assert url.startswith("http")

    def test_connection_error(self):
        client = ContentAdminClient(base_url="http://127.0.0.1:1")
        with pytest.raises(ContentAdminError) as exc:
            client.list_imports("fake-token")
        # Windows 上 httpx 可能抛出 OSError 而不被 httpx.HTTPError 捕获，
        # 此时 code 为 HTTP_ERROR；其他平台为 CONNECTION。两者都接受。
        assert exc.value.code in ("CONNECTION", "HTTP_ERROR")

    def test_http_error_parsing(self):
        """用 mock 模拟 401 错误响应。"""
        client = ContentAdminClient(base_url="http://test")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = '{"detail": {"code": "UNAUTHORIZED", "message": "未认证"}}'
        mock_resp.json.return_value = {"detail": {"code": "UNAUTHORIZED", "message": "未认证"}}
        with patch.object(client._client, "request", return_value=mock_resp):
            with pytest.raises(ContentAdminError) as exc:
                client._request("GET", "/api/admin/content/imports")
            assert exc.value.status_code == 401
            assert "UNAUTHORIZED" in exc.value.code

    def test_403_student(self):
        client = ContentAdminClient(base_url="http://test")
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = '{"detail": {"code": "FORBIDDEN", "message": "需要管理员权限"}}'
        mock_resp.json.return_value = {"detail": {"code": "FORBIDDEN", "message": "需要管理员权限"}}
        with patch.object(client._client, "request", return_value=mock_resp):
            with pytest.raises(ContentAdminError) as exc:
                client._request("POST", "/api/admin/content/questions/1/review", token="student-token")
            assert exc.value.status_code == 403
            assert "FORBIDDEN" in exc.value.code

    def test_validation_failure(self):
        client = ContentAdminClient(base_url="http://test")
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = json.dumps(
            {
                "detail": {
                    "code": "VALIDATION_FAILED",
                    "message": "审核未通过: 题干不能为空",
                    "errors": ["题干不能为空"],
                }
            }
        )
        mock_resp.json.return_value = {
            "detail": {
                "code": "VALIDATION_FAILED",
                "message": "审核未通过: 题干不能为空",
                "errors": ["题干不能为空"],
            }
        }
        with patch.object(client._client, "request", return_value=mock_resp):
            with pytest.raises(ContentAdminError) as exc:
                client._request("POST", "/api/admin/content/questions/1/review", token="admin-token")
            assert exc.value.status_code == 400
            assert exc.value.errors == ["题干不能为空"]

    def test_unwrap_error_code(self):
        client = ContentAdminClient(base_url="http://test")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"code": -1, "message": "内部错误"}
        with patch.object(client._client, "request", return_value=mock_resp):
            with pytest.raises(ContentAdminError) as exc:
                client._request_json("GET", "/api/admin/content/imports", token="admin-token")
            assert exc.value.status_code == 200

    def test_plain_text_error(self):
        client = ContentAdminClient(base_url="http://test")
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "Bad Request"
        mock_resp.json.side_effect = ValueError("not json")
        with patch.object(client._client, "request", return_value=mock_resp):
            with pytest.raises(ContentAdminError) as exc:
                client._request("GET", "/api/admin/content/imports", token="admin-token")
            assert exc.value.status_code == 400

    def test_preview_raw_bytes(self):
        """preview 接口返回原始字节（image/png），不走 JSON 解包。"""
        client = ContentAdminClient(base_url="http://test")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"\x89PNGfake"
        with patch.object(client._client, "request", return_value=mock_resp):
            data = client.preview_page("admin-token", "doc-1", 3)
            assert data == b"\x89PNGfake"

    def test_login_path_and_method(self):
        client = ContentAdminClient(base_url="http://test")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": "success",
            "data": {"user_id": "u1", "username": "admin", "access_token": "tok", "refresh_token": "r", "token_type": "bearer"},
        }
        with patch.object(client._client, "request", return_value=mock_resp) as mock_req:
            data = client.login("admin", "secret")
            assert data["access_token"] == "tok"
            args = mock_req.call_args
            assert args.args[0] == "POST"
            assert args.args[1].endswith("/api/auth/login")


# ══════════════════════════════════════════════════════════════════
# App — smoke test
# ══════════════════════════════════════════════════════════════════
class TestAppSmoke:
    def test_can_import(self):
        """验证 app.py 可以导入（不触发 streamlit runtime 异常）。"""
        pytest.importorskip("streamlit")
        import app as app_mod
        assert app_mod.PAGE_TITLE == "知微 · 内容审核"
        assert hasattr(app_mod, "main")
        assert hasattr(app_mod, "render_import_jobs")
        assert hasattr(app_mod, "render_candidate_review")
        assert hasattr(app_mod, "render_question_queue")