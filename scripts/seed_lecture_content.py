# -*- coding: utf-8 -*-
"""把人工编写的《精讲》与《易错警示》讲义写入 knowledge_point_resources。

- 内容源：scripts/lecture_content.py（仓库维护者撰写，零 LLM、零 API 成本）。
- 幂等：按 (knowledge_point_id, resource_type, title) 唯一约束 upsert——
  已存在则更新正文与发布时间，不存在则插入 published。
- 运行：venv/Scripts/python.exe scripts/seed_lecture_content.py [--only code1,code2]
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lecture_content import LECTURES, PITFALLS

COURSE_CODE = "advanced-calculus"
SPEC = (("lecture", "精讲", LECTURES), ("pitfalls", "易错警示", PITFALLS))


async def main(only: set[str] | None = None) -> None:
    from sqlalchemy import func, select

    from app.data.database import close_db, get_db_session, init_db
    from app.data.models import Course, KnowledgePoint, KnowledgePointResource

    await init_db()
    now = datetime.now(timezone.utc)
    created = updated = missing = 0

    async with get_db_session() as db:
        course = (await db.execute(
            select(Course).where(Course.code == COURSE_CODE, Course.status == "active")
        )).scalars().first()
        if course is None or not course.default_version_id:
            raise SystemExit("课程 advanced-calculus 不存在或没有默认知识版本")

        points = (await db.execute(
            select(KnowledgePoint).where(
                KnowledgePoint.course_id == course.id,
                KnowledgePoint.status == "active",
            ).order_by(KnowledgePoint.sort_order, KnowledgePoint.id)
        )).scalars().all()

        for point in points:
            if only and point.code not in only:
                continue
            for resource_type, title, source in SPEC:
                body = source.get(point.code)
                if not body or not body.strip():
                    missing += 1
                    print(f"[missing] {point.code} 缺 {resource_type} 内容")
                    continue
                existing = (await db.execute(
                    select(KnowledgePointResource).where(
                        KnowledgePointResource.knowledge_point_id == point.id,
                        KnowledgePointResource.resource_type == resource_type,
                        KnowledgePointResource.title == title,
                    )
                )).scalars().first()
                if existing:
                    existing.body = body
                    existing.status = "published"
                    existing.published_at = now
                    updated += 1
                else:
                    db.add(KnowledgePointResource(
                        knowledge_point_id=point.id,
                        resource_type=resource_type,
                        title=title,
                        body=body,
                        sort_order=0,
                        status="published",
                        math_validation_status="verified",
                        published_at=now,
                    ))
                    created += 1
        await db.commit()

        total = (await db.execute(
            select(func.count()).select_from(KnowledgePointResource)
            .where(KnowledgePointResource.resource_type.in_(("lecture", "pitfalls")),
                   KnowledgePointResource.status == "published")
        )).scalar_one()

    print(f"[done] created={created} updated={updated} missing={missing} "
          f"讲义资源总数(published)={total}")
    await close_db()


if __name__ == "__main__":
    only_arg = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        only_arg = {c.strip() for c in sys.argv[idx + 1].split(",") if c.strip()}
    asyncio.run(main(only_arg))
