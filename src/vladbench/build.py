"""The ordered build: score files -> record -> site data -> answers -> variants -> parquet -> figures -> card -> site.

Each step takes the previous steps' results in memory. The record step refuses partial runs unless allow_incomplete.
The record, answers, and export steps also read the sweep records under results/runs/, which are not in git; a
checkout without them skips those steps and starts from the committed results/rerun.json.
"""
from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Literal

from . import paths
from .record import IncompleteRun, Record, build_record, load_record, write_record
from .registry import ModelInfo, load_registry, require_models
from .spec import load_spec

Step = Literal["record", "site-data", "answers", "variants", "export", "figures", "card", "site"]
STEPS: tuple[Step, ...] = ("record", "site-data", "answers", "variants", "export", "figures", "card", "site")
NEEDS_RUNS: frozenset[Step] = frozenset({"record", "answers", "export"})


@dataclass
class BuildReport:
    models: list[str] = field(default_factory=list)
    written: dict[str, list[Path]] = field(default_factory=dict)
    skipped: list[Step] = field(default_factory=list)


def have_runs(spec: dict, runs: Path) -> bool:
    """Whether any protocol model has a folder of sweep records."""
    return any((runs / m["id"]).is_dir() for m in spec["models"])


def plan(steps: Collection[str] | None, runs_present: bool) -> tuple[list[Step], list[Step]]:
    """(steps to run in order, steps skipped). With no steps named, a checkout without sweep records skips the steps that read them."""
    if steps is None:
        chosen = [s for s in STEPS if runs_present or s not in NEEDS_RUNS]
        return chosen, [s for s in STEPS if s not in chosen]
    unknown = set(steps) - set(STEPS)
    if unknown:
        raise ValueError(f"Unknown steps {sorted(unknown)}; choose from {STEPS}")
    blocked = sorted(NEEDS_RUNS & set(steps))
    if blocked and not runs_present:
        raise IncompleteRun(f"steps {blocked} read the sweep records in {paths.relative(paths.RUNS)}, which are not in git; "
                            "leave them out to build from the committed results/rerun.json")
    return [s for s in STEPS if s in steps], []


def writers(record: Record, registry: dict[str, ModelInfo], site_out: Path | None, article: str | None,
            repo: str) -> dict[Step, Callable[[], list[Path]]]:
    """One function per step, each writing that step's files and returning their paths."""
    inputs: list = []

    def task_inputs():
        if not inputs:
            from .sitedata import task_inputs as load
            inputs.append(load())
        return inputs[0]

    def site_data():
        from .sitedata import write_site_data
        return write_site_data(record, task_inputs())

    def answers():
        from .answers import write_answers
        return write_answers(record, task_inputs())

    def variants_js():
        from .boxes import variants
        from .sitedata import FILES, site_file, write_js
        return [write_js(site_file("variants"), FILES["variants"][1], variants(record, registry))]

    def export():
        from .export import export as write_tables
        return write_tables(record)

    def figures():
        from .figures import render_figures
        return render_figures(record, registry, paths.DATASET)

    def card():
        from .card import check_card, render_card
        text = render_card(record, paths.CARD_TEMPLATE.read_text(), repo=repo, protocol_sha256=hashlib.sha256(paths.PROTOCOL.read_bytes()).hexdigest())
        check_card(text, record)
        path = paths.DATASET / "README.md"
        path.write_text(text)
        return [path]

    def site():
        from .site import build_site
        return [build_site(site_out or paths.DIST / "pages", article=article)]

    return {"record": lambda: [write_record(record)], "site-data": site_data, "answers": answers, "variants": variants_js,
            "export": export, "figures": figures, "card": card, "site": site}


def build(*, steps: Collection[str] | None = None, allow_incomplete: bool = False, site_out: Path | None = None,
          article: str | None = None, repo: str = "Eventual-Inc/VLADBench-reeval") -> BuildReport:
    """Check the protocol against the registry, then run the chosen steps in order (all by default). Steps not run read what is on disk."""
    spec = load_spec(paths.PROTOCOL)
    registry = load_registry()
    require_models(registry, [m["id"] for m in spec["models"]])
    chosen, skipped = plan(steps, have_runs(spec, paths.RUNS))
    record: Record = build_record(spec, registry, allow_incomplete=allow_incomplete) if "record" in chosen else load_record()
    report = BuildReport(models=[m["id"] for m in record["models"]], skipped=skipped)
    write = writers(record, registry, site_out, article, repo)
    for step in chosen:
        report.written[step] = write[step]()
    return report
