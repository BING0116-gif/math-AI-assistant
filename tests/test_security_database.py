import pathlib


def test_alembic_cold_start_contract():
    """The real PostgreSQL cold start runs in CI; assert its required artifacts."""
    root = pathlib.Path(__file__).resolve().parents[1]
    migration = root / "app/data/alembic/versions/9d3f2a6b7c81_add_memory_user_foreign_keys.py"
    workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    migration_text = migration.read_text(encoding="utf-8")

    assert 'down_revision = "7824223d8a63"' in migration_text
    assert "fk_memories_user_id_users" in migration_text
    assert "fk_user_profiles_user_id_users" in migration_text
    assert "compose-cold-start:" in workflow
    assert "alembic -c app/data/alembic.ini upgrade head" in workflow
    assert "scripts.verification.verify_database_backend postgresql" in workflow


def test_event_idempotency_uses_database_unique_claim():
    root = pathlib.Path(__file__).resolve().parents[1]
    source = (root / "app/api/events_api.py").read_text(encoding="utf-8")
    assert "_event_idempotency" not in source
    assert "EventIdempotency(" in source
    assert "except IntegrityError" in source
    assert 'status="processing"' in source
    assert '"processed"' in source
    assert '"failed"' in source
