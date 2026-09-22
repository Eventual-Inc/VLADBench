# VLADBench companion site review (2026-09-22)

Checked against the live site (byte-identical to local `web/*.js` and data bundles at review time), `results/rerun.json`, `task-review-variants.js`, and `answers/*.json`. Uncommitted local edits to `web/analysis.js` fix some items; those are marked.

## 1. Out-of-date descriptions (14)

| # | Location | Text | Data | Status |
|---|---|---|---|---|
| 1 | results.html:143 (box panel), docs/hf-dataset-card.md Known issues | "OpenAI's models answer in pixels. Qwen, Muse, Gemma, MiniMax, and Reka answer on a 0 to 1000 grid" | Claude Opus 5.5 answers in pixels (`VARIANTS.opus55.convention = "pixels"`) and is not mentioned | CONFIRMED |
| 2 | web/results.js:331 | "billed through OpenRouter, 2026-09-13 to 2026-09-16" | Opus answers are timestamped 2026-09-22 17:54 to 20:31 UTC | CONFIRMED |
| 3 | web/results.js:439 | "OpenAI and Qwen bill by pixel area … Google's video path bills a flat count per frame" | Anthropic (area) is not mentioned. Only Qwen Max is `area`; Qwen 27B/3.6 are `pair`. Muse, MiniMax, and Reka are flat too | CONFIRMED |
| 4 | web/analysis.js:533 | Risk_Prediction "Gemma 52, the rest above 75" | Qwen 3.6 35B A3B scores 62.4. Still wrong locally | CONFIRMED |
| 5 | web/analysis.js:533 (live) | Sign_Sign_Relation "19% miss for every model" | 33/192 = 17.2% with Opus. Fixed locally | CONFIRMED |
| 6 | web/analysis.js:533 (live) | "Astra 95, field 73" | field mean 74.4. Fixed locally | CONFIRMED |
| 7 | web/results.js:228 | "follow the video cost calculator below" | the calculator is on the Cost tab, not below | CONFIRMED |
| 8 | docs/PROTOCOL.md per-model table | 12 rows | Opus 5.5 is missing, and so are GPT-6 Luna/Sol, which are declared in the protocol file | CONFIRMED |
| 9 | docs/PROTOCOL.md:22-23 | "Qwen Max and the OpenAI models see frames as separate images, the others see a video" | Opus uses `ordered_image_urls` too | CONFIRMED |
| 10 | docs/PROTOCOL.md:12-13 | "Qwen Max vs Inkling" | no Inkling model in the scored set | CONFIRMED |
| 11 | scripts/build_blog_embed.py VIEWS["overview"] | "Leaderboard, Cost vs Score, frontier tables, and the video cost calculator" | `embed=overview` maps to the Cost tab, which has no leaderboard | CONFIRMED |
| 12 | build_blog_embed.py snippets() | "the weights bar … work inside the frame" | the weights control was removed (results.js:146-149 is empty) | CONFIRMED |
| 13 | build_blog_embed.py VIEWS["results"] | "Table 10 layout", height 2200 | the embed also renders the wheel and is 3558 px tall | CONFIRMED |
| 14 | scripts/build_variants.py:24, web/results.js:966 | "OpenAI models answer in pixels"; embed list comment | Opus omitted from the first; 8 embed names missing from the second | CONFIRMED (comments) |

## 2. Wrong or misleading

1. **Video cost for Opus and Qwen Max is understated 20x and 8x.** At web/results.js:393, `clipTokens` has no `area` branch, so it falls through to `tokens_per_frame = 0`. Live leaderboard and calculator show Opus 0 tokens/frame, $0.00000 input/frame, $0.91/h; Python metering gives 1199 tokens and $18.18/h. Qwen Max shows $0.92/h against $7.72/h. Opus appears cheaper per hour than GPT-5.6 Luna, which is false. Fix: add `if (rule.kind === "area") return frames * rule.tokens_per_pixel * width * height;`. CONFIRMED.
2. **Model colours collide.** `MODEL_COLORS` has 10 entries for 13 models (results.js:13). Opus = Muse (#199e70), Qwen 3.8 27B = Gemini 3.8 Flash (#3987e5), Qwen 3.6 = Qwen Max (#d95926). This affects every legend, the wheel, radar, bars, and scatter. Fix: add at least 3 validated hues. CONFIRMED.
3. **The frontier depends on the box reading, and the page does not say so.** Pixels: Gemma → Qwen 3.6 → Gemini 2.5 Lite → Luna → Gemini 3.8 → Opus → Astra. On each model's own grid: Gemma → Qwen 3.6 → Gemini 3.8 → Qwen Max → Opus → Astra. With box tasks removed, MiniMax replaces Luna. Three frontier members change. Fix: add a box-reading toggle on the Cost tab, or a note under the frontier. CONFIRMED.
4. **No run-to-run noise statement on the site.** Opus vs Astra is 0.9 points, shown as "$389.32 per point". Gemini 3.8 / Sol / Qwen Max sit within 0.6. The HF card says "differences under about two points could be run-to-run noise"; the site says nothing. CONFIRMED (absence).
5. **"Near saturation" includes Weather (mean 73.7) and Light (69.4)** only because sd < 2.5. That measures agreement, not saturation. Relabel the column or split it. CONFIRMED.
6. **Explore column header shows TOTAL as "75.9% mean"** (results.js:661), while other tabs call it Score or TOTAL and give it no % sign. CONFIRMED.
7. **The video table includes Reka Edge**; the leaderboard, plot, and frontier exclude it. CONFIRMED.
8. **The 2025 distribution cohort (25 models) includes the paper's own fine-tuned model ("Ours 4B") and driving-specialist models.** The page does not say this, so 2025 vs 2026 means mix general and domain-tuned models. SUSPECTED as misleading.

## 3. Broken

1. **Embed builds load the 16 MB question file.** `embed_html()` replaces `task-review-data.js"` but results.html has `task-review-data.js?v=2"`, so nothing is replaced. The live embed.html is byte-identical to results.html. Note: task-review-tasks.js has `items: []`, so once the swap works, Explore would show "0 questions" (results.js:689). Fix both together. CONFIRMED.
2. **Expanding "Trajectory" in Explore throws.** You get a 404 on answers/Trajectory.json, then `TypeError … reading 'scorer_function'` at task-detail.js:38. Trajectory is unscored but still listed. Hide it, or guard `sample`. CONFIRMED.
3. **The Article nav link returns 404** (https://www.eventual.ai/blog/vladbench-reeval). CONFIRMED.
4. **Phone, 375 px:** clicking a wheel wedge or bar sets `#matrix`, which phones cannot show, so the page falls back to Overview and nothing happens. The Cost vs Score SVG (1180 wide) scales to about 0.28x, so its labels are unreadable. The leaderboard hides the latency and $/frame columns without saying so. CONFIRMED.
5. **results/rerun.json returns 404 on Pages.** There is no machine-readable download on the site. CONFIRMED.
6. **Accessibility:**
   - The wheel creates about 364 tab stops.
   - Tabs lack `aria-controls` and arrow-key handling.
   - Charts are `role=img` with no text alternative, except the frontier tables.
   - The default heat scale is red/green.
   - Model identity is carried by colour alone, and colours collide (item 2.2).

   CONFIRMED.
7. **self-test.html** uses `results.css?v=27` against v=46 on the main page and loads 16 MB up front. Minor.

## 4. Confusing (expected vs got)

- **q1 · q2 · q3 in cells.** Expected question numbers, or accuracy first. Got other · accuracy · instruction, with q1 greyed on most tasks.
- **Box chart ring "own 0–1000 grid" for OpenAI/Claude.** Expected no ring. Got a ring at Δ 0.0.
- **Chip "11,137 carried · 56 re-asked."** Expected an explanation on the page. It is only in PROTOCOL.md.
- **Reka note** reads "Reka Edge (39.8; 7B edge model scoring 39.8; …)". The number appears twice.
- **"Score", "TOTAL", "mean", and "field mean"** are used for different things across tabs, with no glossary.
- **Table 10 abbreviations (L.R.RL etc.)** are explained only in hover titles.
- **`embed=overview`** shows the Cost tab.
- **PROTOCOL claim "higher than both Qwen models on 25 of 28".** It holds for the two small Qwens; against all three it is 14.
- **Cut-in survey** lists Gemini "reasoning on" and "Qwen 3.6 FP8", which differ from the protocol settings. The caption says "different runner" but does not name these differences.
- **GPT-6 Luna and Sol** are in the protocol but nowhere on the page, not even as "pending".

## 5. Wished-for, ranked

1. Bootstrap CIs per task and TOTAL, with paired tests for adjacent ranks and frontier steps.
2. Downloads: leaderboard and per-task CSV/JSON, rerun.json, per-model answers, plus links to the HF dataset and PROTOCOL.md in the nav.
3. A global box-reading toggle (pixels / own grid / excluded) that drives the leaderboard and frontier.
4. A per-model card: slug, route/hosts, run dates, reasoning, transport, retries, empty and truncated answers, fallbacks, and cost basis.
5. A "trusted tasks only" TOTAL, and domain subtotals relevant to buyers (planning, VRU, signals).
6. Latency and throughput vs score, and a rate-limit note.
7. Instruction-following rate per model as its own column, since format failures cost up to 20% on some tasks.
8. A changelog on the page (Opus added 2026-09-22), with dataset, scorer, and spec hashes and the commit shown.
9. A two-model head-to-head view with per-task deltas.
