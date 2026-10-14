import pytest

from app.services.async_task import (
    CANCELLED,
    PERMANENTLY_FAILED,
    RETRYABLE_FAILED,
    RUNNING,
    SUCCEEDED,
    InvalidTaskTransition,
    legacy_status,
    transition,
)


class Task:
    status = "pending"
    attempts = 0
    started_at = succeeded_at = failed_at = cancelled_at = lease_until = updated_at = None
    last_error = None


@pytest.mark.parametrize("target", [RUNNING, CANCELLED])
def test_pending_has_only_valid_transitions(target):
    task = transition(Task(), target)
    assert task.status == target


@pytest.mark.parametrize("current,target", [(SUCCEEDED, RUNNING), (CANCELLED, RETRYABLE_FAILED), (PERMANENTLY_FAILED, RUNNING), ("unknown", RUNNING)])
def test_illegal_transition_is_rejected(current, target):
    task = Task(); task.status = current
    with pytest.raises(InvalidTaskTransition):
        transition(task, target)


def test_running_failure_records_attempt_and_error():
    task = Task()
    transition(task, RUNNING)
    transition(task, RETRYABLE_FAILED, error="qdrant unavailable")
    assert task.attempts == 1
    assert task.last_error == "qdrant unavailable"
    assert task.failed_at is not None


@pytest.mark.parametrize("old,new", [("retrying", RETRYABLE_FAILED), ("analyzing", RUNNING), ("fallback", SUCCEEDED), ("cancelled", CANCELLED)])
def test_legacy_status_mapping(old, new):
    assert legacy_status(old) == new
