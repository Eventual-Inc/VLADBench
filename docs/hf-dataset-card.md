---
license: cc-by-4.0
pretty_name: VLADBench-reeval
language:
  - en
task_categories:
  - visual-question-answering
tags:
  - autonomous-driving
  - benchmark
  - vision-language
size_categories:
  - 100K<n<1M
configs:
@CONFIGS@
---

# VLADBench-reeval

We re-evaluated the VLADBench benchmark (Li et al., 2025, [arXiv:2503.21505](https://arxiv.org/abs/2503.21505)) against current SOTA VLMs under the original scoring criteria and prompts. Please see  [Eventual-Inc/VLADBench](https://github.com/Eventual-Inc/VLADBench) for our implementation. The report with interactive figures is on the [Eventual blog](). 

## Cost vs Score

![Cost vs Score: TOTAL against sweep spend for every model, with the Pareto frontier](cost-vs-score.png)

Up and to the left is better. The dashed line is the cost-performance frontier which is defined by measuring the best TOTAL score available against it's cost. 

## Leaderboard


| # | Model | TOTAL | Sweep cost | Input $/frame | Output $/query | Est. $/hour of video |
|---|---|---|---|---|---|---|
@LEADERBOARD@

The last three columns meter video question answering at 1280x720. Input cost per frame is the tokeniser rule fitted to our billed tokens (`vladbench.metering`: OpenAI bills about 1.2 tokens per 32x32 patch at its cache-write rate, Qwen bills per pair of frames in proportion to area, Google's video path bills a flat count per frame) times the per-token price the sweep was actually charged. Output cost per query is the billed completion cost per answer, reasoning tokens included. The hourly estimate applies one workload: a 1 FPS feed cut into non-overlapping 8-frame clips with one question each, so 3,600 frames and 450 queries an hour. The rules are checked against every sweep and live against the API in `tests/test_metering.py`; residuals at 720p are under 10% for OpenAI and Google and within host variance for Qwen, whose OpenRouter hosts differ in frame sampling. Models without a fitted rule show n/a. `models.input_cost_per_frame_usd`, `models.output_cost_per_query_usd`, and `models.cost_per_video_hour_usd` carry them.


@OMITTED@

The same table from the parquet files with [Daft](https://www.daft.ai):

```python
import daft
from daft import col

base = "hf://datasets/@REPO@/"
scores = daft.read_parquet(base + "task_scores.parquet")
models = daft.read_parquet(base + "models.parquet")

leaderboard = (
    scores.join(models.where(col("featured")), on="model_id")
    .with_column("weighted", col("score") * col("questions_scored"))
    .groupby("label", "cost_usd")
    .agg(col("weighted").sum().alias("weighted"), col("questions_scored").sum().alias("questions"))
    .with_column("TOTAL", col("weighted") / col("questions"))
    .select("label", "TOTAL", "cost_usd")
    .sort("TOTAL", desc=True)
)
leaderboard.show(models.count_rows())
```

## Re-Evaluating VLADBench in 2026

We re-evaluated @N_MODELS@ current vision-language models on VLADBench with our own harness, the original paper's  scoring criteria and prompts. The benchmark is unchanged using the same questions, frames, gold references, scorer, and per-task weights. 

Here is where our setup differs from the paper's:

- **Not all models support video inputs**. Frame sequences are passed as video where supported and ordered images otherwise. Most tasks only provide 2 or 3 frames so we expect the temporal perception impact to be smaller than 8-16 frame clips. Alibaba ended up rejecting clips under four frames, and OpenAI only accepts images, so those models received the frames as ordered images. Input differences are labeled as such. 
- **Reasoning is set to its lowest available level**. Several providers do not expose a means to disable reasoning all together, so the lowest reasoning settings is used.

We think these are reasonable trade-offs given the structural differences in how models are served today. 

## Scoring

The overall score is a question-weighted average. VLADBench is comprised of 28 tasks, each with its own score. To roll scores from all tasks, we average the task scores with each task weighted by how many questions it has, so a task with 795 questions counts about four times as much as one with 200. The paper does not say how it rolled up its own numbers, but this rule reproduces the group averages and overall scores printed in its Table 10, so we use it too. Those rows are labelled MEAN and TOTAL, as in the paper.
one reproduces the published rows for the paper's own models.

## Tables


| Table         | Rows          | One row is                                                                                           |
| ------------- | ------------- | ---------------------------------------------------------------------------------------------------- |
| `models`      | @N_MODELS@    | a model: label, lab, provider string, protocol declarations, spend, latency summary, TOTAL           |
| `tasks`       | @N_TASKS@     | a task: category, group, scorer function, the paper's component weights, sample and question counts  |
| `questions`   | @N_QUESTIONS@ | a released question: prompt, pinned frame URLs, gold reference, country                              |
| `answers`     | @N_ANSWERS@   | one model's answer to one question: text, finish reason, tokens, cost, latency, protocol hash        |
| `task_scores` | @N_SCORES@    | one model on one task: the paper's scoring criteria applied to our answers, components and composite |


## Models


| Lab          | Model | Provider string | Parameters | Sequences | Reasoning | Completion guard | Truncated |
| ------------ | ----- | --------------- | ---------- | --------- | --------- | ---------------- | --------- |
| @MODEL_ROWS@ |       |                 |            |           |           |                  |           |


@CAP_NOTE@Full declarations and footnotes are in `docs/PROTOCOL.md` in the repository.

## Scoring

We follow the same scoring criteria as the original paper, running its own scoring code unchanged, and roll tasks up the way the paper does by weighting each task by its number of questions. Reference the repository for the code. 

## Cost and latency

`answers.cost_usd` is the provider-billed cost per answer as returned by OpenRouter, and `models.cost_usd` sums it over the sweep. Prices are as billed on the dates in `answers.timestamp`. `answers.elapsed_seconds` is wall-clock time per request as seen by the harness; `models` carries the 25th, 50th, 75th, and 95th percentiles.

## Citation

```bibtex
@misc{vladbench_reeval_2026,
  title        = {VLADBench-reeval: a re-evaluation of vision-language models on VLADBench},
  author       = {Eventual},
  year         = {2026},
  howpublished = {\url{https://huggingface.co/datasets/@REPO@}},
  note         = {Best TOTAL at publication: @BEST@}
}
```

## Source data

Questions and frames were sourced from the released VLADBench annotations at revision `1895f222` of
[depth2world/VLADBench.](https://huggingface.co/datasets/depth2world/VLADBench)  This dataset adds model answers and scores only. Answer text is published as returned by each provider.