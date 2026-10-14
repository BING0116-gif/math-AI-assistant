import pytest

from app.services.qdrant_reconciliation import ReconciliationReport, rebuild


def test_reconciliation_report_counts_all_differences():
    report = ReconciliationReport(kind="memory", collection="mem", expected=2, actual=2,
                                  missing=["1"], stale=["9"], user_scope_errors=["2"],
                                  embedding_version_mismatch=["3"])
    assert report.different == 4
    assert report.as_dict()["collection"] == "mem"


@pytest.mark.asyncio
async def test_memory_rebuild_requires_explicit_user_scope():
    with pytest.raises(PermissionError, match="user-id"):
        await rebuild("memory", execute=True)


@pytest.mark.asyncio
async def test_invalid_kind_is_rejected():
    with pytest.raises(ValueError):
        await rebuild("all", execute=True)
