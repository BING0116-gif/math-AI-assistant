from datetime import datetime, timezone
from types import SimpleNamespace

from app.api.content_import_api import _serialize_candidate


def _candidate(runs):
    return SimpleNamespace(
        id="candidate-1",
        import_batch_id="batch-1",
        candidate_index=0,
        source_page_start=1,
        source_page_end=1,
        source_question_number="1",
        stem="题干",
        options=[],
        original_answer="A",
        original_solution="解析",
        detected_question_type="choice",
        supported=True,
        warnings=[],
        suggested_knowledge_point_codes=[],
        status="parsed",
        created_at=datetime.now(timezone.utc),
        updated_at=None,
        ai_analysis_runs=runs,
    )


def test_candidate_serializer_exposes_latest_analysis_summary():
    candidate = _candidate([
        SimpleNamespace(attempt_no=1, gate="FAILED", status="failed", human_disposition="reject"),
        SimpleNamespace(attempt_no=2, gate="PASS", status="pass", human_disposition="approved"),
    ])

    payload = _serialize_candidate(candidate)

    assert payload["latest_ai_gate"] == "PASS"
    assert payload["latest_ai_status"] == "pass"
    assert payload["latest_human_disposition"] == "approved"


def test_candidate_serializer_keeps_new_fields_nullable_without_analysis():
    payload = _serialize_candidate(_candidate([]))

    assert payload["latest_ai_gate"] is None
    assert payload["latest_ai_status"] is None
    assert payload["latest_human_disposition"] is None
