---
name: cost-for-your-fleet
description: Estimate what running each benchmarked VLM over a fleet's video would cost, and which model gives the best VLADBench score for a budget. Use when asked about VLM cost, budget, video volume, or whether a team is overspending on a model.
---

# Cost for your fleet

Ask for, or assume and state: hours of video per day, frame size, frames per second, frames per question, and a
daily budget. The published figures assume 1280x720, 1 FPS, 8-frame clips, one question per clip, no overlap.

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
- If the user's task is one family of VLADBench tasks (for example signs, vulnerable road users, or planning),
  rank by the question-weighted mean of those tasks instead of TOTAL.

State the limits with the answer: prices are what our sweeps were billed and change; open-weight models were served
by several OpenRouter hosts at different prices, so their figures are blends; output length depends on the question;
VLADBench score is a proxy for the user's task, not a measurement of it.
