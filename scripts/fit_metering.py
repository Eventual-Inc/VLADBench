"""Re-derive the tokeniser rules in vladbench.metering from the sweeps and report the residuals.

  PYTHONPATH=src python3 scripts/fit_metering.py

For every model with a rule: billed visual tokens per clip at each frame resolution the dataset contains, the rule's
prediction, and the residual; the effective per-token prices the sweep paid against OpenRouter's list; and which hosts
served the model. Run it after a new sweep lands to confirm the rules still hold before publishing hourly costs.
"""

from collections import defaultdict
import glob
import json
import os
from pathlib import Path
from statistics import median

from dotenv import load_dotenv

from vladbench.metering import RULES, TEXT_TOKENS, clip_tokens, effective_prices, fetch_prices
from vladbench.requests import questions, tasks

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results/runs/full-original"
MEDIA = ROOT / "results/runs/media"


def frame_dimensions() -> dict[str, tuple[int, int]]:
    """Frame size per URL from the media receipts; sequence frames only, which is what the video path bills."""
    dims = {}
    for receipt in MEDIA.glob("*.json"):
        for frame in json.loads(receipt.read_text()).get("frames", []):
            dims[frame["url"]] = tuple(frame["dimensions"])
    return dims


def clips() -> dict[str, tuple[int, tuple[int, int]]]:
    """question id -> (frames, resolution) for sequence questions whose frames share one resolution."""
    dims = frame_dimensions()
    out = {}
    for task in tasks():
        for q in questions(task):
            if q["sequence"]:
                sizes = {dims.get(u) for u in q["image_urls"]}
                if len(sizes) == 1 and None not in sizes:
                    out[q["id"]] = (len(q["image_urls"]), sizes.pop())
    return out


def records(model_id: str) -> list[dict]:
    return [json.loads(line) for path in glob.glob(str(RUNS / model_id / "*.jsonl")) for line in open(path)]


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
    load_dotenv(ROOT / ".env")
    spec = json.loads((ROOT / "results/protocols/full-original.json").read_text())
    slugs = {m["id"]: m["model"] for m in spec["models"] if m["id"] in RULES}
    key = os.environ.get("OPENROUTER_API_KEY")
    listed = fetch_prices(key, list(slugs.values())) if key else {}
    shapes = clips()
    for model_id, slug in slugs.items():
        rows = records(model_id)
        if rows:
            report(model_id, rows, shapes, slug, listed.get(slug))


if __name__ == "__main__":
    main()
