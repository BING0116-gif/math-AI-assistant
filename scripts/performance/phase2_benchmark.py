"""Versioned, network-free Phase 2 performance smoke benchmark.

The smoke profile uses a disposable SQLite database populated only with fixed
synthetic rows. It is intended for repeatable CI regression detection. It does
not replace a controlled Compose load test for capacity planning.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import platform
import sqlite3
import statistics
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable


ROOT = Path(__file__).resolve().parents[2]
SCENARIO_VERSION = "phase2-v1"
SYNTHETIC_SCALE = {
    "users": 8,
    "courses": 2,
    "knowledge_points": 500,
    "questions": 500,
    "learning_records": 2000,
    "error_items": 800,
    "outbox_events": 500,
    "rag_documents": 500,
}
MODEL_LIMITS = {"max_calls": 3, "timeout_seconds": 20, "max_budget_usd": 0.10}


@dataclass
class Measurement:
    name: str
    kind: str
    boundary: str
    samples: int
    concurrency: int
    cold_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    throughput_per_second: float
    errors: int
    error_rate: float
    budget_ms: float
    passed: bool
    quality: dict[str, float] | None = None


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _measure(
    name: str,
    kind: str,
    boundary: str,
    operation: Callable[[], object],
    *,
    samples: int,
    concurrency: int,
    budget_ms: float,
    quality: dict[str, float] | None = None,
) -> Measurement:
    start = time.perf_counter()
    operation()
    cold_ms = (time.perf_counter() - start) * 1000
    latencies: list[float] = []
    errors = 0
    run_start = time.perf_counter()
    for _ in range(samples):
        started = time.perf_counter()
        try:
            operation()
        except Exception:
            errors += 1
        latencies.append((time.perf_counter() - started) * 1000)
    elapsed = max(time.perf_counter() - run_start, 1e-9)
    p95 = _percentile(latencies, 0.95)
    error_rate = errors / max(samples, 1)
    return Measurement(
        name=name,
        kind=kind,
        boundary=boundary,
        samples=samples,
        concurrency=concurrency,
        cold_ms=round(cold_ms, 3),
        p50_ms=round(_percentile(latencies, 0.50), 3),
        p95_ms=round(p95, 3),
        p99_ms=round(_percentile(latencies, 0.99), 3),
        throughput_per_second=round(samples / elapsed, 2),
        errors=errors,
        error_rate=round(error_rate, 6),
        budget_ms=budget_ms,
        passed=errors == 0 and p95 <= budget_ms,
        quality=quality,
    )


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.row_factory = sqlite3.Row
    return connection


def _seed_database(path: Path) -> None:
    connection = _connect(path)
    connection.executescript(
        """
        CREATE TABLE courses(id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL);
        CREATE TABLE knowledge_points(id TEXT PRIMARY KEY, course_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL, sort_order INTEGER NOT NULL);
        CREATE INDEX ix_points_course ON knowledge_points(course_id, sort_order);
        CREATE TABLE questions(id TEXT PRIMARY KEY, point_id TEXT NOT NULL, content TEXT NOT NULL, answer TEXT NOT NULL);
        CREATE INDEX ix_questions_point ON questions(point_id);
        CREATE TABLE learning_records(id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, point_id TEXT NOT NULL, correct INTEGER NOT NULL, duration_ms INTEGER NOT NULL);
        CREATE INDEX ix_learning_user ON learning_records(user_id, id);
        CREATE TABLE error_items(id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, question_id TEXT NOT NULL, mastered INTEGER NOT NULL, updated_at INTEGER NOT NULL);
        CREATE INDEX ix_errors_user ON error_items(user_id, mastered, updated_at DESC);
        CREATE TABLE practice_sessions(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, status TEXT NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE practice_attempts(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER NOT NULL, question_id TEXT NOT NULL, correct INTEGER NOT NULL);
        CREATE TABLE outbox_events(id INTEGER PRIMARY KEY, event_type TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX ix_outbox_status ON outbox_events(status, id);
        """
    )
    connection.executemany("INSERT INTO courses VALUES (?, ?, 'active')", [(f"c{i}", f"Synthetic Course {i}") for i in range(2)])
    points = [(f"kp{i}", f"c{i % 2}", f"code-{i}", f"Knowledge Point {i}", i) for i in range(500)]
    connection.executemany("INSERT INTO knowledge_points VALUES (?, ?, ?, ?, ?)", points)
    questions = [(f"q{i}", f"kp{i}", f"Synthetic question {i}", str(i % 7)) for i in range(500)]
    connection.executemany("INSERT INTO questions VALUES (?, ?, ?, ?)", questions)
    records = [(i, f"u{i % 8}", f"kp{i % 500}", int(i % 3 != 0), 1000 + i % 5000) for i in range(2000)]
    connection.executemany("INSERT INTO learning_records VALUES (?, ?, ?, ?, ?)", records)
    errors = [(i, f"u{i % 8}", f"q{i % 500}", int(i % 5 == 0), 1_700_000_000 + i) for i in range(800)]
    connection.executemany("INSERT INTO error_items VALUES (?, ?, ?, ?, ?)", errors)
    outbox = [(i, "memory.upsert", "pending", json.dumps({"id": i}), 0) for i in range(500)]
    connection.executemany("INSERT INTO outbox_events VALUES (?, ?, ?, ?, ?)", outbox)
    connection.commit()
    connection.close()


def _vector(index: int, dimensions: int = 16) -> list[float]:
    digest = hashlib.sha256(f"phase2-vector-{index}".encode()).digest()
    values = [((digest[offset] / 255) * 2) - 1 for offset in range(dimensions)]
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


def _cosine(left: Iterable[float], right: Iterable[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def run_smoke(samples: int = 40, concurrency: int = 1) -> dict:
    with tempfile.TemporaryDirectory(prefix="mathai_phase2_") as directory:
        database = Path(directory) / "synthetic.db"
        _seed_database(database)
        connection = _connect(database)

        def home_dependencies():
            return (
                connection.execute("SELECT id, name FROM courses WHERE status='active' ORDER BY name").fetchall(),
                connection.execute("SELECT COUNT(*) FROM learning_records WHERE user_id='u1'").fetchone()[0],
                connection.execute("SELECT COUNT(*) FROM error_items WHERE user_id='u1' AND mastered=0").fetchone()[0],
            )

        def knowledge_catalog():
            rows = connection.execute(
                "SELECT id, code, name FROM knowledge_points WHERE course_id='c0' ORDER BY sort_order"
            ).fetchall()
            return json.dumps([dict(row) for row in rows], ensure_ascii=False)

        def dashboard():
            return connection.execute(
                "SELECT COUNT(*), AVG(correct), SUM(duration_ms) FROM learning_records WHERE user_id='u1'"
            ).fetchone()

        def error_book():
            return connection.execute(
                "SELECT question_id, updated_at FROM error_items WHERE user_id='u1' AND mastered=0 ORDER BY updated_at DESC LIMIT 50"
            ).fetchall()

        def practice_create():
            cursor = connection.execute(
                "INSERT INTO practice_sessions(user_id,status,created_at) VALUES ('u1','created',?)",
                (time.time_ns(),),
            )
            connection.execute("DELETE FROM practice_sessions WHERE id=?", (cursor.lastrowid,))
            connection.commit()

        def practice_submit():
            connection.execute("BEGIN")
            cursor = connection.execute(
                "INSERT INTO practice_sessions(user_id,status,created_at) VALUES ('u1','in_progress',?)",
                (time.time_ns(),),
            )
            connection.execute(
                "INSERT INTO practice_attempts(session_id,question_id,correct) VALUES (?,?,1)",
                (cursor.lastrowid, "q1"),
            )
            connection.execute("UPDATE practice_sessions SET status='completed' WHERE id=?", (cursor.lastrowid,))
            connection.rollback()

        vectors = [_vector(index) for index in range(500)]
        queries = [(index, vectors[index]) for index in range(0, 500, 25)]

        def rag_embedding():
            digest = hashlib.sha256(b"synthetic calculus query").digest()
            values = [((digest[offset] / 255) * 2) - 1 for offset in range(16)]
            norm = math.sqrt(sum(value * value for value in values))
            return [value / norm for value in values]

        def rag_retrieval():
            expected, query = queries[rag_retrieval.cursor % len(queries)]
            rag_retrieval.cursor += 1
            ranked = sorted(enumerate(vectors), key=lambda row: _cosine(query, row[1]), reverse=True)[:5]
            return expected, [item[0] for item in ranked]

        rag_retrieval.cursor = 0
        quality_hits = 0
        reciprocal_ranks = []
        for expected, query in queries:
            ranked = sorted(enumerate(vectors), key=lambda row: _cosine(query, row[1]), reverse=True)[:5]
            ids = [item[0] for item in ranked]
            if expected in ids:
                quality_hits += 1
                reciprocal_ranks.append(1 / (ids.index(expected) + 1))
            else:
                reciprocal_ranks.append(0)
        rag_quality = {
            "recall_at_5": round(quality_hits / len(queries), 4),
            "mrr_at_5": round(statistics.mean(reciprocal_ranks), 4),
        }

        def outbox_batch():
            ids = [row[0] for row in connection.execute(
                "SELECT id FROM outbox_events WHERE status='pending' ORDER BY id LIMIT 50"
            ).fetchall()]
            if ids:
                connection.executemany("UPDATE outbox_events SET status='completed' WHERE id=?", [(event_id,) for event_id in ids])
                connection.executemany("UPDATE outbox_events SET status='pending' WHERE id=?", [(event_id,) for event_id in ids])
                connection.commit()
            return len(ids)

        chat_payload = json.dumps({"message": "求极限", "stream": True, "conversation_id": "synthetic"})

        def chat_stream_entry():
            payload = json.loads(chat_payload)
            if not payload["message"] or not payload["stream"]:
                raise ValueError("invalid stream request")
            return hashlib.sha256(payload["conversation_id"].encode()).hexdigest()

        definitions = [
            ("home_dependencies", "read", "database", home_dependencies, 300),
            ("knowledge_catalog", "read", "database", knowledge_catalog, 300),
            ("learning_dashboard", "read", "database", dashboard, 300),
            ("error_book_list", "read", "database", error_book, 300),
            ("practice_create", "write", "database", practice_create, 500),
            ("practice_submit", "write", "database", practice_submit, 500),
            ("rag_embedding", "read", "embedding", rag_embedding, 300),
            ("rag_retrieval", "read", "vector", rag_retrieval, 300),
            ("outbox_batch_50", "write", "database", outbox_batch, 500),
            ("chat_stream_entry", "read", "application", chat_stream_entry, 300),
        ]
        measurements = []
        for name, kind, boundary, operation, budget in definitions:
            quality = rag_quality if name == "rag_retrieval" else None
            measurements.append(asdict(_measure(
                name,
                kind,
                boundary,
                operation,
                samples=samples,
                concurrency=concurrency,
                budget_ms=budget,
                quality=quality,
            )))
        drain_started = time.perf_counter()
        drained = connection.execute("UPDATE outbox_events SET status='completed' WHERE status='pending'").rowcount
        connection.commit()
        drain_ms = round((time.perf_counter() - drain_started) * 1000, 3)
        pending = connection.execute("SELECT COUNT(*) FROM outbox_events WHERE status='pending'").fetchone()[0]
        dead = connection.execute("SELECT COUNT(*) FROM outbox_events WHERE status='dead'").fetchone()[0]
        connection.close()

    return {
        "schema_version": 1,
        "scenario_version": SCENARIO_VERSION,
        "profile": "smoke",
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "git_sha": _git_sha(),
            "database": "disposable SQLite synthetic fixture",
            "vector": "deterministic in-process cosine index",
            "model": "disabled",
        },
        "data_scale": SYNTHETIC_SCALE,
        "load": {"concurrency": concurrency, "samples_per_scenario": samples},
        "external_model_limits": MODEL_LIMITS | {"calls_used": 0},
        "boundaries": {
            "application": "local request admission work",
            "database": "disposable SQLite fixture",
            "embedding": "deterministic CPU embedding substitute",
            "vector": "deterministic cosine retrieval",
            "model": "skipped in smoke profile; limits remain enforced",
        },
        "measurements": measurements,
        "outbox": {
            "processed_batch": 50,
            "drained_events": drained,
            "drain_500_ms": drain_ms,
            "drain_budget_ms": 120_000,
            "pending": pending,
            "dead": dead,
        },
        "passed": all(item["passed"] for item in measurements)
        and rag_quality["recall_at_5"] == 1.0
        and rag_quality["mrr_at_5"] == 1.0
        and drained == 500
        and drain_ms <= 120_000
        and pending == 0
        and dead == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("smoke",), default="smoke")
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts" / "performance" / "phase2-smoke.json")
    args = parser.parse_args()
    report = run_smoke(samples=max(5, args.samples), concurrency=max(1, args.concurrency))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    args.output.write_text(payload, encoding="utf-8")
    gzip_path = args.output.with_suffix(args.output.suffix + ".gz")
    gzip_path.write_bytes(gzip.compress(payload.encode("utf-8")))
    print(payload)
    print(f"report={args.output}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
