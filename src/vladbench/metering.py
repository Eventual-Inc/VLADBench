"""Reproduce what each provider bills for a frame, a question, and an hour of video question answering.

Every rule here was fitted to the billed token counts of the full sweeps on 2026-09-16 (scripts/fit_metering.py
re-derives them and reports the residuals) and is checked live against the provider in tests/test_metering.py.

Start from ``hourly_cost``.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from urllib.request import Request, urlopen

TEXT_TOKENS = 110      # the benchmark's question text, averaged over all 11,193 prompts
OPENROUTER_MODELS = "https://openrouter.ai/api/v1/models"


@dataclass(frozen=True)
class Rule:
    """How a provider turns one frame into billed prompt tokens.

    kind "patch": ceil(w/patch) * ceil(h/patch) * multiplier per frame, the OpenAI image path.
    kind "pair": tokens_per_pixel * w * h per pair of frames, ceil(frames/2) pairs; the Qwen video tokeniser merges
                 two consecutive frames into one temporal patch. Some OpenRouter hosts subsample and bill a third of this.
    kind "flat": tokens_per_frame regardless of resolution, the Google video path at 1 FPS.
    """
    kind: str
    patch: int = 0
    multiplier: float = 0.0
    tokens_per_pixel: float = 0.0
    tokens_per_frame: float = 0.0
    input_rate: str = "prompt"   # which price field the frame tokens are billed at


def clip_tokens(rule: Rule, width: int, height: int, frames: int) -> float:
    """Billed visual tokens for a clip of ``frames`` frames at one resolution."""
    if rule.kind == "patch":
        return frames * math.ceil(width / rule.patch) * math.ceil(height / rule.patch) * rule.multiplier
    if rule.kind == "pair":
        return math.ceil(frames / 2) * rule.tokens_per_pixel * width * height
    return frames * rule.tokens_per_frame


def frame_tokens(rule: Rule, width: int, height: int, frames: int = 8) -> float:
    """Average billed tokens per frame inside a clip of ``frames`` frames; equals the per-frame figure for patch and flat."""
    return clip_tokens(rule, width, height, frames) / frames


# Fitted per model id in results/protocols/full-original.json (scripts/fit_metering.py prints the residuals).
# patch: within 1% at every resolution in the dataset. flat: Google bills its video path by clip duration with a small
# per-clip overhead, so the per-frame constant holds within 10% for clips of 3 to 8 frames at 720p and drifts up to 30%
# for 2-frame clips or 1920x1208 frames; the live check at 720p x 8 frames passes within 10%. pair: the standard Qwen
# tokeniser as served by most OpenRouter hosts (about 880 tokens per pair at 720p); DeepInfra, Darkbloom, Phala, and
# AtlasCloud subsample frames and bill about a third of it, so hourly figures for the open Qwens are an upper bound.
RULES: dict[str, Rule] = {
    "luna56": Rule("patch", patch=32, multiplier=1.2, input_rate="input_cache_write"),
    "sol56": Rule("patch", patch=32, multiplier=1.2, input_rate="input_cache_write"),
    "astra6": Rule("patch", patch=32, multiplier=1.2, input_rate="input_cache_write"),
    "qwen36or": Rule("pair", tokens_per_pixel=880 / (1280 * 720)),
    "qwen38or": Rule("pair", tokens_per_pixel=880 / (1280 * 720)),
    "gemini38": Rule("flat", tokens_per_frame=63),
    "gemini25lite": Rule("flat", tokens_per_frame=255),
    "gemma431": Rule("flat", tokens_per_frame=74),
}


@dataclass(frozen=True)
class Prices:
    """USD per token, as OpenRouter lists them."""
    prompt: float
    completion: float
    input_cache_write: float | None = None

    def input(self, rate: str) -> float:
        value = getattr(self, rate, None)
        return self.prompt if value is None else value


def prices_from_openrouter(pricing: dict) -> Prices:
    cache = pricing.get("input_cache_write")
    return Prices(prompt=float(pricing["prompt"]), completion=float(pricing["completion"]),
                  input_cache_write=float(cache) if cache is not None else None)


def fetch_prices(api_key: str, slugs: list[str]) -> dict[str, Prices]:
    """Current OpenRouter list prices for the given provider model strings."""
    request = Request(OPENROUTER_MODELS, headers={"Authorization": "Bearer " + api_key})
    with urlopen(request, timeout=60) as response:
        listed = {m["id"]: m["pricing"] for m in json.loads(response.read())["data"]}
    return {slug: prices_from_openrouter(listed[slug]) for slug in slugs if slug in listed}


def effective_prices(records: list[dict]) -> Prices:
    """What a sweep was actually billed per token, from OpenRouter's per-answer cost details.

    Open-weight models route across hosts whose prices differ, so the list price is the cheapest host and the sweep
    pays a blend above it; single-host models bill exactly at list. Image tokens on OpenAI are cache writes, so the
    effective prompt rate already includes that premium and the rule's input_rate should be treated as "prompt".
    """
    prompt_tokens = sum(r["usage"]["prompt_tokens"] for r in records)
    completion_tokens = sum(r["usage"].get("completion_tokens", 0) for r in records)
    prompt_cost = sum(r["usage"]["cost_details"]["upstream_inference_prompt_cost"] for r in records)
    completion_cost = sum(r["usage"]["cost_details"]["upstream_inference_completions_cost"] for r in records)
    return Prices(prompt=prompt_cost / prompt_tokens, completion=completion_cost / max(completion_tokens, 1))


def input_cost(rule: Rule, prices: Prices, width: int, height: int, frames: int, text_tokens: int = TEXT_TOKENS) -> float:
    """Billed cost of one query's prompt: the frames at the rule's rate plus the question text at the prompt rate."""
    return clip_tokens(rule, width, height, frames) * prices.input(rule.input_rate) + text_tokens * prices.prompt


def output_cost(prices: Prices, output_tokens: float) -> float:
    """Completion cost including reasoning tokens, which every provider here bills at the completion rate."""
    return output_tokens * prices.completion


def hourly_cost(rule: Rule, prices: Prices, *, width: int = 1280, height: int = 720, fps: float = 1.0,
                frames_per_query: int = 8, output_tokens_per_query: float = 0.0) -> dict:
    """Cost of one hour of video question answering under a stated workload.

    Frames per hour is fps * 3600; queries per hour is frames per hour over frames per query, so clips do not overlap.
    """
    frames_per_hour = fps * 3600
    queries_per_hour = frames_per_hour / frames_per_query
    per_query_in = input_cost(rule, prices, width, height, frames_per_query)
    per_query_out = output_cost(prices, output_tokens_per_query)
    return {"frames_per_hour": frames_per_hour, "queries_per_hour": queries_per_hour,
            "tokens_per_frame": frame_tokens(rule, width, height, frames_per_query),
            "input_usd": queries_per_hour * per_query_in, "output_usd": queries_per_hour * per_query_out,
            "total_usd": queries_per_hour * (per_query_in + per_query_out)}
