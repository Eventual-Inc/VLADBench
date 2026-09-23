"""The ordered build: score files -> record -> site data -> answers -> variants -> parquet -> figures -> card -> site.

Each step takes the previous steps' results in memory. The record step refuses partial runs unless allow_incomplete.
"""
from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Literal

from . import paths
from .record import Record, build_record, load_record, write_record
from .registry import load_registry, require_models
from .spec import load_spec

Step = Literal["record", "site-data", "answers", "variants", "export", "figures", "card", "site"]
STEPS: tuple[Step, ...] = ("record", "site-data", "answers", "variants", "export", "figures", "card", "site")


@dataclass
class BuildReport:
    models: list[str] = field(default_factory=list)
    written: dict[str, list[Path]] = field(default_factory=dict)


def build(*, steps: Collection[Step] = STEPS, allow_incomplete: bool = False, site_out: Path | None = None,
          article: str | None = None, repo: str = "Eventual-Inc/VLADBench-reeval") -> BuildReport:
    """Check the protocol against the registry, then run the chosen steps in order. Steps not chosen read what is on disk."""
    unknown = set(steps) - set(STEPS)
    if unknown:
        raise ValueError(f"Unknown steps {sorted(unknown)}; choose from {STEPS}")
    spec = load_spec(paths.PROTOCOL)
    registry = load_registry()
    require_models(registry, [m["id"] for m in spec["models"]])
    report = BuildReport()
    record: Record = build_record(spec, registry, allow_incomplete=allow_incomplete) if "record" in steps else load_record()
    report.models = [m["id"] for m in record["models"]]
    inputs = None

    def task_inputs():
        nonlocal inputs
        if inputs is None:
            from .sitedata import task_inputs as load
            inputs = load()
        return inputs

    if "record" in steps:
        report.written["record"] = [write_record(record)]
    if "site-data" in steps:
        from .sitedata import write_site_data
        report.written["site-data"] = write_site_data(record, task_inputs())
    if "answers" in steps:
        from .answers import write_answers
        report.written["answers"] = write_answers(record, task_inputs())
    if "variants" in steps:
        from .boxes import variants
        from .sitedata import FILES, site_file, write_js
        report.written["variants"] = [write_js(site_file("variants"), FILES["variants"][1], variants(record, registry))]
    if "export" in steps:
        from .export import export
        report.written["export"] = export(record)
    if "figures" in steps:
        from .figures import render_figures
        report.written["figures"] = render_figures(record, registry, paths.DATASET)
    if "card" in steps:
        from .card import check_card, render_card
        card = render_card(record, paths.CARD_TEMPLATE.read_text(), repo=repo, protocol_sha256=hashlib.sha256(paths.PROTOCOL.read_bytes()).hexdigest())
        check_card(card, record)
        path = paths.DATASET / "README.md"
        path.write_text(card)
        report.written["card"] = [path]
    if "site" in steps:
        from .site import build_site
        report.written["site"] = [build_site(site_out or paths.DIST / "pages", article=article)]
    return report
