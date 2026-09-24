# AGENTS.md

This repository re-evaluates vision-language models on VLADBench, a driving-scene question-answering benchmark
(arXiv 2503.21505), with the paper's prompts, frames, references, scorer, and per-task weights. It records what every
sweep cost. Results: https://eventual-inc.github.io/VLADBench/. Data: https://huggingface.co/datasets/Eventual-Inc/VLADBench-reeval.

Procedures:

| Task | Procedure |
|---|---|
| Evaluate a model on the benchmark | `.claude/skills/evaluate-model/SKILL.md` |
| Estimate the cost of video question answering at a stated workload | `.claude/skills/estimate-video-cost/SKILL.md` |
| Audit a task's references, scoring, and model answers | `.claude/skills/audit-task/SKILL.md` |
| Known limitations of the benchmark and this re-evaluation | `docs/PROTOCOL.md`, the Known issues section of `docs/hf-dataset-card.md`, `docs/reviews/` |

## Setup

```sh
uv sync --group scripts        # Python 3.12, dependencies, dev tools; ffmpeg must be on PATH for video models
cp .env.example .env           # OPENROUTER_API_KEY for runs, HF_TOKEN only to publish
```

Run Python through `uv run`. The CLI is `uv run vladbench <command>`.

## Commands

```sh
uv run vladbench validate results/protocols/full-original.json
uv run vladbench run   <protocol.json> --smoke --models <id>   # one question per task, 28 answers; billable
uv run vladbench run   <protocol.json> --models <id>           # every unanswered question, 11,193 per model; billable; resumes
uv run vladbench score <protocol.json> --models <id>           # writes results/scores-<id>.json
uv run vladbench build                                         # rebuilds every derived file; stops if any run is partial;
                                                               # without results/runs/ it skips record, answers, export
uv run vladbench publish --dry-run                             # the Hugging Face upload; maintainers only
```

Runs are billed. Run `--smoke` first and report its cost before a full run. OpenRouter reserves the maximum
cost of every in-flight request against the account balance, so a low balance stops a sweep with HTTP 402 even when
the total cost would fit. A stopped run resumes where it left off.

## Where things are

- `results/protocols/full-original.json`: the published condition. One entry per model: endpoint, provider string,
  reasoning setting, and how frame sequences are sent (MP4 video or ordered images). Its hash identifies the condition.
- `results/models.json`: label, lab, parameters, size rank, featured flag, box convention (`pixels`, `grid`,
  `grid_yx`), and colour for every model in the published condition.
- `results/scores-<id>.json`: one model's scored results. `results/rerun.json`: every published number, built from them.
- `results/runs/`: raw answer records, not in git. `answers/<Task>.json`: every model's answer and per-question mark, in git.
- `results/dataset/`: parquet tables, dataset card, and figures, as published.
- `src/vladbench/`: runner (`run`, `requests`, `video`), scorer (`scoring`, `per_question`), billing rules
  (`metering`), and the build (`record`, `boxes`, `answers`, `export`, `card`, `figures`, `site`, `build`).
  Layout and reasons: `docs/plans/package-layout.md`.
- `original/`: the paper's scoring code and task catalog, byte for byte.

## Rules

- Never edit `original/`. It is the paper's released code, kept byte for byte with hashes.
- Never hand-edit generated files: `results/rerun.json`, `task-review-*.js`, `answers/*.json`, `results/dataset/*`.
  Change the source and run `uv run vladbench build`.
- A new model in the published condition needs an entry in `results/protocols/full-original.json` and in
  `results/models.json`. To test a model without changing the published results, put it in its own protocol file
  (see `results/protocols/gpt6-reasoning-low.json`).
- TOTAL is the question-weighted mean of the 28 task scores (`vladbench.aggregate.total`). The 29th task, Trajectory,
  has no released references or scorer and is not scored.
- One run per model: differences under about two points may be run-to-run noise.
- Before committing: `uv run ruff check .`, `uv run ty check`, `uv run pytest -q`. The pre-commit hooks run these.

## Reading results

- Leaderboard, costs, and the frontier: `results/rerun.json`, or the site's Leaderboard and Cost Performance Frontier tabs.
- The three box tasks are scored in pixels. Models that answer on a 0-1000 grid score near zero there. The frontier
  under each reading is on the Cost tab, and in `task-review-variants.js`.
- Task scores are composites of accuracy, instruction following, and a task-specific component, weighted per task as
  the paper does. They are not plain accuracy.
