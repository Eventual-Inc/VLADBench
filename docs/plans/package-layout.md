# Package layout: from scripts to `vladbench build`

Status: implemented 2026-09-22 (commits 379a5cb to 5055102). Every output was rebuilt byte for byte against the old
scripts before they were deleted. Differences from the plan:

- test_build.py rebuilds the committed outputs instead of a synthetic fixture: the record step requires all 11,193
  answers per model, and the answer records are not in git. Site data, variants, the card, and the site bundle are
  checked in CI; the record and answer files are checked where the sweep records exist.
- usage.frames_per_question was dead code in the old builder and was dropped.
- aggregate.frontier keeps a pricier model that only ties the top score, the same rule as paretoFrontier in web/results.js.

## Goal

Updating the site after a sweep takes one command, `vladbench build`. It refuses to build from a partial run and writes every derived file in order. Publishing to Hugging Face takes a second command, `vladbench publish`. All logic lives in `src/vladbench/`, where it is tested, linted, and type-checked. Scripts keep only diagnostics.

## Problems this fixes

1. Updating the site takes six scripts in a fixed order, and nothing enforces the order.
2. TOTAL is defined in four places: `plot_cost_score.total`, `publish_hf.total`, `build_variants.total`, and `modelMean` in `web/results.js`.
3. Per-model metadata is spread out. Labels, labs, parameter counts, size ranks, and the featured flag are dicts in `build_review_results.py`. Box conventions are a dict in `build_variants.py`. Colours are a dict in `web/results.js`. Adding a model means editing three files, and missing one fails silently: a model missing from the box-convention dict is treated as answering in pixels.
4. `build_review_results.py` reads `results/runs/` and accepted Flash Lite's half-finished rerun.
5. Scripts pass data to each other through the site's JavaScript files (`task-review-results.js`), parsed with string slicing.
6. `ROOT = Path(__file__).resolve().parents[1]` is repeated in 9 files.
7. 0% test coverage and no type checking on the code that builds every published number.

## One new data file: `results/models.json`

The protocol file (`results/protocols/full-original.json`) declares how requests are sent. It stays as it is, because its hash identifies the condition. How we label, group, colour, and interpret each model's answers is a separate concern, so it gets its own registry:

```json
{
  "opus55": {
    "label": "Claude Opus 5.5",
    "lab": "Anthropic",
    "parameters": "undisclosed",
    "size_rank": 1,
    "featured": true,
    "box_convention": "pixels",
    "color": "#d95926"
  },
  "gemini38": { "label": "Gemini 3.8 Flash", "lab": "Google", "parameters": "undisclosed", "size_rank": 3,
                "featured": true, "box_convention": "grid_yx", "color": "#ffc15c" },
  "rekaedge": { "label": "Reka Edge", "lab": "Reka", "parameters": "7B", "size_rank": 1,
                "featured": false, "not_featured_reason": "7B edge model; kept in the data, left out of the headline figures as an outlier",
                "box_convention": "grid", "color": "#008300" }
}
```

- `box_convention` is one of `pixels`, `grid` (0–1000, x first), or `grid_yx` (0–1000, y first). There is no default. The build fails if a scored model has no entry or no convention.
- `color` moves out of `web/results.js`. The site reads it from `task-review-results.js`, and the figures read it from the registry.
- Adding a model means one protocol entry and one registry entry.

## Module skeleton

New modules are marked `new`. Existing modules are unchanged unless noted.

```
src/vladbench/
  __init__.py
  __main__.py
  cli.py            changed: adds build, publish, audit
  spec.py           changed: validates results/models.json against the protocol
  dataset.py
  requests.py
  video.py
  run.py
  scoring.py
  per_question.py
  metering.py
  paths.py          new: every repository path in one place
  registry.py       new: results/models.json
  aggregate.py      new: TOTAL, task wins, frontier
  usage.py          new: cost, latency, and video-hour summaries from run records
  record.py         new: score files -> results/rerun.json
  sitedata.py       new: the site's task-review-*.js files
  answers.py        new: answers/<Task>.json with per-question marks
  boxes.py          new: box parsing and the three box readings
  export.py         new: parquet tables
  card.py           new: dataset card rendering and checks
  figures.py        new: cost-vs-score PNGs (matplotlib, scripts group)
  site.py           new: the Pages bundle
  publish.py        new: Hugging Face upload
  build.py          new: the ordered build
```

### `paths.py`

```python
ROOT: Path                 # repository root
PROTOCOL: Path             # results/protocols/full-original.json
REGISTRY: Path             # results/models.json
RUNS: Path                 # results/runs/full-original
RESULTS: Path              # results/
RECORD: Path               # results/rerun.json
DATASET: Path              # results/dataset/
ANSWERS: Path              # answers/
SITE_DATA: Path            # repository root, where task-review-*.js live
CARD_TEMPLATE: Path        # docs/hf-dataset-card.md
DIST: Path                 # dist/
DATASET_REVISION: str      # upstream VLADBench revision, now in three scripts
FRAME_BASE: str            # https://huggingface.co/datasets/depth2world/VLADBench/resolve/<revision>/
```

### `registry.py`

```python
BoxConvention = Literal["pixels", "grid", "grid_yx"]

@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str
    lab: str
    parameters: str
    size_rank: int
    featured: bool
    box_convention: BoxConvention
    color: str
    not_featured_reason: str | None = None

def load_registry(path: Path = paths.REGISTRY) -> dict[str, ModelInfo]:
    """Read and validate results/models.json. Unknown keys and missing fields are errors."""

def require_models(registry: dict[str, ModelInfo], model_ids: Iterable[str]) -> None:
    """Fail if any protocol model has no registry entry."""
```

### `aggregate.py`

The one definition of TOTAL. `web/results.js` keeps its own copy, because the page recomputes it under task filters, and a test checks that both agree.

```python
class TaskScore(TypedDict):
    score: float
    questions_scored: int

def total(tasks: Mapping[str, TaskScore], *, skip: Collection[str] = (), override: Mapping[str, float] | None = None) -> float:
    """Question-weighted mean of task scores: the paper's TOTAL."""

def group_means(tasks: Mapping[str, TaskScore], groups: Mapping[str, Sequence[str]]) -> dict[str, float]:
    """The same weighting within each task group: Table 10's MEAN rows."""

@dataclass(frozen=True)
class Tie:
    task: str
    model_ids: tuple[str, ...]

def task_wins(scores: Mapping[str, Mapping[str, float]], task_order: Sequence[str]) -> tuple[dict[str, int], list[Tie]]:
    """Sole-leader counts per model and the tied tasks. Pure: returns counts instead of mutating the models."""

@dataclass(frozen=True)
class Point:
    model_id: str
    cost: float
    score: float

def frontier(points: Iterable[Point]) -> list[Point]:
    """Models that no other model beats on score for the same cost or less, cheapest first."""
```

### `usage.py`

Taken from `build_review_results.py` (`task_usage`, `percentile`, `latency_summary`, `answer_records`, `frames_per_question`, `detail`, `video_cost`, `flat_usage`).

```python
def answer_records(model_id: str, runs: Path = paths.RUNS) -> list[dict]:
    """Every stored answer record for one model, across task files."""

def percentile(values: Sequence[float], q: float) -> float: ...

def latency_summary(seconds: Sequence[float]) -> LatencySummary | None:
    """p25, p50, p75, p95 of per-request wall-clock time."""

def task_usage(records: Sequence[dict]) -> TaskUsage:
    """Billed cost, answer count, and median latency for one task."""

def frames_per_question() -> dict[str, int]:
    """Frame count for every question id, from the dataset. Computed once, not cached in a global."""

def video_cost(model_id: str, records: Sequence[dict], frames: Mapping[str, int]) -> VideoCost:
    """Input $/frame, output $/query, and $/video hour from the fitted metering rule and billed prices."""

def model_usage(model_id: str, records: Sequence[dict]) -> ModelUsage:
    """Sweep cost, latency summary, and video cost for one model. Replaces flat_usage."""
```

### `record.py`

Taken from `build_review_results.py` (`score_files`, `specification_entry`, `run_specifications`, `check_result`, `model_entry`, `compact_task`, `build_rerun`). The record's shape is typed, so ty checks every reader.

```python
class TaskResult(TypedDict):
    score: float
    components: dict[str, float | str]
    weights: dict[str, float]
    samples_scored: int
    questions_scored: int
    scorer_function: str
    dataset_complete: bool
    usage: TaskUsage

class ModelRecord(TypedDict):
    id: str
    label: str
    model: str
    lab: str
    parameters: str
    size_rank: int
    featured: bool
    not_featured_reason: str | None
    color: str
    box_convention: BoxConvention
    reasoning: str
    transport: str
    declared: dict
    completion_cap: int
    truncated_answers: int
    responses: int
    dataset_complete: bool
    source: str
    source_sha256: str
    summary: ModelSummary        # unweighted mean, median, task wins
    tasks: dict[str, TaskResult]
    usage: ModelUsage

class Record(TypedDict):
    schema_version: int
    kind: str
    generated_at: str
    dataset: DatasetSummary
    scorer: dict
    experiment: dict
    task_order: list[str]
    models: list[ModelRecord]
    tied_tasks: list[Tie]

class IncompleteRun(Exception):
    """A model's score file is not protocol-complete, or its run records are partial."""

def load_score_file(path: Path) -> dict: ...

def check_score_file(result: dict, path: Path, task_order: Sequence[str] | None, scorer: dict | None) -> None:
    """Same dataset revision, scorer, and task order as the other score files. Replaces check_result."""

def require_complete(model_id: str, result: dict, records: Sequence[dict]) -> None:
    """Raise IncompleteRun unless every task is complete and the run holds every answer.
    This is the check that would have stopped the half-finished Flash Lite build."""

def model_record(spec_model: dict, info: ModelInfo, result: dict, usage: ModelUsage, source: Path) -> ModelRecord: ...

def build_record(spec: dict, registry: dict[str, ModelInfo], *, allow_incomplete: bool = False) -> Record:
    """Every scored model in protocol order, with task wins and ties."""

def load_record(path: Path = paths.RECORD) -> Record: ...
def write_record(record: Record, path: Path = paths.RECORD) -> Path: ...
```

### `sitedata.py`

Taken from `build_review_results.py` (`question_item`, `task_input`, `build_task_inputs`, `write_javascript`). It also replaces the three copies of `load_js`.

```python
FILES = {
    "tasks_full": "task-review-data.js",      # REVIEW_DATA, with every question
    "tasks": "task-review-tasks.js",          # REVIEW_DATA, slim, for embeds
    "audit": "task-review-audit.js",          # REVIEW_AUDIT
    "published": "task-review-published.js",  # PUBLISHED, the paper's Table 10
    "results": "task-review-results.js",      # FULL_RESULTS, the record
    "variants": "task-review-variants.js",    # VARIANTS
}

def write_js(path: Path, variable: str, value: object) -> Path: ...
def read_js(path: Path) -> Any: ...

def task_inputs(catalog: dict, descriptions: dict) -> list[TaskInput]:
    """Each task with its category, group, scorer, description, and questions."""

def write_site_data(record: Record, task_inputs: list[TaskInput], audit: dict, published: dict, out: Path = paths.SITE_DATA) -> list[Path]:
    """Write task-review-{data,tasks,audit,published,results}.js."""
```

### `boxes.py`

Taken from `build_variants.py`. The per-model `GRID` dict is replaced by `ModelInfo.box_convention`.

```python
BOX_TASKS: tuple[str, ...] = ("VRU_Recognition", "Vehicle_Recognition", "Obstruction_Recognition")
Reading = Literal["pixels", "grid", "none"]
Box = tuple[float, float, float, float]

def parse_box(text: str) -> Box | None:
    """The single [x1, y1, x2, y2] in an answer, or None for zero or several boxes."""

def to_pixels(box: Box, convention: BoxConvention, width: int, height: int) -> Box:
    """Read a box on the model's own convention and return frame pixels. Unit fractions scale to the 0-1000 grid first."""

@dataclass(frozen=True)
class GridScore:
    composite: float
    accuracy: float
    mean_iou: float
    box_hits: float
    boxes: int

def grid_composite(task: TaskResult, questions: Sequence[dict], model_id: str, dims: Mapping[str, tuple[int, int]],
                   convention: BoxConvention, box_iou: Callable[[Box, Box], float]) -> GridScore:
    """Re-mark the box questions on the model's own grid; keep the released marks for every other question."""

def variants(record: Record, registry: dict[str, ModelInfo], answers: Path = paths.ANSWERS) -> Variants:
    """TOTAL per model under the three readings, and per-task grid composites."""
```

### `answers.py`

Taken from `build_answers.py` (`recorded_answers`, `mark_task`, `check`, `build_task`).

```python
def recorded_answers(model_id: str, task: str, runs: Path = paths.RUNS) -> dict[str, str]: ...

def mark_task(task: str, family: str, answers: Mapping[str, str], requests: Sequence[dict]) -> dict[str, Mark] | None:
    """Per-question marks under the released scorer's rules."""

def check_marks(task: str, family: str, model: ModelRecord, marks: Mapping[str, Mark]) -> None:
    """The marks re-aggregate to the task's published components, or the build stops."""

def task_answers(task: str, models: Sequence[ModelRecord], items: Sequence[dict]) -> TaskAnswers:
    """Every model's answer and mark for every question of one task."""

def write_answers(record: Record, task_inputs: Sequence[TaskInput], out: Path = paths.ANSWERS) -> list[Path]: ...
```

### `export.py`

Taken from `export_parquet.py`. Its rows are typed, and a test checks them against the card's table descriptions.

```python
TABLES: tuple[str, ...] = ("models", "tasks", "questions", "answers", "task_scores")

def model_rows(record: Record) -> list[dict]: ...
def task_rows(record: Record) -> list[dict]: ...
def question_rows(task_order: Sequence[str]) -> list[dict]: ...
def answer_row(model_id: str, record: dict, question_id: str, condition: str) -> dict:
    """Includes served_provider and served_model."""
def answer_rows(record: Record, question_ids: set[str]) -> list[dict]: ...
def score_rows(record: Record) -> list[dict]: ...
def export(record: Record, out: Path = paths.DATASET) -> list[Path]: ...
```

### `card.py`

Taken from `publish_hf.py` (`model_row`, `cap_note`, `spend`, `usd`, `leaderboard_rows`, `dataset_card`). The checks turn today's template bugs into build errors.

```python
def leaderboard(record: Record) -> tuple[str, str]:
    """Table rows for featured models ranked by TOTAL, and the note naming the models left out."""

def model_table(record: Record) -> str: ...
def cap_note(record: Record) -> str: ...

def render_card(record: Record, template: str, *, repo: str, protocol_sha256: str) -> str: ...

def check_card(card: str) -> None:
    """No unfilled @PLACEHOLDER@, every table row has its header's column count, and every model in the record appears."""
```

### `figures.py`

Taken from `plot_cost_score.py`. It imports matplotlib lazily, so the core package keeps its three dependencies.

```python
def cost_points(record: Record, registry: dict[str, ModelInfo]) -> list[Point]: ...
def render_cost_score(record: Record, registry: dict[str, ModelInfo], out: Path, *, hero: bool = False) -> Path: ...
# label placement helpers stay private: _overlaps, _label_box, _inside, _choose_anchor, _place_labels, _style_axes, _draw
```

### `site.py`

Taken from `build_blog_embed.py`, Pages mode only. The blog-bundle mode, the paste snippets, and `VIEWS` go away now that the site is on Pages. The embed list stays documented in `web/results.js`, where `EMBED_TABS` is defined.

```python
def embed_html(results_html: str) -> str:
    """results.html with the slim task file. Fails if the script tag it replaces is missing."""

def build_site(out: Path, *, article: str | None = None, blog: str | None = None) -> Path:
    """index.html, results.html, embed.html, self-test.html, web/, answers/, data files, figures, rerun.json, config.js."""
```

### `publish.py`

Taken from `publish_hf.py` (`commit_message`, `upload`, `main`). The HF Space and org-card paths are dropped.

```python
def commit_message(record: Record) -> str: ...

def publish_dataset(repo: str, folder: Path = paths.DATASET, *, token: str, dry_run: bool = False) -> str | None:
    """Upload changed files in one commit; returns the commit URL."""
```

### `build.py`

The ordered build. Each step reads the previous step's output from memory, not from the JS files.

```python
Step = Literal["record", "site-data", "answers", "variants", "export", "figures", "card", "site"]
STEPS: tuple[Step, ...] = ("record", "site-data", "answers", "variants", "export", "figures", "card", "site")

@dataclass
class BuildReport:
    written: dict[Step, list[Path]]
    models: list[str]
    skipped: list[Step]

def build(*, steps: Collection[Step] = STEPS, allow_incomplete: bool = False, site_out: Path | None = None,
          article: str | None = None) -> BuildReport:
    """Load the protocol and registry, check them against each other, then run the steps in order."""
```

### `cli.py`

```
vladbench validate SPEC
vladbench run SPEC [--models ...] [--smoke]
vladbench score SPEC [--models ...]
vladbench build [--steps record,answers,...] [--allow-incomplete] [--site dist/pages] [--article URL]
vladbench publish [--repo Eventual-Inc/VLADBench-reeval] [--dry-run]
vladbench audit                   # later: gold distributions, when the audit post needs new numbers
```

## What the scripts become

| Today | After |
|---|---|
| `scripts/build_review_results.py` | deleted: `record.py`, `usage.py`, `sitedata.py`, `registry.py` |
| `scripts/build_answers.py` | deleted: `answers.py` |
| `scripts/build_variants.py` | deleted: `boxes.py` |
| `scripts/export_parquet.py` | deleted: `export.py` |
| `scripts/plot_cost_score.py` | deleted: `figures.py` |
| `scripts/publish_hf.py` | deleted: `card.py`, `publish.py` |
| `scripts/build_blog_embed.py` | deleted: `site.py` |
| `scripts/fit_metering.py` | stays: a diagnostic report, now typed and linted, using `paths` and `usage` |
| `scripts/audit_gold_distributions.py` | moved to `scripts/archive/`; its output `results/audit/gold-distributions.json` stays committed. Rewritten as `audit.py` when needed. |
| `hosting/` | moved out of the repository (its own branch or repo) |

Callers to update: `.github/workflows/pages.yml` (`uv run vladbench build --steps site --site dist/pages`), `docs/REPRODUCTION.md`, `README.md` (layout section), and the tests that load scripts by path (`test_per_question.py`, `test_export_parquet.py`, `test_builders.py`).

## Tests

| Test file | Covers |
|---|---|
| `test_aggregate.py` | TOTAL, group means (the 241 of 250 Table 10 check), task wins, frontier, and agreement with `modelMean` in `web/results.js` on the published record |
| `test_boxes.py` | the hand-worked cases now in `test_builders.py`, plus `parse_box` and `to_pixels` for each convention |
| `test_registry.py` | every protocol model has a registry entry; unknown keys, missing conventions, and bad colours fail |
| `test_record.py` | `require_complete` rejects a partial run; the record matches the score files |
| `test_card.py` | a rendered card has no placeholders, well-formed tables, and every model |
| `test_build.py` | the whole build on a small fixture (2 models, 2 tasks, a few answers) into a temp directory; runs in CI without the sweep data |
| existing tests | unchanged, except for import paths |

## Migration

Each step keeps every output byte for byte. Before the first step, build the current outputs once and keep them as a reference: `results/rerun.json`, `task-review-*.js`, `answers/*.json`, `results/dataset/*.parquet`, and the card. After each step, rebuild and diff against the reference. A step is done when the diff is empty; the only differences allowed are ones listed in its commit message.

1. `paths.py`, `registry.py`, `results/models.json`. Scripts read the registry instead of their dicts. Output unchanged.
2. `aggregate.py`. The four TOTALs point at it. Output unchanged.
3. `usage.py`, `record.py`, `sitedata.py`, with `require_complete`. `build_review_results.py` becomes a wrapper. Output unchanged.
4. `boxes.py`, with conventions from the registry. `build_variants.py` becomes a wrapper. Output unchanged; GPT-6 Luna and Sol get an explicit `pixels` entry.
5. `answers.py`, `export.py`, `card.py`, `figures.py`, `site.py`, `publish.py`, `build.py`, and the CLI. The wrappers are deleted, and the callers and docs are updated.
6. ty on the whole repo, and the new tests in CI.

Steps 1 to 4 come before the GPT-6 and Flash Lite results are built, so that build is the first one to go through the completeness check and the explicit box conventions. Steps 5 and 6 can follow the frontier post.
