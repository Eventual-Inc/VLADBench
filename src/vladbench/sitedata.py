"""The results page's data files, task-review-*.js, next to results.html."""
from __future__ import annotations

from collections.abc import Sequence
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from . import paths
from .record import Record, load_json

FILES = {
    "tasks_full": ("task-review-data.js", "REVIEW_DATA"),      # every task with every question
    "tasks": ("task-review-tasks.js", "REVIEW_DATA"),          # the same without questions, for embeds
    "audit": ("task-review-audit.js", "REVIEW_AUDIT"),
    "published": ("task-review-published.js", "PUBLISHED"),    # the paper's Table 10
    "results": ("task-review-results.js", "FULL_RESULTS"),     # the record
    "variants": ("task-review-variants.js", "VARIANTS"),
}


def write_js(path: Path, variable: str, value: object) -> Path:
    """window.<variable> = <compact JSON>; with '<' escaped so the payload cannot close a script tag."""
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    path.write_text(f"window.{variable} = {payload};\n")
    return path


def read_js(path: Path) -> Any:
    text = path.read_text()
    return json.loads(text[text.index("=") + 1:].strip().rstrip(";"))


def site_file(key: str, root: Path = paths.SITE_DATA) -> Path:
    return root / FILES[key][0]


def question_item(folder: Path, name: str, sample: dict, sample_index: int, index: int) -> dict:
    """One released question with its pinned frame URLs and gold answer."""
    raw = sample["questions"][index]
    selector, text = (part.strip() for part in raw.split(";", 1))
    sequence = selector.startswith("[") and selector.endswith("]")
    frames = [folder / name / sample["sequence"] / f for f in sample[selector[1:-1]]] if sequence else [folder / name / selector]
    prefix = f"The {'sequence' if sequence else 'image'} is from {sample['country']}. "
    return dict(id=sample.get("id", sample.get("sequence", str(sample_index + 1))), sequence=sample.get("sequence"),
                question=index + 1, raw=raw, prompt=prefix + text, selector=selector, gold=sample["reference"][index],
                images=[dict(path=paths.FRAME_BASE + quote(p.as_posix(), safe="/"), exists=True, remote=True) for p in frames])


def task_input(category: str, group: str, name: str, scorer: str | None) -> dict:
    folder = Path(category) / group
    source = folder / (name + "_E.json")
    metadata = paths.AUDIT / "gold_metadata" / source
    samples = json.loads(metadata.read_text()) if metadata.exists() else []
    items = [question_item(folder, name, sample, sample_index, index)
             for sample_index, sample in enumerate(samples) for index in range(len(sample["questions"]))]
    return dict(name=name, category=category, group=group, source=paths.FRAME_BASE + quote(source.as_posix(), safe="/"),
                revision=paths.DATASET_REVISION, scorer=scorer, samples=len(samples), items=items)


def task_inputs() -> list[dict]:
    """Every released question, gold answer, and pinned image URL, with each task's description and scoring rule."""
    from .scoring import load_scorer

    catalog = load_json(paths.CATALOG)
    scorers = {task: fn.__name__ for task, fn in load_scorer()[0].func_mapping.items()}
    described = load_json(paths.AUDIT / "task-descriptions.json")
    inputs = [task_input(category, group, name, scorers.get(name))
              for category, groups in catalog.items() for group, names in groups.items() for name in names]
    for task in inputs:
        rule = described["scoring"].get(task["scorer"] or "", {})
        task.update(description=described["tasks"].get(task["name"], ""), scoring_label=rule.get("label", ""), scoring_rule=rule.get("rule", ""))
    return inputs


def write_site_data(record: Record, inputs: Sequence[dict], root: Path = paths.SITE_DATA) -> list[Path]:
    """task-review-{data,tasks,audit,published,results}.js. The variants file is written by the variants step."""
    audit = load_json(paths.AUDIT / "gold-distributions.json")
    published = load_json(paths.AUDIT / "published-results-2025.json")
    slim = [dict(task, items=[], question_count=len(task["items"])) for task in inputs]
    return [write_js(site_file(key, root), FILES[key][1], value)
            for key, value in (("tasks_full", list(inputs)), ("tasks", slim), ("audit", audit), ("published", published), ("results", record))]
