"""Resolve a selected chapter and its descendants within one course version."""
from sqlalchemy import select
from app.data.models import Chapter


async def expand_chapter_scope(db, selected, course_id: str, version_id: str) -> set[str]:
    rows = (await db.execute(select(Chapter.id, Chapter.parent_id).where(
        Chapter.course_id == course_id, Chapter.version_id == version_id,
    ))).all()
    resolved = set(selected)
    if not resolved <= {row.id for row in rows}:
        from app.services.practice_service import PracticeError
        raise PracticeError("VALIDATION_FAILED", "所选章节不属于当前课程版本")
    while True:
        children = {row.id for row in rows if row.parent_id in resolved}
        if children <= resolved:
            return resolved
        resolved |= children
