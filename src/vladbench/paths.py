"""Every repository path the build reads or writes, in one place."""
from __future__ import annotations

from .dataset import DEFAULT_REVISION, REPO_ROOT

ROOT = REPO_ROOT
PROTOCOL = ROOT / "results/protocols/full-original.json"
REGISTRY = ROOT / "results/models.json"
RESULTS = ROOT / "results"
RUNS = ROOT / "results/runs/full-original"       # the live condition's answer records, one folder per model
RECORD = ROOT / "results/rerun.json"
AUDIT = ROOT / "results/audit"
DATASET = ROOT / "results/dataset"
ANSWERS = ROOT / "answers"
SITE_DATA = ROOT                                  # task-review-*.js sit next to results.html
CATALOG = ROOT / "original/all_task.json"
CARD_TEMPLATE = ROOT / "docs/hf-dataset-card.md"
DIST = ROOT / "dist"

DATASET_REVISION = DEFAULT_REVISION
FRAME_BASE = f"https://huggingface.co/datasets/depth2world/VLADBench/resolve/{DATASET_REVISION}/"
QUESTIONS_PER_MODEL = 11193


def relative(path) -> str:
    """A repository path as stored in the record: relative to the root, POSIX separators."""
    return path.resolve().relative_to(ROOT).as_posix()
