---
license: other
license_name: cc-by-4.0-additions-upstream-unlicensed
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

We re-evaluated the VLADBench benchmark (Li et al., 2025, [arXiv:2503.21505](https://arxiv.org/abs/2503.21505)) against current SOTA VLMs under the original scoring criteria and prompts. See [Eventual-Inc/VLADBench](https://github.com/Eventual-Inc/VLADBench) for the code, and the [companion site](https://eventual-inc.github.io/VLADBench/) for interactive results.

## Cost vs Score

![Cost vs Score: TOTAL against sweep cost for every model, with the Pareto frontier](cost-vs-score.png)

Up and to the left is better. The dashed line is the cost-performance frontier which is defined by measuring the best TOTAL score available against its cost. 

## Leaderboard


| # | Model | Score | Sweep cost | Input $/frame | Output $/query | Est. $/hour of video |
|---|---|---|---|---|---|---|
@LEADERBOARD@

@OMITTED@

The per-frame, per-query, and hourly costs assume 1280×720 frames at 1 fps and 8 frames per query, with no overlap between clips. The tokeniser rules are in `src/vladbench/metering.py`.


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

We re-evaluated @N_MODELS@ current vision-language models on VLADBench with our own harness, the original paper's scoring criteria and prompts. The benchmark is unchanged using the same questions, frames, gold references, scorer, and per-task weights. 

Here is where our setup differs from the paper's:

- **Not all models support video inputs**. Frame sequences are passed as video where supported and ordered images otherwise. Sequence questions have a median of 4 to 5 frames, so we expect the temporal perception impact to be smaller than with 8-16 frame clips. Alibaba's route rejected clips under four frames, and OpenAI and Anthropic only accept images, so Qwen 3.8 Max, Claude Opus 5.5, and the OpenAI models received the frames as ordered images. The two open Qwen models received video from third-party hosts, with the Alibaba route excluded. Input differences are labeled as such. 
- **Reasoning is set to its lowest available level**. Several providers do not expose a means to disable reasoning altogether, so the lowest reasoning setting is used. GPT-6 Astra is the exception: it ran at low, though its endpoint also accepts minimal.

We think these are reasonable trade-offs given the structural differences in how models are served today. 

## Scoring

The overall score is a question-weighted average. VLADBench is comprised of 28 tasks, each with its own score. To roll scores from all tasks, we average the task scores with each task weighted by how many questions it has, so a task with 795 questions counts about four times as much as one with 200. The paper does not say how it rolled up its own numbers, but this rule reproduces 241 of the 250 group averages printed in its Table 10 to within 0.1, so we use it too. We run the paper's own scoring code, with one disclosed syntax repair. Those rows are labelled MEAN and TOTAL, as in the paper.

## Tables


| Table         | Rows          | One row is                                                                                           |
| ------------- | ------------- | ---------------------------------------------------------------------------------------------------- |
| `models`      | @N_MODELS@    | a model: label, lab, provider string, protocol declarations, spend, latency summary, mean task score |
| `tasks`       | @N_TASKS@     | a task: category, group, scorer function, the paper's component weights, sample and question counts  |
| `questions`   | @N_QUESTIONS@ | a released question: prompt, pinned frame URLs, gold reference, country                              |
| `answers`     | @N_ANSWERS@   | one model's answer to one question: text, finish reason, tokens, cost, latency, request hash         |
| `task_scores` | @N_SCORES@    | one model on one task: the paper's scoring criteria applied to our answers, components and composite |


## Models


| Lab | Model | Provider string | Parameters | Sequences | Reasoning | Completion guard | Truncated |
| --- | ----- | --------------- | ---------- | --------- | --------- | ---------------- | --------- |
@MODEL_ROWS@


@CAP_NOTE@Full declarations and footnotes are in `docs/PROTOCOL.md` in the repository.

## Cost and latency

`answers.cost_usd` is the provider-billed cost per answer as returned by OpenRouter, and `models.cost_usd` sums it over the sweep. Prices are as billed on the dates in `answers.timestamp`. `answers.elapsed_seconds` is wall-clock time per request as seen by the harness; `models` carries the 25th, 50th, 75th, and 95th percentiles.

## Known issues

- **Bounding boxes are scored in pixels.** Three tasks ask for a box. The prompt gives the image size in pixels but doesn't say what units the box should use. OpenAI and Anthropic models answer in pixels. Qwen, Muse, Gemma, MiniMax, and Reka answer on a 0 to 1000 grid, and Gemini answers on that grid with y before x, so most of their boxes miss. The three box tasks are 12% of TOTAL, so this favours the pixel models. The paper's scorer rescaled boxes for some model families by name; we don't. The Cost Performance Frontier tab on the companion site shows every model's TOTAL and the frontier with boxes read on each model's own grid and with the box tasks left out.
- **Vehicle cut-in references are almost all "yes".** 172 of the 174 yes/no references are "yes", so answering yes to everything scores about 99% on that component. The question also asks whether the vehicle has "the intention to cross the road", which reads oddly for a cut-in.
- **Some references aren't among the options.** On Traffic Light, 7 of 795 references aren't in the list the question offers, like "Malfunction" and "Manualt".
- **Weather and Light labels are ambiguous.** Every model lands within a few points of the others. The questions that stump every model have references the frames don't support, like "cloudy" versus "overcast", or a dusk clip with a bright sky and the lights on labelled nighttime.
- **Descriptive answers are exact match.** Vehicle and VRU behavior are graded against one short reference, so a reasonable answer in different words scores zero.
- **Two Qwen 3.8 27B answers hit the completion guard.** They're scored as returned, which by our own protocol means that run isn't protocol-complete.
- **Empty or cut-off answers were re-asked.** The harness re-asks up to four times when an answer is empty, cut off, or degenerate, and keeps the last one. Only the kept answer's cost is recorded, so sweep costs are a lower bound. `answers.attempt` counts these re-asks together with HTTP retries.
- **Open-weight models were served by several hosts.** OpenRouter routed Qwen 3.8 27B and Qwen 3.6 35B A3B across several third-party hosts, which can run different quantizations.
- **One Qwen 3.6 35B A3B answer ended in a provider error.** It is scored as returned.
- **Trajectory is not scored.** The release has no references or scorer for it, so TOTAL covers 28 of the 29 tasks.
- **Every model ran once.** Differences under about two points could be run-to-run noise.

The Caveats tab on the [companion site](https://eventual-inc.github.io/VLADBench/#caveats) walks through each of these with the per-question answers.

## Citation

```bibtex
@misc{vladbench_reeval_2026,
  title        = {VLADBench-reeval: a re-evaluation of vision-language models on VLADBench},
  author       = {Eventual},
  year         = {2026},
  howpublished = {\url{https://huggingface.co/datasets/@REPO@}},
  note         = {Results as of @DATE@, protocol sha256 @SPEC@}
}

@article{li2025vladbench,
  title   = {Fine-Grained Evaluation of Large Vision-Language Models in Autonomous Driving},
  author  = {Li, Yue and others},
  journal = {arXiv preprint arXiv:2503.21505},
  year    = {2025}
}
```

## Source data

Questions and frames were sourced from the released VLADBench annotations at revision `1895f22252f9a702fed95334c8e3b60280b4c626` of
[depth2world/VLADBench](https://huggingface.co/datasets/depth2world/VLADBench). This dataset adds model answers and scores only. Answer text is published as returned by each provider.

## License

Our additions are licensed CC-BY-4.0: the model answers, scores, costs, and latencies. The questions and references are the VLADBench authors' work, and they have not declared a license for them. The frames come from the source datasets VLADBench draws on, such as CODA, SODA, and LingoQA, each under its own terms. This dataset links to the frames in the upstream repository and does not host them. To request a change or removal, email everett@eventualcomputing.com.