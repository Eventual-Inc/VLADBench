"""Build compact, static result assets for the benchmark companion."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean, median


ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = ROOT / "results/rerun.json"
RESULTS = ROOT / "results"
SPECIFICATION = ROOT / "results/protocols/full-original.json"
LABELS = {"gemini38": "Gemini 3.8 Flash", "qwen38max": "Qwen 3.8 Max",
          "muse13": "Muse Spark 1.3", "minimax3": "MiniMax M3", "gemma431": "Gemma 4 31B", "luna56": "GPT-5.6 Luna", "astra6": "GPT-6 Astra", "sol56": "GPT-5.6 Sol", "gemini25lite": "Gemini 2.5 Flash Lite", "rekaedge": "Reka Edge", "qwen38or": "Qwen 3.8 27B", "qwen36or": "Qwen 3.6 35B A3B",
          "opus55": "Claude Opus 5.5", "luna6": "GPT-6 Luna", "sol6": "GPT-6 Sol"}
# Parameter counts from the model cards where published (Hugging Face safetensors totals or provider descriptions, 2026-09-15).
PARAMETERS = {"gemini38": "undisclosed", "qwen38max": "2.4T MoE",
              "muse13": "undisclosed", "minimax3": "undisclosed", "gemma431": "30.7B dense", "luna56": "undisclosed", "astra6": "undisclosed",
              "sol56": "undisclosed", "gemini25lite": "undisclosed", "rekaedge": "7B", "qwen38or": "27B dense", "qwen36or": "35B MoE, 3B active",
              "opus55": "undisclosed", "luna6": "undisclosed", "sol6": "undisclosed"}
# Lab and a within-lab size rank (smallest first) for grouping columns; undisclosed sizes are ranked by product tier.
LAB = {"qwen38max": "Alibaba", "gemma431": "Google", "gemini25lite": "Google",
       "gemini38": "Google", "luna56": "OpenAI", "sol56": "OpenAI", "astra6": "OpenAI", "muse13": "Meta", "minimax3": "MiniMax",
       "rekaedge": "Reka", "qwen38or": "Alibaba", "qwen36or": "Alibaba",
       "opus55": "Anthropic", "luna6": "OpenAI", "sol6": "OpenAI"}
SIZE_RANK = {"qwen38or": 1, "qwen36or": 2, "qwen38max": 4, "gemma431": 1, "gemini25lite": 2, "gemini38": 3, "luna56": 1, "sol56": 2, "astra6": 3,
             "muse13": 1, "minimax3": 1, "rekaedge": 1, "opus55": 1, "luna6": 1, "sol6": 2}
# Complete models kept in the dataset and the full tables but left out of the headline figure and leaderboard.
NOT_FEATURED = {"rekaedge": "7B edge model scoring 39.8; kept in the data, left out of the headline figures as an outlier"}
REVISION = "1895f22252f9a702fed95334c8e3b60280b4c626"
BASE = f"https://huggingface.co/datasets/depth2world/VLADBench/resolve/{REVISION}/"


def transport_label(declared: dict) -> str:
    if declared["input_transport"] == "video_mp4":
        return "Lossless 1 FPS MP4 sequences and image URLs" + ("; receipted H.264 fallback above the provider body limit" if declared["oversize_fallback"] != "none" else "")
    return "Ordered image URLs for sequences and image URLs"


def score_files() -> list[Path]:
    """Score files in results/, in the specification's model order; models missing from the specification sort last."""
    order = [m["id"] for m in load_json(SPECIFICATION)["models"]]
    rank = lambda path: order.index(path.stem[len("scores-"):]) if path.stem[len("scores-"):] in order else len(order)
    return sorted(RESULTS.glob("scores-*.json"), key=rank)


def specification_entry(path: Path, result: dict) -> dict:
    model_id = result["model_id"]
    effort = result["declared"]["reasoning_effort"]
    return {"id": model_id, "label": LABELS.get(model_id, model_id), "score_path": str(path.relative_to(ROOT)),
            "reasoning": "off" if effort == "none" else effort, "transport": transport_label(result["declared"])}


def run_specifications() -> list[dict]:
    """One entry per complete score file."""
    results = [(path, load_json(path)) for path in score_files()]
    return [specification_entry(path, result) for path, result in results if result.get("dataset_complete")]


def load_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Required result is unavailable: {path}")
    return json.loads(path.read_text())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def task_usage(records: list[dict]) -> dict:
    """Billed cost and latency of one model's answers on one task."""
    costs = [(r.get("usage") or {}).get("cost") for r in records]
    known = [c for c in costs if c is not None]
    seconds = sorted(r["elapsed_seconds"] for r in records if r.get("elapsed_seconds") is not None)
    return {"cost_usd": sum(known) if known else None, "answers": len(records),
            "latency_p50": seconds[len(seconds) // 2] if seconds else None}


def compact_task(result: dict, records: list[dict] = ()) -> dict:
    denominators = result["denominators"]
    scorer = result["scorer"]
    return {
        "usage": task_usage(list(records)),
        "score": result["score"],
        "components": result["components"],
        "weights": result["weights"],
        "samples_scored": denominators["samples_scored"],
        "questions_scored": denominators["questions_scored"],
        "scorer_function": scorer["function"],
        "dataset_complete": result["dataset_complete"],
    }


def percentile(values: list, q: float) -> float:
    return values[min(len(values) - 1, int(len(values) * q))]


def latency_summary(seconds: list) -> dict | None:
    if not seconds:
        return None
    seconds = sorted(seconds)
    return {"n": len(seconds), "p25": percentile(seconds, .25), "p50": percentile(seconds, .5),
            "p75": percentile(seconds, .75), "p95": percentile(seconds, .95), "max": seconds[-1]}


def answer_records(model_id: str) -> list[dict]:
    from vladbench.run import RUNS, read_jsonl
    folder = RUNS / "full-original" / model_id
    if not folder.is_dir():
        return []
    return [r for path in sorted(folder.glob("*.jsonl")) for r in read_jsonl(path)]


def frames_per_question() -> dict[str, int]:
    """Frames sent for every sequence question, keyed by question id; single-image questions are absent."""
    from vladbench.requests import questions, tasks
    return {q["id"]: len(q["image_urls"]) for task in tasks() for q in questions(task) if q["sequence"]}


FRAMES = None


def detail(record: dict, key: str) -> float:
    return ((record.get("usage") or {}).get("cost_details") or {}).get(key) or 0.0


def video_cost(model_id: str, records: list[dict]) -> dict:
    """Metered video question answering at 720p: the fitted tokeniser rule, the sweep's effective prices, and the
    measured output tokens per query, under the post's workload (1 FPS, non-overlapping 8-frame clips, one question each)."""
    from vladbench.metering import RULES, effective_prices, hourly_cost, frame_tokens
    rule = RULES.get(model_id)
    if rule is None or not all("cost_details" in (r.get("usage") or {}) for r in records):
        return {"input_cost_per_frame_usd": None, "output_cost_per_query_usd": None, "cost_per_video_hour_usd": None}
    prices = effective_prices(records)
    output_tokens = sum((r.get("usage") or {}).get("completion_tokens", 0) for r in records) / len(records)
    hour = hourly_cost(rule, prices, width=1280, height=720, fps=1.0, frames_per_query=8, output_tokens_per_query=output_tokens)
    return {"input_cost_per_frame_usd": frame_tokens(rule, 1280, 720, 8) * prices.prompt,
            "output_cost_per_query_usd": output_tokens * prices.completion,
            "cost_per_video_hour_usd": hour["total_usd"], "tokens_per_frame_720p": hour["tokens_per_frame"],
            "metering": {"rule": {"kind": rule.kind, "patch": rule.patch, "multiplier": rule.multiplier, "tokens_per_pixel": rule.tokens_per_pixel,
                                  "tokens_per_frame": rule.tokens_per_frame},
                         "prompt_price": prices.prompt, "completion_price": prices.completion, "output_tokens_per_query": output_tokens,
                         "text_tokens": 110},
            "video_cost_basis": "1280x720 at 1 FPS in non-overlapping 8-frame clips, one question each: 3,600 frames and 450 queries an hour; fitted tokeniser rule (vladbench.metering), the sweep's effective per-token prices, measured output tokens per query including reasoning"}


def flat_usage(model_id: str) -> dict | None:
    """Cost and latency from the answer files: provider-billed cost per answer, summed over the sweep."""
    records = answer_records(model_id)
    if not records:
        return None
    known = [c for c in ((r.get("usage") or {}).get("cost") for r in records) if c is not None]
    seconds = [r["elapsed_seconds"] for r in records if r.get("elapsed_seconds") is not None]
    return {"cost_usd": sum(known) if known else None, "cost_receipts": len(known), "answers": len(records),
            "latency_seconds": latency_summary(seconds), **video_cost(model_id, records)}


def check_result(result: dict, score_path: Path, task_order: list | None, scorer: dict | None) -> None:
    """Every score file must be complete, cover every question, and share the task order and scoring code."""
    if not result.get("dataset_complete"):
        raise ValueError(f"Result is not dataset-complete: {score_path}")
    if result.get("request_success", {}).get("completed") != 11193:
        raise ValueError(f"Unexpected request coverage: {score_path}")
    if task_order is not None and list(result["tasks"]) != task_order:
        raise ValueError(f"Task order differs: {score_path}")
    if scorer is not None and result["scorer"]["sha256"] != scorer["sha256"]:
        raise ValueError(f"Scorer differs: {score_path}")


def model_entry(specification: dict, result: dict, score_path: Path) -> dict:
    model_id = specification["id"]
    by_task = {}
    for record in answer_records(model_id):
        by_task.setdefault(record["task"], []).append(record)
    tasks = {task: compact_task(task_result, by_task.get(task, [])) for task, task_result in result["tasks"].items()}
    values = [task["score"] for task in tasks.values()]
    return {
        "id": model_id, "label": specification["label"], "model": result["model"], "reasoning": specification["reasoning"],
        "parameters": PARAMETERS.get(model_id, "undisclosed"), "lab": LAB.get(model_id, "Other"),
        "featured": model_id not in NOT_FEATURED, "not_featured_reason": NOT_FEATURED.get(model_id),
        "size_rank": SIZE_RANK.get(model_id, 99), "prompt": "original", "transport": specification["transport"],
        "declared": result.get("declared"), "completion_cap": result["protocol"]["max_tokens"],
        "truncated_answers": result.get("truncated_answers"),
        "carried_from_superseded_condition": result.get("carried_from_superseded_condition") or 0,
        "oversize_fallback_requests": result.get("oversize_fallback_requests", 0),
        "responses": result["request_success"]["completed"], "dataset_complete": True,
        "source": specification["score_path"], "source_sha256": sha256(score_path),
        "summary": {"unweighted_mean_task_score": mean(values), "median_task_score": median(values),
                    "minimum": min(tasks, key=lambda task: tasks[task]["score"]), "maximum": max(tasks, key=lambda task: tasks[task]["score"])},
        "tasks": tasks, "usage": flat_usage(model_id),
    }


def task_wins(models: list[dict], task_order: list[str]) -> list[dict]:
    """Count sole winners per task into each model's summary; return the tasks with a tie for first."""
    tied = []
    for task in task_order:
        best = max(model["tasks"][task]["score"] for model in models)
        winners = [model for model in models if abs(model["tasks"][task]["score"] - best) < 1e-9]
        if len(winners) == 1:
            winners[0]["summary"]["task_wins"] = winners[0]["summary"].get("task_wins", 0) + 1
        else:
            tied.append({"task": task, "models": [model["id"] for model in winners]})
    for model in models:
        model["summary"].setdefault("task_wins", 0)
    return tied


def build_rerun() -> dict:
    models, task_order, scorer, generated_at = [], None, None, 0.0
    for specification in run_specifications():
        score_path = ROOT / specification["score_path"]
        result = load_json(score_path)
        check_result(result, score_path, task_order, scorer)
        task_order, scorer = task_order or list(result["tasks"]), scorer or result["scorer"]
        models.append(model_entry(specification, result, score_path))
        generated_at = max(generated_at, result["generated_at"])
    tied_tasks = task_wins(models, task_order)
    return {
        "schema_version": 1,
        "kind": "complete_model_reruns",
        "generated_at": datetime.fromtimestamp(generated_at, tz=timezone.utc).isoformat(),
        "dataset": {"repository": "depth2world/VLADBench", "revision": REVISION, "tasks": len(task_order),
                    "questions_per_model": 11193, "responses": 11193 * len(models)},
        "scorer": scorer,
        "experiment": {"specification": str(SPECIFICATION.relative_to(ROOT)),
                       "specification_sha256": hashlib.sha256(SPECIFICATION.read_bytes()).hexdigest(),
                       "protocol": load_json(SPECIFICATION)["protocol"],
                       "note": "Models whose completion_cap is 512 were run under the archived scripts/archive/full-original-512.json; see docs/PROTOCOL.md."},
        "summary_note": ("Means and medians are descriptive summaries across 28 task composites. "
                         "They are not the paper's TOTAL score."),
        "task_order": task_order,
        "models": models,
        "tied_tasks": tied_tasks,
    }


def question_item(folder: Path, name: str, sample: dict, sample_index: int, index: int) -> dict:
    """One released question with its pinned frame URLs and gold answer."""
    from urllib.parse import quote

    raw = sample["questions"][index]
    selector, text = (part.strip() for part in raw.split(";", 1))
    sequence = selector.startswith("[") and selector.endswith("]")
    paths = [folder / name / sample["sequence"] / f for f in sample[selector[1:-1]]] if sequence else [folder / name / selector]
    prefix = f"The {'sequence' if sequence else 'image'} is from {sample['country']}. "
    return dict(id=sample.get("id", sample.get("sequence", str(sample_index + 1))), sequence=sample.get("sequence"),
                question=index + 1, raw=raw, prompt=prefix + text, selector=selector, gold=sample["reference"][index],
                images=[dict(path=BASE + quote(p.as_posix(), safe="/"), exists=True, remote=True) for p in paths])


def task_input(category: str, group: str, name: str, scorer: str | None) -> dict:
    from urllib.parse import quote

    folder = Path(category) / group
    source = folder / (name + "_E.json")
    metadata = ROOT / "results/audit/gold_metadata" / source
    samples = json.loads(metadata.read_text()) if metadata.exists() else []
    items = [question_item(folder, name, sample, sample_index, index)
             for sample_index, sample in enumerate(samples) for index in range(len(sample["questions"]))]
    return dict(name=name, category=category, group=group, source=BASE + quote(source.as_posix(), safe="/"),
                revision=REVISION, scorer=scorer, samples=len(samples), items=items)


def build_task_inputs() -> list:
    """Every released question, gold answer, and pinned image URL for the results page; no model calls."""
    from vladbench.scoring import load_scorer

    catalog = load_json(ROOT / "original/all_task.json")
    # The preserved source only compiles with its disclosed syntax repair; reuse the scorer loader.
    scorers = {task: fn.__name__ for task, fn in load_scorer()[0].func_mapping.items()}
    described = load_json(ROOT / "results/audit/task-descriptions.json")
    tasks = [task_input(category, group, name, scorers.get(name))
             for category, groups in catalog.items() for group, names in groups.items() for name in names]
    for task in tasks:
        rule = described["scoring"].get(task["scorer"] or "", {})
        task.update(description=described["tasks"].get(task["name"], ""), scoring_label=rule.get("label", ""), scoring_rule=rule.get("rule", ""))
    return tasks


def write_javascript(path: Path, variable: str, value):
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    safe_payload = payload.replace("<", "\\u003c")
    path.write_text(f"window.{variable} = {safe_payload};\n")


def main():
    audit = load_json(ROOT / "results/audit/gold-distributions.json")
    published = load_json(ROOT / "results/audit/published-results-2025.json")
    rerun = build_rerun()

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(
        json.dumps(rerun, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    inputs = build_task_inputs()
    write_javascript(ROOT / "task-review-data.js", "REVIEW_DATA", inputs)
    # Same task list without the per-question items: what blog embeds load instead of the 16 MB file.
    write_javascript(ROOT / "task-review-tasks.js", "REVIEW_DATA", [dict(task, items=[]) for task in inputs])
    write_javascript(ROOT / "task-review-audit.js", "REVIEW_AUDIT", audit)
    write_javascript(ROOT / "task-review-published.js", "PUBLISHED", published)
    write_javascript(ROOT / "task-review-results.js", "FULL_RESULTS", rerun)
    print(
        f"Exported {len(rerun['models'])} complete models, "
        f"{len(rerun['task_order'])} tasks, "
        f"{rerun['dataset']['responses']} responses."
    )


if __name__ == "__main__":
    main()
