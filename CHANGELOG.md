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

- Protocol-driven runner and scorer: one file per condition, request hashes on every answer, the paper's scoring code
  preserved byte for byte.
- Billed cost per answer and tokeniser rules for cost per hour of video (`vladbench.metering`).
- Per-question marks that re-aggregate to the released scorer's components (`answers/<Task>.json`).
- Results site at https://eventual-inc.github.io/VLADBench/ and the parquet dataset with serving host per answer.
- `vladbench build` and `vladbench publish`; the build refuses partial runs and stale score files, and `score` refuses
  to replace a score file that has more answers than it found.
- Model registry (`results/models.json`) with each model's box convention.
- Frontier and totals under three bounding-box readings (`vladbench.boxes`).
- CI, pre-commit hooks, `AGENTS.md`, and procedures for agents in `.claude/skills/`.

### Method notes

- Bounding boxes are scored in pixels for every model; models that answer on a 0-1000 grid are also reported on their
  own grid.
- Gemini 2.5 Flash Lite runs with reasoning off; its earlier reasoning-low answers are archived.
- Known limitations: `docs/PROTOCOL.md` and the dataset card's Known issues.
