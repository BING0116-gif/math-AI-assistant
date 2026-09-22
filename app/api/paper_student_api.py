"""Legacy student paper API — permanent 410 tombstone.

The student-facing paper flow was replaced by the owner-scoped practice /
exam / assessment session APIs.  These endpoints stay registered only to
answer old clients with an explicit 410 Gone plus the replacement path;
they must never execute any composition or grading logic again.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/papers", tags=["组卷测试-学生端（已废弃）"], deprecated=True)


def _deprecated() -> None:
    raise HTTPException(
        status_code=410,
        detail={
            "code": "PAPER_API_DEPRECATED",
            "message": "旧组卷接口已停用，请使用 /api/practice/sessions",
            "replacement": "/api/practice/sessions",
        },
    )


@router.post("/generate")
async def generate_paper():
    _deprecated()


@router.get("/{paper_id}")
async def get_paper(paper_id: str):
    _deprecated()


@router.post("/{paper_id}/submit")
async def submit_paper(paper_id: str):
    _deprecated()
