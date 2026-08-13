from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from typing import Iterable


def precision_at_k(grades: list[int], k: int, relevant_grade: int = 1) -> float:
    if k < 1:
        raise ValueError("k must be >= 1")
    return sum(grade >= relevant_grade for grade in grades[:k]) / k


def reciprocal_rank(grades: list[int], relevant_grade: int = 2) -> float:
    for rank, grade in enumerate(grades, start=1):
        if grade >= relevant_grade:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(grades: list[int], k: int, ideal_grades: list[int] | None = None) -> float:
    def dcg(values: list[int]) -> float:
        return sum((2**grade - 1) / math.log2(rank + 1) for rank, grade in enumerate(values, start=1))

    observed = dcg(grades[:k])
    ideal = dcg(sorted(ideal_grades if ideal_grades is not None else grades, reverse=True)[:k])
    return observed / ideal if ideal else 0.0


def pooled_recall_at_k(grades: list[int], relevant_in_pool: int, k: int, relevant_grade: int = 1) -> float:
    if relevant_in_pool < 0:
        raise ValueError("relevant_in_pool must be >= 0")
    if not relevant_in_pool:
        return 0.0
    return sum(grade >= relevant_grade for grade in grades[:k]) / relevant_in_pool


def mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def bootstrap_mean_ci(values: list[float], *, repeats: int = 2000, seed: int = 20260811) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return values[0], values[0]
    rng = random.Random(seed)
    estimates = sorted(mean(rng.choices(values, k=len(values))) for _ in range(repeats))
    return estimates[int(0.025 * repeats)], estimates[min(repeats - 1, int(0.975 * repeats))]


def cohen_kappa(labels_a: list[str], labels_b: list[str]) -> float | None:
    if len(labels_a) != len(labels_b) or not labels_a:
        return None
    observed = mean(a == b for a, b in zip(labels_a, labels_b))
    counts_a = Counter(labels_a)
    counts_b = Counter(labels_b)
    total = len(labels_a)
    expected = sum((counts_a[label] / total) * (counts_b[label] / total) for label in counts_a | counts_b)
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def pairwise_kappas(rows: list[dict[str, str]], *, item_key: str, annotator_key: str, label_key: str) -> dict[str, float]:
    by_annotator: dict[str, dict[str, str]] = defaultdict(dict)
    for row in rows:
        by_annotator[row[annotator_key]][row[item_key]] = row[label_key]
    annotators = sorted(by_annotator)
    results = {}
    for left_index, left in enumerate(annotators):
        for right in annotators[left_index + 1 :]:
            common = sorted(set(by_annotator[left]) & set(by_annotator[right]))
            value = cohen_kappa(
                [by_annotator[left][item] for item in common],
                [by_annotator[right][item] for item in common],
            )
            if value is not None:
                results[f"{left}__{right}"] = value
    return results
