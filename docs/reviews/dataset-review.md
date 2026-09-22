# Review: Eventual-Inc/VLADBench-reeval (Hub sha 3c93bb36, 2026-09-22)

All 6 published files are byte-identical to `results/dataset/`.

## What checks out (CONFIRMED)

- Row counts: models 13, tasks 28, questions 11,193, answers 145,509 (13 x 11,193), task_scores 364. No nulls. No duplicate keys. `model_id` is the same across all tables. Every answer joins to a question.
- `task_scores` equals `scores-*.json` exactly. The leaderboard TOTALs in the card match the question-weighted mean.
- Re-scoring from the parquet alone (answers + questions + `per_question.py` + `original/` scorer) gives every task score back to within 1e-13, and every TOTAL. Box references first have to be passed through `ast.literal_eval` (see M3).
- `models.cost_usd` equals the sum of `answers.cost_usd` for every model. Opus 5.5 appears in all tables (82.73, $205.28, 11,193 answers). There are no rows for GPT-6 Luna/Sol (`luna6`/`sol6` exist only in the protocol JSON).
- The card's Daft snippet runs as written (daft 0.7.25) and prints the 12 featured rows. `datasets.load_dataset` loads every config.
- Known-issue numbers: cut-in 172/174 "yes" is correct. Weather 17% and Light 20% all-wrong are correct for the 12 featured models (15.7%/15.5% with all 13).

## Findings, by severity

### High

**H1. Card, Known issues, boxes: Opus is left out of the pixel group, and the issue is understated. CONFIRMED.**
The card says "OpenAI models answer in pixels". Opus 5.5 also answers in pixels. Its mean IoU is 0.80–0.87, the best on Obstruction.
The three box tasks are 1,327 of 11,193 questions (11.9% of TOTAL). Pixel models (Astra, Opus, Sol, Luna) get IoU 0.60–0.87. All other models get about 0–0.29. So the top-2 ordering and the "frontier" depend on this convention.
The card also says the prompt "doesn't say what units". But the prompt states the image width and height in pixels.
Fix: name Anthropic, and publish a per-model TOTAL with box tasks excluded and/or on each model's own grid. Right now only Qwen 3.8 Max is given (78.3, not verified here).

**H2. License, source data. CONFIRMED that upstream has no license. SUSPECTED that the frame sources carry their own terms.**
The card declares `cc-by-4.0`. But upstream `depth2world/VLADBench` has no license in its Hub metadata, no README at the pinned revision, and the GitHub repo has `license: null`.
The dataset redistributes upstream prompts and references under CC-BY. The frames come from CODA, SODA, LingoQA and others (see `questions.country`), which likely have their own, possibly non-commercial, terms.
Fix: license only the answers/scores you created. State that the upstream annotations and frames are unlicensed or governed by their sources. Add the paper's BibTeX.

**H3. Serving provider not recorded; open-weight models were spread over many hosts. CONFIRMED.**
Run records show `qwen36or` served by at least 5 OpenRouter hosts (Darkbloom 2,887, DeepInfra 1,951, AkashML, Parasail, DekaLLM). `qwen38or` was also served by at least 5. `run.py` itself mentions "a quantised host".
Neither the card nor the parquet has `provider` or response `model`/`system_fingerprint`. This hurts reproducibility, and the quality and price of the open models are a mix of hosts.
Fix: add `answers.provider` and `answers.served_model`, and disclose the routing in the card.

**H4. Gemini 2.5 Flash Lite ran with reasoning ON, which contradicts the card. CONFIRMED.**
The card says reasoning is at "its lowest available level" and names Astra as the only exception. `docs/PROTOCOL.md:59` says Flash Lite is "low, requested; thinking is off by default". Its answers average 792 reasoning tokens.
Fix: list it as a second exception, or re-run it with reasoning off.

### Medium

**M1. Card rendering bugs from `publish_hf.py`/template. CONFIRMED.**
(a) `@MODEL_ROWS@` sits inside a table row. The first row starts with an extra `| |`, which shifts every column of Qwen 3.8 27B, and the Reka row has trailing empty cells.
(b) `@OMITTED@` is filled but never placed in the template. The card says 13 models, the leaderboard shows 12, and nothing explains that Reka Edge (39.78) is missing.
(c) The 512-guard note loses its first sentence when no model is capped, so the card says "Gemini 3.8 Flash also started under it" with no antecedent.
(d) `@DATE@` and `@SPEC@` are computed but never shown. The card has no date and no protocol hash.

**M2. Card text vs data. CONFIRMED.**
- "Most tasks only provide 2 or 3 frames": the median frame count per sequence task is 4–5 for 11 of 12 tasks (Lateral: 1).
- "Alibaba ... rejecting clips under four frames ... those models received ordered images": only Qwen 3.8 Max got images. Qwen 3.8 27B and 3.6 got video, routed away from Alibaba (`provider.ignore: ["Alibaba"]`).
- The `models` row of the Tables section says it has "TOTAL". There is no TOTAL column (only `mean_task_score` and `median_task_score`, which are unweighted).
- Anthropic's image transport is not explained.

**M3. `questions.reference` is `str()` of mixed Python types. CONFIRMED.**
Boxes come out as `"[1760, 588, 1918, 986]"`, which is a Python repr and not typed. Rescoring needs `ast.literal_eval` for grounding tasks only. Parsing all bracketed references crashes `speed_mark`.
Fix: add a typed `reference_json` column and document it.

**M4. Hidden redraws; cost is under-counted. CONFIRMED from code.**
`send_until_answered` redraws empty, truncated, or degenerate answers and keeps only the final `usage`. So `cost_usd` and "Sweep cost" leave out billed discarded draws.
The guard also works as resample-until-finished. `attempt` mixes HTTP retries with redraws (minimax 151, muse 104, gemini38 63). None of this is in the card.
Fix: record cost and tokens per draw, and add `redraws` and `http_retries` columns.

**M5. Unreported error row. CONFIRMED.**
`qwen36or` question `20502f52...` (Drive_Efficiency) has `finish_reason="error"`, $0, answer "D.". It is scored, and the model is still `protocol_complete=True`.
Fix: list it in Known issues, or re-ask it.

**M6. Mixed conditions for Gemini 3.8 Flash. CONFIRMED.**
11,137 answers are `condition=full-original-512` (2026-09-13) and 56 are live. Reasoning under a 512 cap can differ from reasoning under 8192. This is disclosed only in the garbled sentence (M1c).

### Low

- **L1.** "$/hour of video" and "Input $/frame" assume 1280x720, 1 fps, 8 frames per query, non-overlapping clips (`metering.py`, `build_review_results.py:137`). The card says only "see the code". The open-Qwen figures are upper bounds (per the `metering.py:58` comment). CONFIRMED.
- **L2.** Traffic Light off-list references: the card says 7/795. My check with `extract_options` finds 9, e.g. "Red Light", "55s", "17s". SUSPECTED counting difference.
- **L3.** Temperature is unset (provider default), `image_detail=auto`, and there are up to 4 attempts. None of this is in the card. CONFIRMED.
- **L4.** The citation has no author list or version. The upstream paper is not cited in BibTeX. The source revision is shortened to `1895f222`; the full SHA is in `image_urls`.
- **L5.** `minimax3` has `reasoning_tokens > completion_tokens` in 5,477 rows, as reported by the provider. SUSPECTED accounting quirk; worth a footnote.
- **L6.** Upstream typos are kept (`Vehicle_Bahavior`, `Key_Obsturction_Detection`, `Geneal_criterion_QA`, country "Amercia" 287 rows). Say they are kept on purpose.

## Reproducibility

Scores can be rebuilt from the dataset plus the repo. Responses cannot:
- There is no served provider or model version (H3).
- There are no raw responses, and no `video_sha256` even though it is recorded.
- The card does not pin a repo commit for the scorer wrapper or the protocol JSON (`specification_sha256` 00e3d4cf... exists only in the repo JSONs).

The frame URLs are pinned to the upstream revision, and the scorer is pinned to Depth2World commit b0dde78 plus a disclosed one-line patch. Both are good, but neither is stated in the card.

## Wishlist (ranked)

1. **Per-question marks table**: accuracy, instruction, other, kind, pair per model x question. This lets users skip re-running the scorer.
2. **`answers.provider`, `served_model`, `system_fingerprint`.**
3. **Adjusted-TOTAL table**: box tasks excluded, own-grid boxes, cut-in judgment removed. Buyers need this to rank fairly.
4. **Per-draw cost and tokens, `redraws`, `http_retries`**, plus a `billed_cost_usd` that includes discarded draws.
5. **Typed reference column, and per-question metadata**: options list, source dataset (not "country"), image resolution, `video_sha256`, `lossy_fallback` explained.
6. **Raw response JSON** (gzipped column or side table).
7. **Provenance block in the card**: repo commit, protocol SHA, scorer commit and patch, full upstream SHA, date, and a pinned Hub revision for users to cite.
8. **A loader or one-call re-score example** (`vladbench.rescore(hf_path)`).
9. **Datasheet sections**: intended use, license per component, PII (CODA/SODA street scenes), known biases.
10. **Name the split** `test`, not the default `train`.

## Confusing, even if not wrong

- **`protocol_sha256`**: I expected one hash per protocol. It is a per-request hash (11,175 distinct per model, with duplicates only for identical repeated questions). A name like `request_sha256` would be clearer.
- **`country`**: I expected countries. It also holds datasets ("SODA", "LingoQA") and a typo ("Amercia").
- **`sequence=True` with `frames=1`**: this happens in several tasks (Lateral median is 1). I expected sequence to mean at least 2 frames.
- **`featured`**: I expected a quality flag. It really means "shown in figures", and the reason for excluding Reka is only in `rerun.json`.
- **`other`, `accuracy_name`, `other_name`**: I had to read `tasks` to learn that `other` means IoU, pairing, or judgment depending on the task. For Judge tasks, `accuracy` is really description accuracy.
- **Leaderboard "Score" vs text "TOTAL" vs `mean_task_score`**: three names; only the first two are the same thing.
- **Reasoning labels**: the card's "off" is `none` in the data. "Sequences: images/video" in the card maps to `input_transport=ordered_image_urls/video_mp4`.
- **`carried_from_512`**: this is a count on `models` but a label (`condition`) on `answers`, and the card never defines the 512 condition.
- **Card Scoring section**: "Those rows are labelled MEAN and TOTAL", but the card has no MEAN rows.
- **Daft snippet**: it groups by float `cost_usd`, which works but reads oddly. `show(models.count_rows())` asks for 13 rows and prints 12, with no note.
