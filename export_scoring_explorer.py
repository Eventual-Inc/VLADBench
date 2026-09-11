#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.24"]
# ///
"""Build scoring-data.js for scoring-explorer.html from output/Vehicle_Cutin."""

from __future__ import annotations

import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path

from evaluate_utils import (
    clean_string,
    convert_if_number,
    extract_options,
    remove_symbols,
)

TASK = "Vehicle_Cutin"
EXCLUDED = {("3_1_1_86", 2)}
IMAGE_PREFIX = (
    "data/VLADBench/Target_Attribute_Comprehension/Intention_Judgment/Vehicle_Cutin"
)
MODEL_NAMES = {
    "GLM-5.3-Flash": "GLM-5.3 Flash",
    "Gemini-3.8-Flash": "Gemini 3.8 Flash",
    "Gemma-4-26B-A4B-it": "Gemma-4-26B",
    "Gemma-4-31B-it": "Gemma-4-31B",
    "Gemma-4-E2B-it": "Gemma-4-E2B",
    "Gemma-4-E4B-it": "Gemma-4-E4B",
    "GPT-5.6-Luna": "GPT-5.6 Luna",
    "GPT-6-Astra": "GPT-6 Astra",
    "Kimi-K3": "Kimi K3",
    "Qwen3.5-0.8B": "Qwen 3.5-0.8B",
    "Qwen3.5-35B-A3B-FP8": "Qwen 3.5-FP8",
    "Qwen3.6-35B-A3B": "Qwen 3.6",
    "Qwen3.6-35B-A3B-FP8": "Qwen 3.6-FP8",
    "Qwen3.6-35B-A3B-FP8-Finetune": "Finetune FP8",
    "Qwen3.8-27B": "Qwen 3.8",
}
VEHICLE_RE = re.compile(
    r"does the (.+?) (?:in the image|within the red box)",
    re.IGNORECASE,
)


def summarize_metadata(items: list[dict]) -> dict:
    """Summarize request timing and usage for one benchmark run."""
    if not items:
        return {
            "wall_seconds": None,
            "median_seconds": None,
            "latency_p25_seconds": None,
            "latency_p75_seconds": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "reasoning_tokens": None,
            "retries": None,
        }

    latencies = [item["api_elapsed_seconds"] for item in items]
    if len(latencies) == 1:
        latency_p25 = latency_p75 = latencies[0]
    else:
        quartiles = statistics.quantiles(latencies, n=4, method="inclusive")
        latency_p25, latency_p75 = quartiles[0], quartiles[2]

    started = min(datetime.fromisoformat(item["started_at"]) for item in items)
    completed = max(
        datetime.fromisoformat(item["completed_at"]) for item in items
    )

    def sum_optional(field: str) -> int | None:
        values = [item.get(field) for item in items]
        present = [value for value in values if value is not None]
        return sum(present) if present else None

    return {
        "wall_seconds": (completed - started).total_seconds(),
        "median_seconds": statistics.median(latencies),
        "latency_p25_seconds": latency_p25,
        "latency_p75_seconds": latency_p75,
        "prompt_tokens": sum_optional("prompt_tokens"),
        "completion_tokens": sum_optional("completion_tokens"),
        "reasoning_tokens": sum_optional("reasoning_tokens"),
        "retries": sum(
            max(0, (item.get("attempts") or 1) - 1) for item in items
        ),
    }


def grade(pred: str, ref, question: str) -> tuple[bool, bool, str]:
    ques_nopath = "".join(question.lower().split(";")[1:])
    tips = extract_options(ques_nopath)
    cleaned = clean_string(remove_symbols(pred or "")).lower()
    reference = clean_string(convert_if_number(ref)).lower()
    parts = cleaned.split("', '")
    obey = False
    correct = False
    if len(parts) == 1:
        if "".join(cleaned.split(";")) in ques_nopath:
            obey = True
        if cleaned == reference:
            correct = True
        elif reference in cleaned and reference in tips:
            tips.remove(reference)
            if not any(tip in cleaned for tip in tips):
                correct = True
    return correct, obey, cleaned


def parse_stem(stem: str) -> dict:
    prompt = "reword" if stem.endswith("-reword") else "official"
    key = stem.removesuffix("-reword")
    think = "off"
    if key.endswith("-reasoning"):
        key = key.removesuffix("-reasoning")
        think = "on"
        if key.endswith("-low"):
            key = key.removesuffix("-low")
            think = "low"
    return {
        "file": stem,
        "model": MODEL_NAMES.get(key, key),
        "think": think,
        "prompt": prompt,
    }


def main() -> None:
    root = Path(__file__).resolve().parent
    meta_path = (
        root
        / "data/VLADBench/Target_Attribute_Comprehension/Intention_Judgment"
        / "Vehicle_Cutin_E.json"
    )
    clips_src = json.loads(meta_path.read_text(encoding="utf-8"))
    clips = []
    for sample in clips_src:
        vehicle_match = VEHICLE_RE.search(sample["questions"][0])
        questions = []
        for index, (raw, gold) in enumerate(
            zip(sample["questions"], sample["reference"])
        ):
            gold_text = clean_string(convert_if_number(gold)).lower()
            kind = "judge" if gold_text in {"yes", "no"} else "reason"
            _, text = raw.split(";", 1)
            questions.append(
                {
                    "kind": kind,
                    "gold": gold_text,
                    "text": text.strip(),
                    "excluded": (sample["id"], index) in EXCLUDED,
                    "commute": gold_text == "commuting efficiency",
                }
            )
        last_raw = sample["image_path"][-1]
        last_plot = sample["image_path_plot"][-1]
        clips.append(
            {
                "id": sample["id"],
                "seq": sample["sequence"],
                "venue": sample["venue"],
                "country": sample["country"],
                "vehicle": vehicle_match.group(1) if vehicle_match else "vehicle",
                "raw": f"{IMAGE_PREFIX}/{sample['sequence']}/{last_raw}",
                "plot": f"{IMAGE_PREFIX}/{sample['sequence']}/{last_plot}",
                "questions": questions,
            }
        )

    runs = []
    for path in sorted((root / "output" / TASK).glob("*.json")):
        if "smoke" in path.stem:
            continue
        samples = json.loads(path.read_text(encoding="utf-8"))
        info = parse_stem(path.stem)
        prompt_variants = {
            sample.get("prompt_variant")
            for sample in samples
            if sample.get("prompt_variant")
        }
        if prompt_variants == {"cutin-reword"}:
            info["prompt"] = "reword"
        answers = []
        completed = 0
        scored = 0
        run_metadata = []
        by_id = {sample["id"]: sample for sample in samples}
        for clip in clips:
            sample = by_id.get(clip["id"])
            clip_answers = []
            for index, question in enumerate(clip["questions"]):
                pred = ""
                metadata = None
                question_sent = question["text"]
                if sample is not None and index < len(sample.get("prediction", [])):
                    pred = sample["prediction"][index] or ""
                    sent = sample.get("questions_sent", sample["questions"])[index]
                    _, question_sent = sent.split(";", 1)
                    question_sent = question_sent.strip()
                    completion_metadata = sample.get("completion_metadata", [])
                    if index < len(completion_metadata):
                        metadata = completion_metadata[index]
                correct, obey, cleaned = grade(
                    pred,
                    clip["questions"][index]["gold"],
                    sample["questions"][index] if sample else "",
                )
                if not question["excluded"]:
                    scored += 1
                    if cleaned:
                        completed += 1
                    if metadata is not None:
                        run_metadata.append(metadata)
                clip_answers.append(
                    {
                        "pred": cleaned,
                        "ok": correct,
                        "obey": obey,
                        "question": question_sent,
                        "latency": (
                            metadata.get("api_elapsed_seconds")
                            if metadata
                            else None
                        ),
                        "prompt_tokens": (
                            metadata.get("prompt_tokens") if metadata else None
                        ),
                        "completion_tokens": (
                            metadata.get("completion_tokens")
                            if metadata
                            else None
                        ),
                        "reasoning_tokens": (
                            metadata.get("reasoning_tokens")
                            if metadata
                            else None
                        ),
                    }
                )
            answers.append(clip_answers)
        info.update(
            {
                "completed": completed,
                "scored": scored,
                "answers": answers,
                **summarize_metadata(run_metadata),
            }
        )
        runs.append(info)

    payload = {
        "clips": clips,
        "runs": runs,
        "expected": 260,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    js_path = root / "scoring-data.js"
    js_path.write_text(
        "window.SCORING_DATA = "
        + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {js_path} ({len(clips)} clips, {len(runs)} runs)")


if __name__ == "__main__":
    main()
