"""Export the published results as parquet tables for the HF dataset.

Tables, written to results/dataset/:
  models       one row per complete model (label, protocol declarations, spend, latency summary)
  tasks        one row per task (category, group, scorer function, released weights)
  questions    one row per released question (prompt, pinned image URLs, gold reference)
  answers      one row per model x question (answer text, finish reason, tokens, cost, latency)
  task_scores  one row per model x task (released scorer components and composite)
"""

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/dataset"
RERUN = ROOT / "results/rerun.json"


def load_json(path: Path):
    return json.loads(path.read_text())


def usage_field(record: dict, *keys):
    value = record.get("usage") or {}
    for key in keys:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def model_rows(rerun: dict) -> list[dict]:
    rows = []
    for model in rerun["models"]:
        scores = load_json(ROOT / model["source"])
        usage = model.get("usage") or {}
        latency = usage.get("latency_seconds") or {}
        rows.append({
            "model_id": model["id"], "label": model["label"], "provider_model": model["model"], "parameters": model.get("parameters", "undisclosed"), "lab": model.get("lab"), "featured": model.get("featured", True),
            "reasoning_effort": model["declared"]["reasoning_effort"], "input_transport": model["declared"]["input_transport"],
            "single_frame_policy": model["declared"]["single_frame_policy"], "oversize_fallback": model["declared"]["oversize_fallback"],
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


def task_rows(rerun: dict) -> list[dict]:
    catalog = load_json(ROOT / "original/all_task.json")
    place = {name: (category, group) for category, groups in catalog.items() for group, names in groups.items() for name in names}
    first = load_json(ROOT / rerun["models"][0]["source"])["tasks"]
    rows = []
    for task in rerun["task_order"]:
        result, weights = first[task], first[task]["weights"]
        rows.append({"task": task, "category": place[task][0], "group": place[task][1], "scorer_function": result["scorer"]["function"],
                     "accuracy_name": result["components"]["accuracy_name"], "other_name": result["components"]["other_name"],
                     "weight_other": weights["other"], "weight_accuracy": weights["accuracy"], "weight_instruction": weights["instruction_following"],
                     "samples": result["dataset_totals"]["samples"], "questions": result["dataset_totals"]["questions"]})
    return rows


def question_rows(task_order: list[str]) -> list[dict]:
    from vladbench.requests import questions

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
    return {"model_id": model_id, "question_id": question_id, "answer": answer, "answer_chars": len(answer),
            "finish_reason": record.get("finish_reason"), "attempt": int(record.get("attempt") or 1),
            "served_provider": (record.get("response") or {}).get("provider"), "served_model": (record.get("response") or {}).get("model"),
            "elapsed_seconds": record.get("elapsed_seconds"), "prompt_tokens": usage_field(record, "prompt_tokens"),
            "completion_tokens": usage_field(record, "completion_tokens"),
            "reasoning_tokens": usage_field(record, "completion_tokens_details", "reasoning_tokens"),
            "cost_usd": usage_field(record, "cost"), "condition": condition, "lossy_fallback": bool(record.get("lossy_fallback")),
            "protocol_sha256": record.get("protocol_sha256"), "timestamp": record.get("timestamp")}


def live_answers(model_id: str, valid: set[str]) -> dict[str, dict]:
    from vladbench.run import RUNS, read_jsonl

    folder = RUNS / "full-original" / model_id
    latest = {}
    for path in sorted(folder.glob("*.jsonl")):
        for record in read_jsonl(path):
            if record["id"] in valid:
                latest[record["id"]] = answer_row(model_id, record, record["id"], record.get("condition", "full-original"))
    return latest


def answer_rows(rerun: dict, question_ids: set[str]) -> list[dict]:
    rows = []
    for model in rerun["models"]:
        found = live_answers(model["id"], question_ids)
        if len(found) != len(question_ids):
            raise ValueError(f"{model['id']}: {len(found)} answers for {len(question_ids)} questions")
        rows.extend(found.values())
    return rows


def score_rows(rerun: dict) -> list[dict]:
    rows = []
    for model in rerun["models"]:
        for task, result in model["tasks"].items():
            c, w = result["components"], result["weights"]
            rows.append({"model_id": model["id"], "task": task, "score": result["score"], "accuracy": c["accuracy"],
                         "instruction_following": c["instruction_following"], "other": c["other"],
                         "weight_other": w["other"], "weight_accuracy": w["accuracy"], "weight_instruction": w["instruction_following"],
                         "samples_scored": result["samples_scored"], "questions_scored": result["questions_scored"]})
    return rows


def write(name: str, rows: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, OUT / f"{name}.parquet", compression="zstd")
    print(f"{name}: {table.num_rows} rows, {table.num_columns} columns")


def main():
    rerun = load_json(RERUN)
    questions = question_rows(rerun["task_order"])
    write("models", model_rows(rerun))
    write("tasks", task_rows(rerun))
    write("questions", questions)
    write("answers", answer_rows(rerun, {q["question_id"] for q in questions}))
    write("task_scores", score_rows(rerun))


if __name__ == "__main__":
    main()
