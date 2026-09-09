"""运行 T04 题目向量去重最小校准集并输出相似度分布。"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config.settings import settings
from app.services.embedding_service import get_embedding_service

DEFAULT_DATASET = ROOT / "evaluations" / "question_dedup" / "v1" / "pairs.json"
GROUP_LABELS = {
    "same_rewrite": "同题改写",
    "same_concept_different": "同知识点不同题",
    "cross_concept": "跨知识点",
}


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def distribution(values: list[float]) -> dict[str, float | int]:
    return {
        "n": len(values),
        "mean": fmean(values),
        "p10": percentile(values, 0.10),
        "p90": percentile(values, 0.90),
        "min": min(values),
        "max": max(values),
    }


def recommend_threshold(groups: dict[str, list[float]]) -> tuple[float, float]:
    positives = groups["same_rewrite"]
    negatives = groups["same_concept_different"] + groups["cross_concept"]
    points = sorted(set(positives + negatives))
    candidates = [0.0, 1.0]
    candidates.extend((left + right) / 2 for left, right in zip(points, points[1:]))

    best_threshold = settings.QUESTION_DEDUP_THRESHOLD
    best_score = -1.0
    best_specificity = -1.0
    for threshold in candidates:
        sensitivity = sum(score >= threshold for score in positives) / len(positives)
        specificity = sum(score < threshold for score in negatives) / len(negatives)
        balanced_accuracy = (sensitivity + specificity) / 2
        key = (balanced_accuracy, specificity, threshold)
        if key > (best_score, best_specificity, best_threshold):
            best_score, best_specificity, best_threshold = key
    return best_threshold, best_score


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        raise ValueError("embedding 向量范数不能为 0")
    return numerator / (left_norm * right_norm)


async def run(dataset_path: Path) -> int:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    groups = payload.get("groups") or {}
    if set(groups) != set(GROUP_LABELS):
        raise ValueError("校准集必须包含同题改写、同知识点不同题、跨知识点三组")
    if any(len(pairs) < 20 for pairs in groups.values()):
        raise ValueError("每个校准组必须至少包含 20 对题目")

    embedding_service = get_embedding_service()
    vectors: dict[str, list[float]] = {}
    scores_by_group: dict[str, list[float]] = {}
    for group, pairs in groups.items():
        scores: list[float] = []
        for left, right in pairs:
            if left not in vectors:
                vectors[left] = await embedding_service.encode_async(left)
            if right not in vectors:
                vectors[right] = await embedding_service.encode_async(right)
            scores.append(cosine_similarity(vectors[left], vectors[right]))
        scores_by_group[group] = scores

    print(f"模型：{embedding_service.model_name}  维度：{embedding_service.vector_size}")
    for group, label in GROUP_LABELS.items():
        stats = distribution(scores_by_group[group])
        print(
            f"{label:<10} n={stats['n']:>2}  mean={stats['mean']:.4f}  "
            f"p10={stats['p10']:.4f}  p90={stats['p90']:.4f}  "
            f"min={stats['min']:.4f}  max={stats['max']:.4f}"
        )

    recommended, balanced_accuracy = recommend_threshold(scores_by_group)
    configured = settings.QUESTION_DEDUP_THRESHOLD
    print(f"当前阈值：{configured:.4f}")
    print(
        f"建议阈值：{recommended:.4f}（校准集 balanced_accuracy={balanced_accuracy:.4f}；"
        "同题改写为正类，其余两组为负类）"
    )
    for group, label in GROUP_LABELS.items():
        blocked = sum(score >= configured for score in scores_by_group[group])
        print(f"当前阈值拦截：{label} {blocked}/{len(scores_by_group[group])}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()
    return asyncio.run(run(args.dataset))


if __name__ == "__main__":
    raise SystemExit(main())
