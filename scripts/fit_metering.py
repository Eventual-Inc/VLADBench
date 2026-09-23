"""Re-derive the tokeniser rules in vladbench.metering from the sweeps and report the residuals.

  uv run python scripts/fit_metering.py

For every model with a rule: billed visual tokens per clip at each frame resolution the dataset contains, the rule's
prediction, and the residual; the effective per-token prices the sweep paid against OpenRouter's list; and which hosts
served the model. Run it after a new sweep lands to confirm the rules still hold before publishing hourly costs.
"""

from collections import defaultdict
import json
import os
from statistics import median

from dotenv import load_dotenv

from vladbench import paths
from vladbench.metering import RULES, TEXT_TOKENS, clip_tokens, effective_prices, fetch_prices
from vladbench.requests import questions, tasks
from vladbench.spec import load_spec
from vladbench.usage import answer_records

MEDIA = paths.ROOT / "results/runs/media"


def frame_dimensions() -> dict[str, tuple[int, int]]:
    """Frame size per URL from the media receipts; sequence frames only, which is what the video path bills."""
    dims: dict[str, tuple[int, int]] = {}
    for receipt in MEDIA.glob("*.json"):
        for frame in json.loads(receipt.read_text()).get("frames", []):
            width, height = frame["dimensions"]
            dims[frame["url"]] = (width, height)
    return dims


def clips() -> dict[str, tuple[int, tuple[int, int]]]:
    """question id -> (frames, resolution) for sequence questions whose frames share one resolution."""
    dims = frame_dimensions()
    out = {}
    for task in tasks():
        for q in questions(task):
            if q["sequence"]:
                sizes = {dims[u] for u in q["image_urls"] if u in dims}
                if len(sizes) == 1 and all(u in dims for u in q["image_urls"]):
                    out[q["id"]] = (len(q["image_urls"]), sizes.pop())
    return out


def report(model_id: str, rows: list[dict], shapes: dict, slug: str, listed) -> None:
    rule = RULES[model_id]
    billed = defaultdict(list)
    hosts = defaultdict(int)
    for r in rows:
        hosts[r["response"].get("provider")] += 1
        shape = shapes.get(r["id"])
        if shape:
            billed[shape].append(r["usage"]["prompt_tokens"] - TEXT_TOKENS)
    print(f"\n{model_id} ({slug}) rule={rule.kind}  hosts={dict(sorted(hosts.items(), key=lambda kv: -kv[1])[:5])}")
    for (frames, (w, h)), values in sorted(billed.items(), key=lambda kv: -len(kv[1])):
        if len(values) < 20:
            continue
        observed, predicted = median(values), clip_tokens(rule, w, h, frames)
        print(f"  {frames} frames @ {w}x{h:<5} n={len(values):4}  billed {observed:7.0f}  rule {predicted:7.0f}  residual {100 * (observed - predicted) / predicted:+6.1f}%")
    effective = effective_prices(rows)
    if listed:
        print(f"  effective $/M in {effective.prompt * 1e6:.4f} (list {listed.prompt * 1e6:.4f})  out {effective.completion * 1e6:.4f} (list {listed.completion * 1e6:.4f})")


def main():
    load_dotenv(paths.ROOT / ".env")
    spec = load_spec(paths.PROTOCOL)
    slugs = {m["id"]: m["model"] for m in spec["models"] if m["id"] in RULES}
    key = os.environ.get("OPENROUTER_API_KEY")
    listed = fetch_prices(key, list(slugs.values())) if key else {}
    shapes = clips()
    for model_id, slug in slugs.items():
        rows = answer_records(model_id)
        if rows:
            report(model_id, rows, shapes, slug, listed.get(slug))


if __name__ == "__main__":
    main()
