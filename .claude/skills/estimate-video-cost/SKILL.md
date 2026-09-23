---
name: estimate-video-cost
description: Estimate the cost of video question answering with each benchmarked model at a stated workload, and identify the highest-scoring model within a budget. Use when asked about model cost, budget, or video volume.
---

# Estimate video cost

State the workload: hours of video per day, frame size, frames per second, frames per question, and the daily
budget, if any. The published figures assume 1280x720, 1 FPS, 8-frame clips, one question per clip, no overlap.

Compute with `uv run python`:

```python
import json
from vladbench.aggregate import Point, frontier, total
from vladbench.metering import RULES, Prices, hourly_cost

record = json.load(open("results/rerun.json"))
for m in record["models"]:
    meter = (m["usage"] or {}).get("metering")
    if not meter or m["id"] not in RULES:
        continue
    prices = Prices(prompt=meter["prompt_price"], completion=meter["completion_price"])   # what the sweep was billed per token
    hour = hourly_cost(RULES[m["id"]], prices, width=1280, height=720, fps=1.0, frames_per_query=8,
                       output_tokens_per_query=meter["output_tokens_per_query"])
    print(m["label"], round(total(m["tasks"]), 1), round(hour["total_usd"], 2))
```

- Multiply the hourly cost by hours per day for a daily cost. List models by TOTAL within the budget.
- The frontier: `frontier(Point(id, cost, score) ...)` over featured models gives the models no cheaper model beats.
  The five on the frontier under every box reading are Gemma 4 31B, Qwen 3.6 35B A3B, Gemini 3.8 Flash,
  Claude Opus 5.5, and GPT-6 Astra; check `task-review-variants.js` if the record has changed.
- If the intended use corresponds to one family of VLADBench tasks (for example signs, vulnerable road users, or planning),
  rank by the question-weighted mean of those tasks instead of TOTAL.

State the limitations with the estimate: prices are those billed during the sweeps and are subject to change;
open-weight models were served by several OpenRouter hosts at different prices, so their figures are blended; output
length depends on the question; a VLADBench score is a proxy for the intended task, not a measurement of it.
