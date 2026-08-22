from app.services.error_classification import ErrorCategory, classify_error


def test_taxonomy_is_fixed_to_product_contract():
    assert {item.value for item in ErrorCategory} == {
        "KNOWLEDGE_GAP", "CONCEPT_MISUNDERSTANDING", "CONDITION_MISSING",
        "CALCULATION_ERROR", "METHOD_SELECTION", "FORMULA_MISUSE", "CARELESS", "UNKNOWN",
    }


def test_unknown_is_used_when_wrong_answer_has_insufficient_evidence():
    result = classify_error({}, "B", correct=False)
    assert result["category"] == "UNKNOWN"
    assert result["confidence"] == 0.2
    assert result["source"] == "deterministic_rule"
    assert result["version"] == "error-taxonomy-v1"


def test_reviewed_common_mistake_can_produce_specific_category():
    snapshot = {"common_mistakes": [{"answer": "0", "category": "FORMULA_MISUSE", "reason": "漏用了链式法则", "key_error_step": "求导", "suggestion": "复习链式法则"}]}
    result = classify_error(snapshot, "0", correct=False)
    assert result["category"] == "FORMULA_MISUSE"
    assert result["source"] == "reviewed_rule"
    assert result["confidence"] == 1.0


def test_correct_answer_has_no_error_classification():
    assert classify_error({}, "A", correct=True) is None
