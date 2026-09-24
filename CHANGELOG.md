# Changelog

Each release is a tag of this repository and a version of the
[Hugging Face dataset](https://huggingface.co/datasets/Eventual-Inc/VLADBench-reeval). Scores cited from this
re-evaluation should name the release.

## Unreleased

## v1.0.0 — 2026-09-24

First release of the re-evaluation.

### Models

15 models, each on all 11,193 released questions under `results/protocols/full-original.json`: Gemini 3.8 Flash,
Gemini 2.5 Flash Lite, Gemma 4 31B, GPT-5.6 Luna, GPT-5.6 Sol, GPT-6 Astra, GPT-6 Luna, GPT-6 Sol, Claude Opus 5.5,
Qwen 3.8 Max, Qwen 3.8 27B, Qwen 3.6 35B A3B, Muse Spark 1.3, MiniMax M3, and Reka Edge. 167,895 scored answers.

### Added

Evaluation
- Protocol-driven runner and scorer: one protocol file per condition, a request hash on every answer, and the paper's
  scoring code kept byte for byte in `original/`.
- `vladbench validate`, `run`, `score`, `build`, and `publish`, with help text for each command.
- Smoke test: `run --smoke` asks a few whole samples of every task, 99 questions, enough for the scorer to score all
  28 tasks. `score --smoke` scores them and writes `scores.json` beside the answers, never to `results/`.
- A model's questions across all tasks share one request pool, so a smoke run takes about 3 minutes instead of 24.
- Every API key is checked before anything is written or billed.
- `score` refuses to replace a score file that has more answers than it found; `--force` replaces it.
- Expected CLI errors print one line; `VLADBENCH_DEBUG=1` shows the traceback.

Results and cost
- Billed cost per answer, and tokeniser rules for cost per hour of video (`vladbench.metering`).
- Per-question marks that re-aggregate to the released scorer's components (`answers/<Task>.json`).
- Model registry (`results/models.json`) with each model's label, lab, colour, and box convention.
- Frontier and totals under three bounding-box readings (`vladbench.boxes`).

Build and publishing
- `vladbench build` replaces the build scripts. It refuses partial runs and stale score files.
- On a checkout without the raw answer records, `build` skips the record, answers, and export steps, says so, and
  builds the site data, figures, dataset card, and site from the committed `results/rerun.json`.
- The parquet dataset on Hugging Face, with the serving host of every answer.

Results site (https://eventual-inc.github.io/VLADBench/)
- Overview in the paper's Table 10 layout, leaderboard, every answer to every question, the cost-performance frontier
  with a video cost calculator, caveats, and the 2025 and 2026 score distributions.
- Serving Efficiency table under the frontier: answer time, cost per video hour, and score.
- Every panel embeddable with `embed.html?embed=<name>`; panel descriptions link to `docs/companion.md`.
- Figures and embeds readable at blog width: larger text and markers, leader lines for displaced labels, and plots
  drawn at container width. The hero PNG drops the footnote.
- Links to the article from the README, the dataset card, and the site's navigation.

Documentation and tooling
- README in the layout of an evaluation harness fork, with a table of what each command needs and a dated log of
  announcements; the upstream README is in `docs/upstream-readme.md`.
- `AGENTS.md` and procedures in `.claude/skills/` to evaluate a model, estimate video cost, and audit a task.
- CI, pre-commit hooks (ruff, ty, codespell), and tests for every module; 94% line coverage.

### Method notes

- Bounding boxes are scored in pixels for every model; models that answer on a 0-1000 grid are also reported on their
  own grid.
- Gemini 2.5 Flash Lite runs with reasoning off; its earlier reasoning-low answers are archived.
- Known limitations: `docs/PROTOCOL.md` and the dataset card's Known issues.
