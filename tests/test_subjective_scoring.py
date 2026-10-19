import pytest

from app.services.subjective_scoring_service import _validate, DIMENSIONS


def test_subjective_score_accepts_only_whitelisted_dimensions_and_clamps_scores():
    payload = _validate({
        "dimension_scores": {name: 1.4 for name in DIMENSIONS},
        "verdict": "probably_correct",
        "rationale": {"evidence": ["学生给出了公式和结论"]},
    })
    assert payload.dimension_scores["concept_use"] == 1.0
    assert payload.review_status == "not_required"


def test_uncertain_verdict_forces_human_review():
    payload = _validate({"dimension_scores": {}, "verdict": "unable_to_determine", "rationale": {"reason": "步骤缺失"}})
    assert payload.review_status == "pending"


@pytest.mark.parametrize("verdict", ["correct", "wrong", "certain"])
def test_unknown_verdict_is_rejected(verdict):
    with pytest.raises(ValueError):
        _validate({"dimension_scores": {}, "verdict": verdict})
