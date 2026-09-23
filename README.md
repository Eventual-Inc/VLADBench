# VLADBench Re-evaluation

[![CI](https://github.com/Eventual-Inc/VLADBench/actions/workflows/ci.yml/badge.svg)](https://github.com/Eventual-Inc/VLADBench/actions/workflows/ci.yml)
[![Results](https://img.shields.io/badge/results-companion-ff00ff)](https://eventual-inc.github.io/VLADBench/)
[![Dataset](https://img.shields.io/badge/%F0%9F%A4%97%20dataset-VLADBench--reeval-yellow)](https://huggingface.co/datasets/Eventual-Inc/VLADBench-reeval)

A fork of [Depth2World/VLADBench](https://github.com/Depth2World/VLADBench) that re-evaluates current
vision-language models on the benchmark and records the cost of every evaluation. The benchmark, its questions,
references, and scoring code are the work of the original authors ([paper](https://arxiv.org/abs/2503.21505),
[dataset](https://huggingface.co/datasets/depth2world/VLADBench), [upstream README](docs/upstream-readme.md)). This
fork is not affiliated with them. Its scores should be cited as this re-evaluation, not as results from the paper.

## Announcement

**2026-09-22.** Claude Opus 5.5, GPT-6 Luna, and GPT-6 Sol added; Gemini 2.5 Flash Lite re-run with reasoning off.
The re-evaluation now covers 15 models and 167,895 scored answers. `vladbench build` replaces the build scripts, and
per-answer serving hosts are published with the dataset.

## Overview

- The released VLADBench questions, frames, references, prompts, scoring code, and per-task weights, unchanged:
  28 scored tasks, 11,193 questions per model. The 29th task, Trajectory, has no released references or scorer.
- One protocol file per evaluation condition, fixing the dataset revision, prompt handling, completion guard, and
  each model's endpoint, reasoning setting, and frame transport. Every stored answer carries a hash of its request.
- Any OpenAI-compatible chat completions endpoint: OpenRouter, a provider API, or a local vLLM server. Frame sequences
  are sent as MP4 video where a model accepts it and as ordered images otherwise.
- Billed cost per answer, and cost per hour of video from tokeniser rules fitted to the billed tokens.
- Per-question marks that re-aggregate exactly to the released scorer's components.
- A static results site, a parquet dataset on Hugging Face, and a build that stops on a partial run.

## Install

```sh
git clone https://github.com/Eventual-Inc/VLADBench && cd VLADBench
uv sync --group scripts
cp .env.example .env        # OPENROUTER_API_KEY, or the key variable a protocol entry names
```

Video models need `ffmpeg` on `PATH`.

## Basic Usage

### Evaluating a model

```sh
uv run vladbench validate results/protocols/full-original.json
uv run vladbench run   results/protocols/full-original.json --smoke --models gemini38   # one question per task
uv run vladbench run   results/protocols/full-original.json --models gemini38           # all unanswered questions; resumes
uv run vladbench score results/protocols/full-original.json --models gemini38           # writes results/scores-gemini38.json
```

Runs are billed. Run `--smoke` first; its 28 answers show the endpoint works and give a cost estimate.

### Adding a model

A protocol entry declares how the model is called:

| Field | Meaning |
|---|---|
| `endpoint`, `model` | Chat completions URL and the provider's model string |
| `credential.variable` | Environment variable holding the API key |
| `reasoning_effort` | `none` where reasoning can be disabled, otherwise the lowest accepted level |
| `input_transport` | `video_mp4` or `ordered_image_urls` |

To evaluate a model without changing the published results, place it in its own protocol file
(`results/protocols/gpt6-reasoning-low.json` is an example). To add it to the published results, add it to
`results/protocols/full-original.json` and `results/models.json`, which holds its label, lab, box convention, and colour.

### Building the results

```sh
uv run vladbench build            # record, site data, answers, variants, parquet, figures, dataset card, site
uv run vladbench build --steps site --site dist/pages
```

The build refuses a model whose run is partial or whose answers are newer than its score file.

## Advanced Usage

### Reading results in Python

```python
import json
from vladbench.aggregate import total
from vladbench.boxes import BOX_TASKS

record = json.load(open("results/rerun.json"))
for model in record["models"]:
    print(model["label"], round(total(model["tasks"]), 2), round(total(model["tasks"], skip=BOX_TASKS), 2))
```

`total` is the question-weighted mean of task scores, the rule that reproduces the paper's Table 10 rows.

### Bounding-box conventions

Three tasks ask for a bounding box. The protocol scores every box in pixels. Models that answer on a 0-1000 grid are
recorded in `results/models.json` as `grid` or `grid_yx`, and `vladbench.boxes` rescores their boxes on that grid.
The site's Cost Performance Frontier tab shows every model under both readings and with the box tasks left out.

### Cost of video question answering

`vladbench.metering` holds one tokeniser rule per model. `vladbench.metering.hourly_cost` gives the cost of an hour of
video at a stated frame size, frame rate, and clip length. `scripts/fit_metering.py` refits the rules against the
sweeps and reports the residuals.

### Agents

[`AGENTS.md`](AGENTS.md) describes the repository for coding agents. `.claude/skills/` holds procedures to evaluate a
model, estimate video cost, and audit a task.

## Visualizing Results

The results site, https://eventual-inc.github.io/VLADBench/, has an overview with the paper's Table 10 layout, a
leaderboard, every answer to every question, the cost-performance frontier with a video cost calculator, the
benchmark's caveats, and the 2025 and 2026 score distributions. Each panel can be embedded with `embed.html?embed=<name>`.
[`docs/companion.md`](docs/companion.md) explains each panel.

The dataset, https://huggingface.co/datasets/Eventual-Inc/VLADBench-reeval, has five tables:

| Table | One row is |
|---|---|
| `models` | a model, with its protocol declarations, spend, and latency |
| `tasks` | a task, with its scorer and the paper's weights |
| `questions` | a released question, with its prompt, frame URLs, and reference |
| `answers` | one model's answer to one question, with tokens, cost, latency, and serving host |
| `task_scores` | one model's score on one task, with its components |

## Repository Layout

| Path | Contents |
|---|---|
| `src/vladbench/` | runner, scorer, billing rules, and the build; layout in [`docs/plans/package-layout.md`](docs/plans/package-layout.md) |
| `results/protocols/` | protocol files, one per condition |
| `results/models.json` | model registry |
| `results/scores-*.json`, `results/rerun.json` | score files and the record built from them |
| `answers/` | every model's answer and per-question mark, per task |
| `original/` | the paper's scoring code and task catalog, byte for byte, with hashes |
| `docs/` | [protocol and limitations](docs/PROTOCOL.md), [reproduction](docs/REPRODUCTION.md), reviews, and plans |

## Known Limitations

Each model ran once; differences under about two points may be run-to-run noise. Reasoning settings differ where a
provider does not allow reasoning to be disabled. Several tasks have reference or grading problems documented in
[`docs/PROTOCOL.md`](docs/PROTOCOL.md) and the dataset card's
[known issues](https://huggingface.co/datasets/Eventual-Inc/VLADBench-reeval#known-issues).

## How to Contribute

Open an issue or a pull request. Before committing:

```sh
uv run ruff check .
uv run ty check
uv run pytest -q
uvx pre-commit install --hook-type pre-commit --hook-type pre-push    # runs the same checks on commit and push
```

Never edit `original/`, and never hand-edit generated files; change the source and run `uv run vladbench build`.

## Optional Extras

| Requirement | Needed for |
|---|---|
| `uv sync --group scripts` | the build (pyarrow, matplotlib) and publishing (huggingface_hub) |
| `uv sync` | tests, lint, and types only |
| `ffmpeg` | models that receive video |
| `OPENROUTER_API_KEY` | runs through OpenRouter |
| `HF_TOKEN` | `vladbench publish`, maintainers only |

## Cite as

```bibtex
@misc{vladbench_reeval_2026,
  title        = {VLADBench-reeval: a re-evaluation of vision-language models on VLADBench},
  author       = {Eventual},
  year         = {2026},
  howpublished = {\url{https://github.com/Eventual-Inc/VLADBench}}
}

@article{li2025vladbench,
  title   = {Fine-Grained Evaluation of Large Vision-Language Models in Autonomous Driving},
  author  = {Li, Yue and Tian, Meng and Lin, Zhenyu and Zhu, Jiangtong and Zhu, Dechang and Liu, Haiqiang and Wang, Zining and Zhang, Yueyi and Xiong, Zhiwei and Zhao, Xinhai},
  journal = {arXiv preprint arXiv:2503.21505},
  year    = {2025}
}
```
