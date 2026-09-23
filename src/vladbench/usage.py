"""Cost, latency, and video-hour summaries from the stored answer records."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from . import paths
from .metering import RULES, effective_prices, frame_tokens, hourly_cost
from .run import read_jsonl

# The post's workload: 1280x720 frames at 1 FPS in non-overlapping 8-frame clips, one question each.
WIDTH, HEIGHT, FPS, FRAMES_PER_QUERY = 1280, 720, 1.0, 8
TEXT_TOKENS = 110
VIDEO_COST_BASIS = ("1280x720 at 1 FPS in non-overlapping 8-frame clips, one question each: 3,600 frames and 450 queries an hour; "
                    "fitted tokeniser rule (vladbench.metering), the sweep's effective per-token prices, measured output tokens per query including reasoning")
NO_VIDEO_COST = {"input_cost_per_frame_usd": None, "output_cost_per_query_usd": None, "cost_per_video_hour_usd": None}


def answer_records(model_id: str, runs: Path = paths.RUNS) -> list[dict]:
    """Every stored answer record for one model, across task files in name order."""
    folder = runs / model_id
    if not folder.is_dir():
        return []
    return [r for path in sorted(folder.glob("*.jsonl")) for r in read_jsonl(path)]


def billed_costs(records: Sequence[dict]) -> list[float]:
    return [c for c in ((r.get("usage") or {}).get("cost") for r in records) if c is not None]


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile of sorted values."""
    return values[min(len(values) - 1, int(len(values) * q))]


def latency_summary(seconds: Sequence[float]) -> dict | None:
    """p25, p50, p75, p95, and max of per-request wall-clock time."""
    if not seconds:
        return None
    ordered = sorted(seconds)
    return {"n": len(ordered), "p25": percentile(ordered, .25), "p50": percentile(ordered, .5),
            "p75": percentile(ordered, .75), "p95": percentile(ordered, .95), "max": ordered[-1]}


def task_usage(records: Sequence[dict]) -> dict:
    """Billed cost, answer count, and median latency of one model's answers on one task."""
    known = billed_costs(records)
    seconds = sorted(r["elapsed_seconds"] for r in records if r.get("elapsed_seconds") is not None)
    return {"cost_usd": sum(known) if known else None, "answers": len(records),
            "latency_p50": seconds[len(seconds) // 2] if seconds else None}


def video_cost(model_id: str, records: Sequence[dict]) -> dict:
    """Input $/frame, output $/query, and $/video hour from the fitted metering rule and the sweep's billed prices."""
    rule = RULES.get(model_id)
    if rule is None or not all("cost_details" in (r.get("usage") or {}) for r in records):
        return dict(NO_VIDEO_COST)
    prices = effective_prices(list(records))
    output_tokens = sum((r.get("usage") or {}).get("completion_tokens", 0) for r in records) / len(records)
    hour = hourly_cost(rule, prices, width=WIDTH, height=HEIGHT, fps=FPS, frames_per_query=FRAMES_PER_QUERY, output_tokens_per_query=output_tokens)
    return {"input_cost_per_frame_usd": frame_tokens(rule, WIDTH, HEIGHT, FRAMES_PER_QUERY) * prices.prompt,
            "output_cost_per_query_usd": output_tokens * prices.completion,
            "cost_per_video_hour_usd": hour["total_usd"], "tokens_per_frame_720p": hour["tokens_per_frame"],
            "metering": {"rule": {"kind": rule.kind, "patch": rule.patch, "multiplier": rule.multiplier, "tokens_per_pixel": rule.tokens_per_pixel,
                                  "tokens_per_frame": rule.tokens_per_frame},
                         "prompt_price": prices.prompt, "completion_price": prices.completion, "output_tokens_per_query": output_tokens,
                         "text_tokens": TEXT_TOKENS},
            "video_cost_basis": VIDEO_COST_BASIS}


def model_usage(model_id: str, records: Sequence[dict]) -> dict | None:
    """Sweep cost (provider-billed, summed per answer), latency summary, and video cost for one model."""
    if not records:
        return None
    known = billed_costs(records)
    seconds = [r["elapsed_seconds"] for r in records if r.get("elapsed_seconds") is not None]
    return {"cost_usd": sum(known) if known else None, "cost_receipts": len(known), "answers": len(records),
            "latency_seconds": latency_summary(seconds), **video_cost(model_id, records)}
