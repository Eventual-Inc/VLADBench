"""Per-question answers and marks for the results page, one JSON file per task.

  PYTHONPATH=src python3 scripts/build_answers.py

Reads the recorded sweeps in results/runs/full-original and the released annotations, marks every answer under the
paper's rules (vladbench.per_question), and writes answers/<Task>.json. Before writing, every model's marks are
re-aggregated and compared with the components the released scorer produced (task-review-results.js); a mismatch
aborts the build, so the grid can never disagree with the leaderboard.

File layout (about 12 MB across all tasks, loaded one task at a time when a row is expanded):
  {"task", "family", "models": [id, ...], "questions": [{"i": position in task-review-data order, "id": request id,
   "kind", "sample", "sequence", "question", "prompt", "gold", "images": [path relative to "base", ...],
   "answers": {model_id: [text, accuracy, instruction, other, pair]}}]}
"""
from __future__ import annotations

import json
from pathlib import Path

from vladbench.per_question import components_from_marks, sample_marks
from vladbench.requests import questions, tasks
from vladbench.run import RUNS, read_jsonl
from vladbench.scoring import load_scorer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "answers"
TEXT_LIMIT = 400
BASE = "https://huggingface.co/datasets/depth2world/VLADBench/resolve/1895f22252f9a702fed95334c8e3b60280b4c626/"   # image URLs are stored relative to this
TOLERANCE = 1e-9


def published() -> dict:
    return load_js(ROOT / "task-review-results.js")


def load_js(path: Path):
    text = path.read_text()
    return json.loads(text[text.index("=") + 1:].strip().rstrip(";"))


def question_items() -> dict[str, list[dict]]:
    """Prompt, reference, and frame URLs per question, in the results page's order (task-review-data.js)."""
    return {task["name"]: task["items"] for task in load_js(ROOT / "task-review-data.js")}


def recorded_answers(model_id: str, task: str) -> dict[str, str]:
    path = RUNS / "full-original" / model_id / f"{task}.jsonl"
    answers = {}
    if path.exists():
        for record in read_jsonl(path):
            answers[record["id"]] = record["answer"]
    return answers


def mark_task(task: str, family: str, model_id: str, requests: list[dict]) -> dict[str, dict] | None:
    """Request id -> mark for one model on one task, or None if any answer is missing."""
    answers = recorded_answers(model_id, task)
    if any(r["id"] not in answers for r in requests):
        return None
    marks = {}
    by_sample: dict[int, list[dict]] = {}
    for r in requests:
        by_sample.setdefault(r["sample_index"], []).append(r)
    for group in by_sample.values():
        group.sort(key=lambda r: r["question_index"])
        sample = group[0]["sample"]
        for r, mark in zip(group, sample_marks(family, sample, [answers[r["id"]] for r in group]), strict=True):
            mark["text"] = answers[r["id"]]
            marks[r["id"]] = mark
    return marks


def check(task: str, family: str, model: dict, marks: dict[str, dict]) -> None:
    got = components_from_marks(family, list(marks.values()))
    want = model["tasks"][task]["components"]
    for value, key in zip(got, ("accuracy", "instruction_following", "other"), strict=True):
        if abs(value - want[key]) > TOLERANCE:
            raise SystemExit(f"{model['id']} {task}: per-question {key} {value:.6f} != released {want[key]:.6f}")


def build_task(task: str, models: list[dict], scorers: dict, items: list[dict]) -> dict:
    family = scorers[task].__name__
    requests = questions(task)
    if len(items) != len(requests):
        raise SystemExit(f"{task}: {len(items)} page items but {len(requests)} questions")
    per_model = {}
    for model in models:
        if task not in model["tasks"] or model["tasks"][task].get("score") is None:
            continue
        marks = mark_task(task, family, model["id"], requests)
        if marks is None:
            continue
        check(task, family, model, marks)
        per_model[model["id"]] = marks
    rows = []
    for position, r in enumerate(requests):
        answers = {}
        for model_id, marks in per_model.items():
            m = marks[r["id"]]
            text = m["text"].strip()
            answers[model_id] = [text[:TEXT_LIMIT] + ("…" if len(text) > TEXT_LIMIT else ""),
                                 round(m["accuracy"], 6), m["instruction"],
                                 None if m["other"] is None else round(m["other"], 4), m["pair"]]
        kind = next(iter(per_model.values()))[r["id"]]["kind"] if per_model else None
        item = items[position]
        rows.append({"i": position, "id": r["id"], "kind": kind, "sample": item["id"], "sequence": item["sequence"],
                     "question": item["question"], "prompt": item["prompt"], "gold": item["gold"],
                     "images": [image["path"].removeprefix(BASE) for image in item["images"]], "answers": answers})
    return {"task": task, "family": family, "base": BASE, "models": list(per_model), "questions": rows}


def main() -> None:
    models = published()["models"]
    scorers = load_scorer()[0].func_mapping
    items = question_items()
    OUT.mkdir(exist_ok=True)
    for task in tasks():
        if task not in scorers:
            continue
        data = build_task(task, models, scorers, items[task])
        (OUT / f"{task}.json").write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
        print(f"{task:28} {len(data['questions']):5} questions  {len(data['models'])} models  ok")


if __name__ == "__main__":
    main()
