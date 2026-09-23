"""answers/<Task>.json: every model's answer and per-question mark for every question, loaded when a row is expanded.

Before a file is written, each model's marks are re-aggregated and compared with the components the released scorer
produced; a mismatch stops the build, so the answer grid can never disagree with the leaderboard.

  {"task", "family", "base", "models": [id, ...], "questions": [{"i", "id", "kind", "sample", "sequence", "question",
   "prompt", "gold", "images": [path relative to base, ...], "answers": {model_id: [text, accuracy, instruction, other, pair]}}]}
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path

from . import paths
from .per_question import components_from_marks, sample_marks
from .record import ModelRecord, Record
from .run import read_jsonl

TEXT_LIMIT = 400
TOLERANCE = 1e-9


class MarksMismatch(ValueError):
    """Per-question marks do not re-aggregate to the released scorer's components."""


def recorded_answers(model_id: str, task: str, runs: Path = paths.RUNS) -> dict[str, str]:
    path = runs / model_id / f"{task}.jsonl"
    return {record["id"]: record["answer"] for record in read_jsonl(path)} if path.exists() else {}


def mark_task(family: str, answers: Mapping[str, str], requests: Sequence[dict]) -> dict[str, dict] | None:
    """Request id -> mark for one model on one task, or None if any answer is missing."""
    if any(r["id"] not in answers for r in requests):
        return None
    by_sample: dict[int, list[dict]] = {}
    for r in requests:
        by_sample.setdefault(r["sample_index"], []).append(r)
    marks = {}
    for group in by_sample.values():
        group.sort(key=lambda r: r["question_index"])
        for r, mark in zip(group, sample_marks(family, group[0]["sample"], [answers[r["id"]] for r in group]), strict=True):
            mark["text"] = answers[r["id"]]
            marks[r["id"]] = mark
    return marks


def check_marks(task: str, family: str, model: ModelRecord, marks: Mapping[str, dict]) -> None:
    got = components_from_marks(family, list(marks.values()))
    want = model["tasks"][task]["components"]
    for value, key in zip(got, ("accuracy", "instruction_following", "other"), strict=True):
        if abs(value - want[key]) > TOLERANCE:
            raise MarksMismatch(f"{model['id']} {task}: per-question {key} {value:.6f} != released {want[key]:.6f}")


def answer_cell(mark: dict) -> list:
    text = mark["text"].strip()
    return [text[:TEXT_LIMIT] + ("…" if len(text) > TEXT_LIMIT else ""), round(mark["accuracy"], 6), mark["instruction"],
            None if mark["other"] is None else round(mark["other"], 4), mark["pair"]]


def task_answers(task: str, family: str, models: Sequence[ModelRecord], items: Sequence[dict], runs: Path = paths.RUNS) -> dict:
    """Every model's answer and mark for every question of one task, in the page's question order."""
    from .requests import questions

    requests = questions(task)
    if len(items) != len(requests):
        raise ValueError(f"{task}: {len(items)} page items but {len(requests)} questions")
    per_model: dict[str, dict[str, dict]] = {}
    for model in models:
        if model["tasks"].get(task, {}).get("score") is None:
            continue
        marks = mark_task(family, recorded_answers(model["id"], task, runs), requests)
        if marks is None:
            continue
        check_marks(task, family, model, marks)
        per_model[model["id"]] = marks
    rows = []
    for position, (r, item) in enumerate(zip(requests, items, strict=True)):
        kind = next(iter(per_model.values()))[r["id"]]["kind"] if per_model else None
        rows.append({"i": position, "id": r["id"], "kind": kind, "sample": item["id"], "sequence": item["sequence"],
                     "question": item["question"], "prompt": item["prompt"], "gold": item["gold"],
                     "images": [image["path"].removeprefix(paths.FRAME_BASE) for image in item["images"]],
                     "answers": {model_id: answer_cell(marks[r["id"]]) for model_id, marks in per_model.items()}})
    return {"task": task, "family": family, "base": paths.FRAME_BASE, "models": list(per_model), "questions": rows}


def write_answers(record: Record, inputs: Sequence[dict], out: Path = paths.ANSWERS, runs: Path = paths.RUNS) -> list[Path]:
    """One file per scored task."""
    from .requests import tasks
    from .scoring import load_scorer

    scorers = load_scorer()[0].func_mapping
    items = {task["name"]: task["items"] for task in inputs}
    out.mkdir(exist_ok=True)
    written = []
    for task in tasks():
        if task not in scorers:
            continue
        data = task_answers(task, scorers[task].__name__, record["models"], items[task], runs)
        path = out / f"{task}.json"
        path.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
        written.append(path)
    return written
