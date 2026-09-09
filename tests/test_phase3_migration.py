import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config


def test_existing_assessment_draft_survives_phase3_rename(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database_path = tmp_path / "phase3.db"
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "app" / "data" / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "a9c0d1e2f3a4")

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """INSERT INTO assessment_draft_answers
               (user_id, session_id, session_question_id, answer, version, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("user-old", "session-old", 7, '"A"', 3, "2026-01-01 00:00:00"),
        )
        connection.commit()

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            "SELECT user_id, session_id, session_question_id, answer, version "
            "FROM practice_session_draft_answers"
        ).fetchone()
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert row == ("user-old", "session-old", 7, '"A"', 3)
    assert revision == "b8d9e0f1a2b3"
