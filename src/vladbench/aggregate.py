"""TOTAL, task wins, and the cost-performance frontier: the one definition of each.

web/results.js keeps its own TOTAL (modelMean) because the page recomputes it under task filters; a test checks that
both agree on the published record.
"""
from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TypedDict

TIE_TOLERANCE = 1e-9


class TaskScore(TypedDict):
    score: float
    questions_scored: int


def total(tasks: Mapping[str, TaskScore], *, skip: Collection[str] = (), override: Mapping[str, float] | None = None) -> float:
    """Question-weighted mean of task scores: the paper's TOTAL. `override` swaps in other scores for some tasks."""
    override = override or {}
    pairs = [(override.get(name, t["score"]), t["questions_scored"]) for name, t in tasks.items() if name not in skip]
    if not pairs:
        raise ValueError("TOTAL over no tasks")
    return sum(score * n for score, n in pairs) / sum(n for _, n in pairs)


def group_means(tasks: Mapping[str, TaskScore], groups: Mapping[str, Sequence[str]]) -> dict[str, float]:
    """The same weighting within each task group: Table 10's MEAN rows."""
    return {group: total({name: tasks[name] for name in names if name in tasks}) for group, names in groups.items()}


@dataclass(frozen=True)
class Tie:
    task: str
    model_ids: tuple[str, ...]


def task_wins(scores: Mapping[str, Mapping[str, float]], task_order: Sequence[str]) -> tuple[dict[str, int], list[Tie]]:
    """Sole-leader counts per model (model id -> task -> score) and the tasks tied for first. Models keep input order."""
    wins = dict.fromkeys(scores, 0)
    ties = []
    for task in task_order:
        best = max(by_task[task] for by_task in scores.values())
        leaders = tuple(model_id for model_id, by_task in scores.items() if abs(by_task[task] - best) < TIE_TOLERANCE)
        if len(leaders) == 1:
            wins[leaders[0]] += 1
        else:
            ties.append(Tie(task, leaders))
    return wins, ties


@dataclass(frozen=True)
class Point:
    model_id: str
    cost: float
    score: float


def frontier(points: Iterable[Point]) -> list[Point]:
    """Models that no other model beats on score for the same cost or less, cheapest first."""
    points = list(points)
    kept = [p for p in points if not any(q.score > p.score and q.cost <= p.cost for q in points)]
    return sorted(kept, key=lambda p: p.cost)
