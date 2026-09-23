"""Score files -> results/rerun.json, the record every published number is read from.

A build refuses a model whose score file is not dataset-complete, whose answer records are partial, or whose answers
are newer than its score file (a rerun that has not been rescored).
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean, median
from typing import Any, TypedDict

from . import paths
from .aggregate import task_wins
from .registry import ModelInfo
from .usage import answer_records, model_usage, task_usage

SCHEMA_VERSION = 1
KIND = "complete_model_reruns"
SUMMARY_NOTE = "Means and medians are descriptive summaries across 28 task composites. They are not the paper's TOTAL score."
CAP_NOTE = "Models whose completion_cap is 512 were run under the archived scripts/archive/full-original-512.json; see docs/PROTOCOL.md."


class TaskResult(TypedDict):
    usage: dict
    score: float
    components: dict[str, Any]
    weights: dict[str, float]
    samples_scored: int
    questions_scored: int
    scorer_function: str
    dataset_complete: bool


class ModelRecord(TypedDict):
    id: str
    label: str
    model: str
    reasoning: str
    parameters: str
    lab: str
    featured: bool
    not_featured_reason: str | None
    size_rank: int
    color: str
    box_convention: str
    prompt: str
    transport: str
    declared: dict
    completion_cap: int
    truncated_answers: int | None
    carried_from_superseded_condition: int
    oversize_fallback_requests: int
    responses: int
    dataset_complete: bool
    source: str
    source_sha256: str
    summary: dict[str, Any]
    tasks: dict[str, TaskResult]
    usage: dict | None


class Record(TypedDict):
    schema_version: int
    kind: str
    generated_at: str
    dataset: dict[str, Any]
    scorer: dict
    experiment: dict[str, Any]
    summary_note: str
    task_order: list[str]
    models: list[ModelRecord]
    tied_tasks: list[dict]


class IncompleteRun(Exception):
    """A model's score file is not complete, its run records are partial, or its answers are newer than its score file."""


def load_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"Required result is unavailable: {path}")
    return json.loads(path.read_text())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score_path(model_id: str) -> Path:
    return paths.RESULTS / f"scores-{model_id}.json"


def transport_label(declared: dict) -> str:
    if declared["input_transport"] == "video_mp4":
        return "Lossless 1 FPS MP4 sequences and image URLs" + ("; receipted H.264 fallback above the provider body limit" if declared["oversize_fallback"] != "none" else "")
    return "Ordered image URLs for sequences and image URLs"


def reasoning_label(effort: str) -> str:
    return "off" if effort == "none" else effort


def check_score_file(result: dict, path: Path, task_order: Sequence[str] | None, scorer: dict | None) -> None:
    """Complete, every question answered, and the same task order and scoring code as the other score files."""
    if not result.get("dataset_complete"):
        raise IncompleteRun(f"Result is not dataset-complete: {path}")
    if result.get("request_success", {}).get("completed") != paths.QUESTIONS_PER_MODEL:
        raise IncompleteRun(f"Unexpected request coverage: {path}")
    if task_order is not None and list(result["tasks"]) != list(task_order):
        raise ValueError(f"Task order differs: {path}")
    if scorer is not None and result["scorer"]["sha256"] != scorer["sha256"]:
        raise ValueError(f"Scorer differs: {path}")


def require_complete(model_id: str, result: dict, records: Sequence[dict]) -> None:
    """Every question has an answer record, and no answer is newer than the score file built from them."""
    answered = {r["id"] for r in records}
    if len(answered) < paths.QUESTIONS_PER_MODEL:
        raise IncompleteRun(f"{model_id}: {len(answered):,} of {paths.QUESTIONS_PER_MODEL:,} questions have answer records; the run is partial")
    scored_at = datetime.fromtimestamp(result["generated_at"], tz=timezone.utc)
    newest = max(datetime.fromisoformat(r["timestamp"]) for r in records if r.get("timestamp"))
    if newest > scored_at:
        raise IncompleteRun(f"{model_id}: answers up to {newest.isoformat()} are newer than its score file ({scored_at.isoformat()}); rescore it first")


def compact_task(result: dict, records: Sequence[dict]) -> TaskResult:
    denominators = result["denominators"]
    return {"usage": task_usage(records), "score": result["score"], "components": result["components"], "weights": result["weights"],
            "samples_scored": denominators["samples_scored"], "questions_scored": denominators["questions_scored"],
            "scorer_function": result["scorer"]["function"], "dataset_complete": result["dataset_complete"]}


def model_record(info: ModelInfo, result: dict, records: Sequence[dict], source: Path) -> ModelRecord:
    by_task: dict[str, list[dict]] = {}
    for record in records:
        by_task.setdefault(record["task"], []).append(record)
    tasks = {task: compact_task(task_result, by_task.get(task, [])) for task, task_result in result["tasks"].items()}
    values = [task["score"] for task in tasks.values()]
    return {
        "id": info.id, "label": info.label, "model": result["model"], "reasoning": reasoning_label(result["declared"]["reasoning_effort"]),
        "parameters": info.parameters, "lab": info.lab, "featured": info.featured, "not_featured_reason": info.not_featured_reason,
        "size_rank": info.size_rank, "color": info.color, "box_convention": info.box_convention, "prompt": "original", "transport": transport_label(result["declared"]),
        "declared": result.get("declared") or {}, "completion_cap": result["protocol"]["max_tokens"],
        "truncated_answers": result.get("truncated_answers"),
        "carried_from_superseded_condition": result.get("carried_from_superseded_condition") or 0,
        "oversize_fallback_requests": result.get("oversize_fallback_requests", 0),
        "responses": result["request_success"]["completed"], "dataset_complete": True,
        "source": paths.relative(source), "source_sha256": sha256(source),
        "summary": {"unweighted_mean_task_score": mean(values), "median_task_score": median(values),
                    "minimum": min(tasks, key=lambda task: tasks[task]["score"]), "maximum": max(tasks, key=lambda task: tasks[task]["score"])},
        "tasks": tasks, "usage": model_usage(info.id, records),
    }


def build_record(spec: dict, registry: dict[str, ModelInfo], *, allow_incomplete: bool = False, runs: Path = paths.RUNS) -> Record:
    """Every protocol model with a score file, in protocol order. Models with no score file yet are left out."""
    models: list[ModelRecord] = []
    task_order: list[str] | None = None
    scorer: dict | None = None
    generated_at = 0.0
    for spec_model in spec["models"]:
        path = score_path(spec_model["id"])
        if not path.is_file():
            continue
        result = load_json(path)
        try:
            check_score_file(result, path, task_order, scorer)
            records = answer_records(spec_model["id"], runs)
            require_complete(spec_model["id"], result, records)
        except IncompleteRun:
            if allow_incomplete:
                continue
            raise
        task_order, scorer = task_order or list(result["tasks"]), scorer or result["scorer"]
        models.append(model_record(registry[spec_model["id"]], result, records, path))
        generated_at = max(generated_at, result["generated_at"])
    if task_order is None or scorer is None:
        raise IncompleteRun("No complete score files")
    wins, ties = task_wins({m["id"]: {t: r["score"] for t, r in m["tasks"].items()} for m in models}, task_order)
    for m in models:
        m["summary"]["task_wins"] = wins[m["id"]]
    protocol = load_json(paths.PROTOCOL)
    return {
        "schema_version": SCHEMA_VERSION, "kind": KIND,
        "generated_at": datetime.fromtimestamp(generated_at, tz=timezone.utc).isoformat(),
        "dataset": {"repository": "depth2world/VLADBench", "revision": paths.DATASET_REVISION, "tasks": len(task_order),
                    "questions_per_model": paths.QUESTIONS_PER_MODEL, "responses": paths.QUESTIONS_PER_MODEL * len(models)},
        "scorer": scorer,
        "experiment": {"specification": paths.relative(paths.PROTOCOL), "specification_sha256": sha256(paths.PROTOCOL),
                       "protocol": protocol["protocol"], "note": CAP_NOTE},
        "summary_note": SUMMARY_NOTE,
        "task_order": task_order,
        "models": models,
        "tied_tasks": [{"task": tie.task, "models": list(tie.model_ids)} for tie in ties],
    }


def load_record(path: Path = paths.RECORD) -> Record:
    return load_json(path)


def write_record(record: Record, path: Path = paths.RECORD) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return path
