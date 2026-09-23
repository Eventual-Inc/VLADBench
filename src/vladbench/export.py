"""Parquet tables for the Hugging Face dataset, written to results/dataset/.

  models       one row per complete model (label, protocol declarations, spend, latency summary)
  tasks        one row per task (category, group, scorer function, released weights)
  questions    one row per released question (prompt, pinned image URLs, gold reference)
  answers      one row per model x question (answer text, finish reason, serving host, tokens, cost, latency)
  task_scores  one row per model x task (released scorer components and composite)
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from . import paths
from .record import Record, load_json
from .run import read_jsonl

TABLES: tuple[str, ...] = ("models", "tasks", "questions", "answers", "task_scores")


def usage_field(record: dict, *keys: str):
    value = record.get("usage") or {}
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def model_rows(record: Record) -> list[dict]:
    rows = []
    for model in record["models"]:
        scores = load_json(paths.ROOT / model["source"])
        usage = model.get("usage") or {}
        latency = usage.get("latency_seconds") or {}
        declared = model["declared"]
        rows.append({
            "model_id": model["id"], "label": model["label"], "provider_model": model["model"], "parameters": model.get("parameters", "undisclosed"),
            "lab": model.get("lab"), "featured": model.get("featured", True),
            "reasoning_effort": declared["reasoning_effort"], "input_transport": declared["input_transport"],
            "single_frame_policy": declared["single_frame_policy"], "oversize_fallback": declared["oversize_fallback"],
            "completion_cap": model["completion_cap"], "truncated_answers": model["truncated_answers"],
            "oversize_fallback_requests": model["oversize_fallback_requests"], "protocol_complete": bool(scores.get("protocol_complete")),
            "carried_from_512": scores.get("carried_from_superseded_condition") or 0,
            "cost_usd": usage.get("cost_usd"), "cost_basis": "provider receipts summed per answer",
            "input_cost_per_frame_usd": usage.get("input_cost_per_frame_usd"), "output_cost_per_query_usd": usage.get("output_cost_per_query_usd"),
            "cost_per_video_hour_usd": usage.get("cost_per_video_hour_usd"),
            "latency_p25": latency.get("p25"), "latency_p50": latency.get("p50"), "latency_p75": latency.get("p75"), "latency_p95": latency.get("p95"),
            "mean_task_score": model["summary"]["unweighted_mean_task_score"], "median_task_score": model["summary"]["median_task_score"],
            "task_wins": model["summary"]["task_wins"],
        })
    return rows


def task_rows(record: Record) -> list[dict]:
    catalog = load_json(paths.CATALOG)
    place = {name: (category, group) for category, groups in catalog.items() for group, names in groups.items() for name in names}
    first = load_json(paths.ROOT / record["models"][0]["source"])["tasks"]
    rows = []
    for task in record["task_order"]:
        result, weights = first[task], first[task]["weights"]
        rows.append({"task": task, "category": place[task][0], "group": place[task][1], "scorer_function": result["scorer"]["function"],
                     "accuracy_name": result["components"]["accuracy_name"], "other_name": result["components"]["other_name"],
                     "weight_other": weights["other"], "weight_accuracy": weights["accuracy"], "weight_instruction": weights["instruction_following"],
                     "samples": result["dataset_totals"]["samples"], "questions": result["dataset_totals"]["questions"]})
    return rows


def question_rows(task_order: Sequence[str]) -> list[dict]:
    from .requests import questions

    rows = []
    for task in task_order:
        for q in questions(task):
            sample = q["sample"]
            rows.append({"question_id": q["id"], "task": task, "sample_id": q["sample_id"], "sample_index": q["sample_index"],
                         "question_index": q["question_index"], "sequence": bool(q["sequence"]), "country": sample.get("country"),
                         "prompt": q["prompt"], "raw_question": q["raw_question"], "reference": str(sample["reference"][q["question_index"]]),
                         "image_urls": list(q["image_urls"]), "frames": len(q["image_urls"])})
    return rows


def answer_row(model_id: str, record: dict, question_id: str, condition: str) -> dict:
    answer = record.get("answer") or ""
    response = record.get("response") or {}
    return {"model_id": model_id, "question_id": question_id, "answer": answer, "answer_chars": len(answer),
            "finish_reason": record.get("finish_reason"), "attempt": int(record.get("attempt") or 1),
            "served_provider": response.get("provider"), "served_model": response.get("model"),
            "elapsed_seconds": record.get("elapsed_seconds"), "prompt_tokens": usage_field(record, "prompt_tokens"),
            "completion_tokens": usage_field(record, "completion_tokens"),
            "reasoning_tokens": usage_field(record, "completion_tokens_details", "reasoning_tokens"),
            "cost_usd": usage_field(record, "cost"), "condition": condition, "lossy_fallback": bool(record.get("lossy_fallback")),
            "protocol_sha256": record.get("protocol_sha256"), "timestamp": record.get("timestamp")}


def latest_answers(model_id: str, valid: set[str], runs: Path = paths.RUNS) -> dict[str, dict]:
    """The last record per question id, across the model's task files in name order."""
    latest = {}
    for path in sorted((runs / model_id).glob("*.jsonl")):
        for record in read_jsonl(path):
            if record["id"] in valid:
                latest[record["id"]] = answer_row(model_id, record, record["id"], record.get("condition", "full-original"))
    return latest


def answer_rows(record: Record, question_ids: set[str], runs: Path = paths.RUNS) -> list[dict]:
    rows = []
    for model in record["models"]:
        found = latest_answers(model["id"], question_ids, runs)
        if len(found) != len(question_ids):
            raise ValueError(f"{model['id']}: {len(found)} answers for {len(question_ids)} questions")
        rows.extend(found.values())
    return rows


def score_rows(record: Record) -> list[dict]:
    rows = []
    for model in record["models"]:
        for task, result in model["tasks"].items():
            c, w = result["components"], result["weights"]
            rows.append({"model_id": model["id"], "task": task, "score": result["score"], "accuracy": c["accuracy"],
                         "instruction_following": c["instruction_following"], "other": c["other"],
                         "weight_other": w["other"], "weight_accuracy": w["accuracy"], "weight_instruction": w["instruction_following"],
                         "samples_scored": result["samples_scored"], "questions_scored": result["questions_scored"]})
    return rows


def write_table(name: str, rows: list[dict], out: Path) -> Path:
    import pyarrow as pa
    import pyarrow.parquet as pq

    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.parquet"
    pq.write_table(pa.Table.from_pylist(rows), path, compression="zstd")
    return path


def export(record: Record, out: Path = paths.DATASET, runs: Path = paths.RUNS) -> list[Path]:
    questions = question_rows(record["task_order"])
    tables = {"models": model_rows(record), "tasks": task_rows(record), "questions": questions,
              "answers": answer_rows(record, {q["question_id"] for q in questions}, runs), "task_scores": score_rows(record)}
    return [write_table(name, tables[name], out) for name in TABLES]
