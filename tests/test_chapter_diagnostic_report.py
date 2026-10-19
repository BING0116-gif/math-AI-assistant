import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.data.models import Base, Course, KnowledgeGraphVersion, Chapter, KnowledgePoint, User, PracticeSession
from app.api.chapter_diagnostic_api import _enrich


@pytest.mark.asyncio
async def test_unit_report_separates_untested_points_and_keeps_all_tested_comparisons(monkeypatch):
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    factory = async_sessionmaker(engine, expire_on_commit=False)
    import app.data.database as database
    monkeypatch.setattr(database, 'async_session_factory', factory)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with factory() as db:
            db.add_all([Course(id='c', code='math', name='数学', subject='math'), KnowledgeGraphVersion(id='v', course_id='c', version='1', name='V1', status='published'), User(id='u', username='qa', email='qa@example.test', password_hash='x')])
            db.add(Chapter(id='root', course_id='c', version_id='v', code='root', name='整单元'))
            await db.flush()
            db.add(Chapter(id='child', parent_id='root', course_id='c', version_id='v', code='child', name='小节'))
            await db.flush()
            for code in ['weak', 'strong', 'untested']:
                db.add(KnowledgePoint(id=code, code=code, name=code, chapter_id='child', course_id='c', version_id='v', status='active'))
            db.add(PracticeSession(id='s', user_id='u', course_id='c', version_id='v', mode='assessment', random_seed=1, status='completed', idempotency_key='diagnostic-key', config_snapshot={'chapter_id':'root', 'diagnostic_kind':'diagnostic', 'mastery_before':{'strong':0.2}}))
            await db.commit()
        result = await _enrich('u', 's', {'status':'completed', 'knowledge_breakdown':[{'knowledge_point_code':'weak', 'accuracy':0.4}, {'knowledge_point_code':'strong', 'accuracy':1.0}]})
        assert [p['knowledge_point_code'] for p in result['weak_points']] == ['weak']
        assert [p['knowledge_point_code'] for p in result['untested_points']] == ['untested']
        assert result['mastery_comparison']['after'] == {'weak':0.4, 'strong':1.0}
        assert result['recommended_resources'] == []
        from app.services.practice_service import recent_sessions
        recent = await recent_sessions('u')
        assert recent['completed'][0]['result_path'] == '/chapter-diagnostics/s/result'
        assert recent['completed'][0]['diagnostic_kind'] == 'diagnostic'
    finally:
        await engine.dispose()
