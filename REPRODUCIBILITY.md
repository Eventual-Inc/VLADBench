# Reproducing the Vehicle Cut-in companion

This is Eventual's companion analysis of the Vehicle Cut-in subset of
[Depth2World's VLADBench](https://github.com/Depth2World/VLADBench), not a new
release of the full benchmark. The upstream [paper](https://arxiv.org/abs/2503.21505)
and [dataset](https://huggingface.co/datasets/depth2world/VLADBench) provide the
benchmark, annotations, and source imagery. The fork adds an API runner,
leaderboards, an explorer, and article figures.

## What the checkout can reproduce

Run with Python 3.10 or newer from the repository root:

```sh
python3 audit_recorded_results.py
python3 -m http.server 8000
```

Open `http://localhost:8000/scoring-explorer.html` for the explorer. The audit
requires only the Python standard library and makes no network or model calls.
It checks the exported answer flags against every completed leaderboard score
column, the question denominators, completion counts, and billing arithmetic.
It prints a SHA-256 digest identifying the audited snapshot. This is an arithmetic
check of exported data, not independent verification of original responses or
provider billing.

| Artifact | Included | Reproduction limit |
| --- | --- | --- |
| `scoring-data.js` | Yes: cleaned answers, golds, prompts, grading flags, available timing and usage | Original response text/reasoning and full request provenance are not preserved here |
| `LEADERBOARD*.md`, `plots/` | Yes: recorded tables and rendered figures | Full regeneration needs raw run JSON and, for article figures, dataset images |
| `benchmark_costs.json` | Yes: manually recorded billing totals and allocation caveats | Provider receipts are not included; several charges cannot be attributed to individual runs |
| `output/Vehicle_Cutin/*.json` | No; ignored by Git | No downloadable, immutable run archive is specified in this checkout |
| `data/VLADBench/` | No; ignored by Git | Download separately; explorer thumbnails require these local frames |

The 12 completed model labels include FP8 and non-FP8 variants separately and
one fine-tuned checkpoint. They are not 12 independent base-model families.
The snapshot contains 24 official configurations: 20 completed and four incomplete.
It also contains five completed reworded configurations, including the fine-tune;
the appendix comparison displays four of those five. “Running”, “Blocked”, and
“DNF” in the saved leaderboard describe the recorded state, not live jobs.

## Scoring and exclusions

There are **87 clips and 261 source questions**, three per clip. Every leaderboard
excludes `3_1_1_86` (`JAAD_video__0246`), question 3 (zero-based index 2), leaving
**260 scored questions: 174 judgment and 86 reason**. The exclusion is encoded in
`update_leaderboard.py` and `export_scoring_explorer.py`. Its original reason and
whether it was chosen before inspecting results are not recorded here; that
provenance remains to be documented.

The displayed composite is:

```text
100 × (0.70 × judgment accuracy + 0.10 × reason accuracy + 0.20 × instruction following)
```

Judgment and reason accuracy use their own denominators (174 and 86).
Instruction following uses all 260 scored questions. It is a string-matching
heuristic in `evaluate_utils.Judge_criterion_QA`, including a substring-of-question
check; it does not validate a structured-output schema. Some reason answers are
accepted by substring matching when no competing option is present. These rules
should be inspected before interpreting the composite. The runner's standalone
`--score-only` output scores the supplied questions without the shared leaderboard
exclusion; use `update_leaderboard.py` for the article's 260-question comparison.

172 of the 174 judgment labels are yes (98.85%, rounded to 98.9%). These are
paired questions on 86 positive clips and one negative clip, not 174 independent
scenes. An always-yes answer therefore achieves 98.9% judgment accuracy. Neither
this baseline nor an improvement after rewording establishes production cut-in
performance. An offline miner's missed scenario is not direct evidence of a
driving-system safety failure.

Only complete 260-answer runs receive ranked scores. Missing timing or token
metadata means unknown, not zero. Qwen3.8 runs lack per-request metadata; their
wall times are separately recorded constants in the leaderboard generator.
Billing includes startup/idle time and configurations with different coverage;
it is not a normalized model cost comparison.

## Regenerating from original run files

Once the original run archive is available, place its JSON files in
`output/Vehicle_Cutin/`. Preserve filenames: they encode model/reasoning labels
and the `-reword` suffix. Install `uv`, then run:

```sh
uv run update_leaderboard.py
uv run update_leaderboard.py --prompt-variant cutin-reword --leaderboard LEADERBOARD-reword.md
uv run export_scoring_explorer.py
uv run generate_article_visuals.py
python3 audit_recorded_results.py
```

The last two generators also need the dataset under `data/VLADBench/`.
The scripts declare dependencies inline. Dependency versions are minimum bounds,
not a locked historical environment; exact image rendering also depends on local
fonts. The download helper currently uses the dataset's current revision. Save
its resolved revision and file checksums for a future reproducibility archive.

Download only the task, without inference, using:

```sh
uv run run_vehicle_cutin.py --download --score-only
```

## Making a new run (billable)

New model outputs may differ from the recorded snapshot. Set `OPENAI_API_KEY` in
your environment and select an OpenAI-compatible endpoint and model explicitly:

```sh
uv run run_vehicle_cutin.py --data-root ./data/VLADBench \
  --base-url https://YOUR-ENDPOINT/v1 --model YOUR_MODEL \
  --output output/Vehicle_Cutin/YOUR_MODEL.json --limit 1 --max-calls 1
```

After checking the response, omit `--limit` and `--max-calls` for a full run.
Use a distinct output filename for each model and reasoning setting; add
`--reword` and a `-reword.json` suffix for the alternate prompt. Defaults include
1280-pixel maximum image side, JPEG quality 85, low image detail, and concurrency
1. Record all overridden flags, endpoint/model revisions, hardware, and request
settings alongside a run. These defaults are not proof of the exact settings
used for every historical configuration. Do not commit API keys.

## Provenance recovered during the readiness audit

A read-only inspection of the maintainer's local records on 2026-09-11 found
29 non-smoke raw run files. All **7,569 answer entries** (29 × 87 × 3), including
empty and excluded entries, matched the checked-in snapshot's cleaned answers,
correctness flags, and instruction-following flags when processed with the
exporter's grading function. This checks correspondence to available local
records; those raw records are not included in this PR.

27 run files contain per-question completion metadata: start/end timestamps,
API elapsed time, attempts, finish reason, and token fields. Both Qwen3.8 run
files lack this metadata. The five reworded files preserve `questions_sent`
and `prompt_variant`. These records do not capture complete request arguments,
endpoint/model revisions, hardware, or a dataset revision per run.

The local Hugging Face cache contains 665 metadata records (the annotation
JSON and 664 images), all recording dataset revision
`1895f22252f9a702fed95334c8e3b60280b4c626`.
The observed `Vehicle_Cutin_E.json` has SHA-256
`52d6ae7f53a28bbd054f94e8e9cae44f90c787101e5768b1dadfa44f03c63a9a`;
its Git blob SHA-1 matches the cached etag
`7965673f6cff2941d6cb12185d7668b6bb423076`.
This is a verified annotation-file/cache association, not proof that all model
runs used that exact revision. The observed annotations specify two to seven
frames per clip. No dataset files are redistributed by this audit.

A local fine-tune serving script specifies H100, tensor parallel size 1,
maximum model length 16,384, and image tag
`vllm/vllm-openai:nightly-69715823df89b11ee684b84066390cbb9092d5c1`,
with `fla-core==0.5.2` and `flash-linear-attention==0.5.2`.
It serves `with-feedback-fp8` from a mounted model volume. This configuration
is not a checkpoint digest, model card, training-data description, or proof of
the deployment used for each recorded request.

## Attribution and release prerequisites

The retained overview and original evaluation code come from VLADBench's authors.
No root LICENSE file is present in this checkout or the inspected upstream file
listing. No license is assigned here on behalf of upstream authors or source
dataset owners. Confirm applicable code and dataset permissions before claiming
a license for the combined distribution. Images originate from multiple datasets;
accessibility on Hugging Face alone does not document their reuse terms.

Before claiming full reproducibility, publish an appropriately licensed run archive
with checksums, dataset revision, raw predictions, exact request/configuration
metadata, model/checkpoint revisions (including the fine-tune and its model card),
exclusion rationale, and dependency lock. Historical details that cannot be
recovered should remain explicitly unknown.

The remaining owner decisions require specific evidence:

| Decision | Evidence needed |
| --- | --- |
| Release a raw-run archive or explicitly limit the reproducibility claim | Approved archive location and redistribution scope; checksums of the exact released files; provenance manifest linking filenames to configurations |
| Retain the shared q3 exclusion | Written rationale and timing of the decision; source evidence for any claim that the question is malformed. The available annotation contains a question, an in-list gold answer, and three frame paths; one leading reasoning run has no answer, which alone does not establish malformation |
| Describe the fine-tune as reproducible | Public checkpoint/model card or documented access route, checkpoint revision/digest, training provenance and applicable terms, plus a deployment record linking it to these runs |
| Claim a pinned historical experiment | Per-run commands/request settings and model revisions, dataset association, runtime/dependency versions; mark unrecoverable fields unknown |
| Apply a distribution license | Upstream code permissions and applicable source-dataset/media terms; distinguish new fork contributions from inherited material |
