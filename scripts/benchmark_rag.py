# -*- coding: utf-8 -*-
"""
RAG 检索性能基准脚本（简历量化用）

目标：产出「Qdrant + BGE 语义检索」的真实性能数字：
  - 纯检索延迟（query_points，不含 embedding）：p50 / p95 / p99 / QPS
  - 全链路延迟（用户视角：embedding encode + Qdrant 检索）
  - 批量灌库吞吐（向量索引构建速度）

测试环境说明（诚实声明）：
  - Qdrant 以 embedded 模式运行（qdrant-client 本地引擎），临时目录，跑完自动清理
  - 不修改 qdrant_storage/ 与 data/math_ai.db（只读题目数据）
  - 向量模型：BAAI/bge-small-zh-v1.5（512 维，与 app/config/settings.py VECTOR_SIZE 一致）
  - 数据源：data/math_ai.db 全部真实题目
  - 查询集：真实题干 + 手工构造的知识点类问题（模拟学生提问）

用法：
  cd 项目根 && venv/Scripts/python.exe scripts/benchmark_rag.py
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "math_ai.db"
COLLECTION = "math_questions_bge_zh_v1"
VECTOR_SIZE = 512
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
TOP_K = 5
WARMUP = 5          # 预热次数
REPEAT = 10         # 每个查询重复次数


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def fmt(ms: float) -> str:
    return f"{ms:.2f}"


def main() -> None:
    # ---------- 1. 读取真实题目 ----------
    print("[1/5] 读取题目数据…")
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    rows = cur.execute(
        "SELECT id, content, category FROM questions WHERE is_active = 1 ORDER BY id"
    ).fetchall()
    con.close()
    if not rows:
        print("!! 没有可用题目，退出")
        sys.exit(1)
    questions = [{"id": r[0], "content": r[1], "category": r[2]} for r in rows]
    print(f"    共 {len(questions)} 道有效题目")

    # ---------- 2. 启动 embedded Qdrant（临时副本目录） ----------
    print("[2/5] 启动 embedded Qdrant…")
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct

    tmp_dir = tempfile.mkdtemp(prefix="rag_bench_")
    client = QdrantClient(path=tmp_dir)
    if client.get_collections().collections:
        client.recreate_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
    else:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
    print(f"    collection={COLLECTION}, dim={VECTOR_SIZE}, 临时目录={tmp_dir}")

    # ---------- 3. 加载 BGE 模型 + 批量灌库（计时） ----------
    print("[3/5] 加载 embedding 模型并批量灌库…")
    t0 = time.perf_counter()
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME)
    model_load_s = time.perf_counter() - t0

    texts = [q["content"] for q in questions]
    t1 = time.perf_counter()
    vectors = model.encode(texts, normalize_embeddings=True, batch_size=32)
    encode_s = time.perf_counter() - t1

    t2 = time.perf_counter()
    batch_size = 32
    for i in range(0, len(questions), batch_size):
        chunk = questions[i : i + batch_size]
        points = [
            PointStruct(
                id=hash(q["id"]) % (2**63),
                vector=vectors[j].tolist(),
                payload={"question_id": q["id"], "content": q["content"][:2000], "category": q["category"] or ""},
            )
            for j, q in enumerate(chunk)
        ]
        client.upsert(collection_name=COLLECTION, points=points)
    upsert_s = time.perf_counter() - t2

    n_points = client.count(collection_name=COLLECTION).count
    print(f"    模型加载 {model_load_s:.1f}s | 编码 {encode_s:.1f}s | 写入 {upsert_s:.2f}s | 总入库 {len(questions)} 条")

    # ---------- 4. 构造查询集 ----------
    # 真实题干（模拟学生贴题提问）+ 手工知识点问题
    manual_queries = [
        "求函数极限的常用方法有哪些",
        "定积分的换元积分法怎么做",
        "如何判断级数是否收敛",
        "多元函数求偏导的链式法则",
        "微分中值定理的应用",
        "求解一阶线性微分方程",
    ]
    stem_queries = [q["content"][:80] for q in questions[:12]]
    queries = manual_queries + stem_queries
    print(f"[4/5] 查询集：手工知识点问题 {len(manual_queries)} 条 + 真实题干 {len(stem_queries)} 条，共 {len(queries)} 条")

    # 预热（含首次推理的额外开销）
    warm = model.encode(queries[0], normalize_embeddings=True)
    for _ in range(WARMUP):
        client.query_points(collection_name=COLLECTION, query=warm.tolist(), limit=TOP_K, with_payload=True)

    # ---------- 5. 压测 ----------
    print("[5/5] 压测中…")
    pure_lat = []   # 纯 Qdrant 检索
    full_lat = []   # 全链路（encode + search）
    top1_hits = []  # top1 是否与查询同 category（弱相关性信号）

    for q in queries:
        for _ in range(REPEAT):
            t = time.perf_counter()
            v = model.encode(q, normalize_embeddings=True)
            t_full_start = time.perf_counter()
            resp = client.query_points(collection_name=COLLECTION, query=v.tolist(), limit=TOP_K, with_payload=True)
            t_end = time.perf_counter()
            pure_lat.append((t_end - t_full_start) * 1000)
            full_lat.append((t_end - t) * 1000)
            if resp.points:
                top1_hits.append(resp.points[0].payload.get("category") or "")

    pure_sorted = sorted(pure_lat)
    full_sorted = sorted(full_lat)

    print("\n" + "=" * 64)
    print("RAG 检索性能基准结果（BGE-small-zh-v1.5 · 512 维 · Qdrant embedded）")
    print("=" * 64)
    print(f"集合规模       : {n_points} 条向量 × {VECTOR_SIZE} 维")
    print(f"压测样本       : {len(queries)} 个查询 × {REPEAT} 次 = {len(pure_lat)} 次检索")
    print(f"批量灌库       : {len(questions)} 条 / {encode_s + upsert_s:.1f}s（编码+写入）≈ {len(questions)/(encode_s+upsert_s):.1f} 条/s")
    print("-" * 64)
    print(f"{'指标':<12}{'纯检索(ms)':>14}{'全链路(ms)':>16}")
    print(f"{'p50':<12}{fmt(percentile(pure_sorted, 50)):>14}{fmt(percentile(full_sorted, 50)):>16}")
    print(f"{'p95':<12}{fmt(percentile(pure_sorted, 95)):>14}{fmt(percentile(full_sorted, 95)):>16}")
    print(f"{'p99':<12}{fmt(percentile(pure_sorted, 99)):>14}{fmt(percentile(full_sorted, 99)):>16}")
    print(f"{'avg':<12}{fmt(sum(pure_lat)/len(pure_lat)):>14}{fmt(sum(full_lat)/len(full_lat)):>16}")
    qps = 1000 / percentile(pure_sorted, 50)
    print(f"{'QPS(p50)':<12}{qps:>14.0f}{'':>16}")
    print("-" * 64)
    # 保存报告
    report = {
        "环境": {
            "qdrant": "embedded (qdrant-client local)",
            "embedding": MODEL_NAME,
            "vector_size": VECTOR_SIZE,
            "top_k": TOP_K,
            "数据源": "data/math_ai.db 真实题目",
        },
        "集合规模": n_points,
        "灌库": {"条数": len(questions), "编码耗时_s": round(encode_s, 2), "写入耗时_s": round(upsert_s, 2), "吞吐_条_s": round(len(questions) / (encode_s + upsert_s), 1)},
        "纯检索_ms": {"p50": round(percentile(pure_sorted, 50), 2), "p95": round(percentile(pure_sorted, 95), 2), "p99": round(percentile(pure_sorted, 99), 2), "avg": round(sum(pure_lat) / len(pure_lat), 2)},
        "全链路_ms": {"p50": round(percentile(full_sorted, 50), 2), "p95": round(percentile(full_sorted, 95), 2), "p99": round(percentile(full_sorted, 99), 2), "avg": round(sum(full_lat) / len(full_lat), 2)},
    }
    out = PROJECT_ROOT / "artifacts" / "rag_benchmark_result.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告已保存: {out}")

    # 清理
    client.close()
    shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
