"""Alembic 迁移与 Python logging 的卫生测试。

背景（2026-09 排查）：env.py 的 fileConfig 默认
disable_existing_loggers=True，会在进程内执行迁移时把所有已创建的
应用 logger（app.services.* 等）静默禁用。曾导致全量 pytest 下
test_llm_robustness / test_question_dedup 等 8 个 caplog 断言失败
（单文件运行则通过），生产侧进程内自动迁移同样会丢失应用日志。
env.py 已改为 disable_existing_loggers=False，本测试防止回归。
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config


def test_in_process_migration_keeps_existing_loggers_enabled(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "app" / "data" / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url", f"sqlite:///{(tmp_path / 'logging.db').as_posix()}"
    )

    # 迁移前确保目标 logger 处于正常状态（防御其他测试遗留污染）
    target = logging.getLogger("app.services.llm_service")
    target.disabled = False

    command.upgrade(config, "head")

    assert target.disabled is False, (
        "进程内执行 Alembic 迁移禁用了既有应用 logger："
        "检查 app/data/alembic/env.py 的 fileConfig 是否带 "
        "disable_existing_loggers=False"
    )

    # 被迁移过的 logger 仍须能把日志送达 root handlers
    records: list[str] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    collector = _Collector()
    root = logging.getLogger()
    root.addHandler(collector)
    try:
        target.warning("迁移后应用日志仍应可见")
    finally:
        root.removeHandler(collector)

    assert "迁移后应用日志仍应可见" in records
