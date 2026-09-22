# Review fix list

Every finding from `companion-review.md` and `dataset-review.md`, with its status as of 2026-09-22.

Status values:

- **Fixed:** changed and pushed. The commit is given.
- **Local:** changed in the working tree, not pushed yet.
- **After sweeps:** needs the GPT-6 Luna, GPT-6 Sol, and Gemini 2.5 Flash Lite (reasoning off) runs to finish, then a results rebuild, a parquet export, and a publish.
- **Open:** not trivial. It needs a decision or real work.
- **Declined:** we decided against the reviewer.

## Companion site

| # | Finding | Status |
|---|---|---|
| C1 | Video cost for Opus 5.5 and Qwen 3.8 Max left out input tokens (area rule missing) | Fixed, `bea5286` |
| C2 | Three pairs of models shared a colour | Fixed, `bea5286`. One hue per lab, lightness within a lab. 15 models cannot all pass the colour-vision checks, so labels carry identity. |
| C3 | The frontier depends on the box reading, and the page did not say so | Fixed, `bea5286`. Box-reading switch on the Cost tab and a frontier-by-reading table. |
| C4 | Cost per point table | Fixed, `bea5286`. Removed. |
| C5 | Box panel, cost notes, and billing dates did not mention Claude or stopped at 09-16 | Fixed, `bea5286`. Notes rewritten as one line on how to read each chart. |
| C6 | Stale quadrant notes (Risk Prediction, Sign-Sign, Spatial-Temporal) | Fixed, `bea5286`. Finding text removed from chips. |
| C7 | "Trusted / Not trusted" wording | Fixed, `bea5286`. Now "Problem found / No problem found". |
| C8 | "follow the video cost calculator below" | Fixed, `bea5286` |
| C9 | PROTOCOL.md: no Opus, Luna 6, or Sol 6 rows; "Inkling"; images list missed Opus | Fixed, `bea5286` |
| C10 | Embed captions and heights (overview, frontier, results); "weights bar" text | Fixed, `bea5286` |
| C11 | Code comments on pixel models and the embed list | Fixed, `bea5286` |
| C12 | embed.html loaded the 16 MB question file | Fixed, `bea5286`. The swap now matches the versioned tag, and the slim file carries question counts. |
| C13 | Expanding Trajectory threw an error | Fixed, `bea5286` |
| C14 | Article nav link was a 404 | Fixed, `bea5286`. Hidden until the post is live; pass `--article <url>` to the Pages build. |
| C15 | Wheel taps did nothing on phones | Fixed, `bea5286`. A tap shows the value under the wheel. |
| C16 | No machine-readable download | Fixed, `bea5286`. rerun.json in the Pages bundle and a Dataset nav link. |
| C17 | About 364 tab stops in the wheel | Fixed, `bea5286`. Bars are no longer tab stops. |
| C18 | self-test.html stylesheet version | Fixed, `bea5286` |
| C19 | Pixel models drawn with a no-op "own grid" ring | Local |
| C20 | Reka note repeats its score | Local. Takes effect at the results rebuild. |
| C21 | PROTOCOL "higher than both Qwen models on 25 of 28" | Local. Reworded to name the two Qwen models; verified 25 of 28. |
| C22 | Weather and Light under "near saturation" only because of agreement | Declined. Weather and Light are saturated; the questions no model answers are bad questions. |
| C23 | No run-to-run noise statement on the site | Open. Needs a decision on wording, or bootstrap intervals. |
| C24 | 2025 cohort includes specialised models | Open on the site. A comment was added in the frontier post. |
| C25 | Explore header shows TOTAL as "75.9% mean" | Open. Trivial rename, pending a glossary decision. |
| C26 | Video table includes Reka Edge while other views leave it out | Open. Trivial, pending a decision. |
| C27 | Phone: Cost vs Score labels unreadable; leaderboard hides columns without saying so | Open |
| C28 | Tabs lack aria-controls and arrow keys; charts have no text alternative; heat scale defaults to red/green | Open |
| C29 | "q1 · q2 · q3" cell legend; "11,137 carried · 56 re-asked" chip; Table 10 abbreviations only in hover titles; no glossary | Open |
| C30 | Cut-in survey settings differ from the protocol (Gemini reasoning on, Qwen 3.6 FP8) | Open. The cut-in rerun under the protocol runner replaces it. |
| C31 | GPT-6 Luna and Sol missing from the page | After sweeps |

## Dataset

| # | Finding | Status |
|---|---|---|
| D1 | License covered upstream material | Fixed, `85ed451`, published. CC-BY-4.0 on our additions; upstream terms stated as undeclared. |
| D2 | Box issue left out Anthropic and understated the effect | Fixed, `85ed451`, published |
| D3 | Re-asks not disclosed; costs are a lower bound | Fixed, `85ed451`, published (disclosure). Per-draw cost logging is Open. |
| D4 | Serving host not recorded | Local export change in `85ed451`. The column ships with the next export (after sweeps). Card sentence to restore then. |
| D5 | Gemini 2.5 Flash Lite ran with reasoning on | After sweeps. Rerun with reasoning off in progress; old answers archived under `results/runs/archive/`. |
| D6 | Template bugs: Reka note missing, shifted model table, cap note, unused date and hash | Fixed, `85ed451`, published |
| D7 | Wrong card text: TOTAL column, protocol hash, "unchanged" scorer, frames per clip, Alibaba routing | Fixed, `85ed451`, published |
| D8 | Missing known issues: provider error answer, Trajectory, carried 512 answers | Fixed, `85ed451`, published |
| D9 | Cost column assumptions unstated | Fixed, `85ed451`, published |
| D10 | Citation: no paper BibTeX, "best TOTAL" note, short sha | Fixed, `85ed451`, published |
| D11 | Traffic Light: 7 or 9 references not among the options | Open. Recount. |
| D12 | Weather/Light percentages depend on the cohort | Fixed. Numbers removed from the card. |
| D13 | Lossy H.264 fallback counts; MiniMax reasoning tokens above completion tokens | Open. Add to known issues. |
| D14 | `reference` stored as Python repr; no typed column | Open |
| D15 | `country` holds dataset names and the typo "Amercia" | Open. Kept from upstream; say so. |
| D16 | Everything loads as a `train` split | Open |
| D17 | Undocumented columns: `featured`, `carried_from_512`, `condition`, `sample_id`, latency units | Open. Needs a column dictionary on the card. |

## Wishlists

Both reviews end with a ranked wishlist. The overlapping items, in order:

1. Uncertainty: bootstrap intervals on TOTAL and task scores, with paired tests for adjacent ranks and frontier steps.
2. A per-question `marks` table and typed references, so the dataset rebuilds scores without the repo.
3. A per-model card: route and hosts, run dates, reasoning, transport, retries, fallbacks, cost basis.
4. Every draw, including discarded ones, with its cost.
5. Domain subtotals for buyers (planning, VRU, signals), and a TOTAL over tasks with no audit problem.
6. A changelog with dataset, scorer, and spec hashes.
