"""The Hugging Face dataset card: docs/hf-dataset-card.md with every @PLACEHOLDER@ filled from the record.

check_card turns template mistakes into build errors: an unfilled placeholder, a table row whose column count differs
from its header, or a model in the record that the card never names.
"""
from __future__ import annotations

from collections.abc import Sequence
import re

from .aggregate import total
from .export import TABLES
from .record import ModelRecord, Record

PLACEHOLDER = re.compile(r"@[A-Z_]+@")


def money(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"${value:,.{digits}f}"


def usage(model: ModelRecord, key: str) -> float | None:
    return (model.get("usage") or {}).get(key)


def model_row(m: ModelRecord) -> str:
    transport = "video" if m["declared"]["input_transport"] == "video_mp4" else "images"
    return (f"| {m.get('lab', '')} | {m['label']} | `{m['model']}` | {m.get('parameters', 'undisclosed')} | {transport} | "
            f"{m['reasoning']} | {m['completion_cap']} | {m['truncated_answers'] or 0} |")


def cap_note(models: Sequence[ModelRecord]) -> str:
    capped = [m["label"] for m in models if m["completion_cap"] == 512]
    note = ""
    if capped:
        note = ("The archived first protocol used a 512-token completion guard. " + ", ".join(capped)
                + " ran under it and were not re-run; the Truncated column counts answers that guard cut short. ")
    for m in (m for m in models if m.get("carried_from_superseded_condition")):
        note += (f"{m['label']} first ran under an archived protocol with a 512-token completion guard. Its cut answers were re-asked "
                 f"under the live 8192 guard and the rest carried over ({m['carried_from_superseded_condition']:,} answers, `models.carried_from_512`). ")
    return note


def leaderboard(models: Sequence[ModelRecord]) -> tuple[str, str, ModelRecord]:
    """Table rows for featured models ranked by TOTAL, the note naming the models left out, and the best model."""
    ranked = sorted([m for m in models if m.get("featured", True)], key=lambda m: total(m["tasks"]), reverse=True)
    omitted = [m for m in models if not m.get("featured", True)]
    rows = "\n".join(f"| {i + 1} | {m['label']} | {total(m['tasks']):.2f} | {money(usage(m, 'cost_usd'))} | {money(usage(m, 'input_cost_per_frame_usd'), 5)} "
                     f"| {money(usage(m, 'output_cost_per_query_usd'), 5)} | {money(usage(m, 'cost_per_video_hour_usd'))} |" for i, m in enumerate(ranked))
    note = ("" if not omitted else "Also in the data but left out of the figure and this table: "
            + "; ".join(f"{m['label']} ({total(m['tasks']):.2f}, {m['not_featured_reason']})" for m in omitted) + ". `models.featured` marks them.")
    return rows, note, ranked[0]


def render_card(record: Record, template: str, *, repo: str, protocol_sha256: str) -> str:
    models = sorted(record["models"], key=lambda m: (m.get("lab", ""), m.get("size_rank", 99)))
    rows, omitted, best = leaderboard(record["models"])
    fills = {"@CONFIGS@": "\n".join(f"  - config_name: {n}\n    data_files: {n}.parquet" for n in TABLES),
             "@DATE@": record["generated_at"][:10], "@SPEC@": protocol_sha256[:12],
             "@N_MODELS@": str(len(models)), "@N_TASKS@": str(record["dataset"]["tasks"]),
             "@N_QUESTIONS@": f"{record['dataset']['questions_per_model']:,}", "@N_ANSWERS@": f"{record['dataset']['responses']:,}",
             "@N_SCORES@": str(len(models) * record["dataset"]["tasks"]), "@MODEL_ROWS@": "\n".join(model_row(m) for m in models),
             "@CAP_NOTE@": cap_note(models), "@REPO@": repo, "@BEST@": best["label"], "@LEADERBOARD@": rows, "@OMITTED@": omitted}
    card = template
    for key, value in fills.items():
        card = card.replace(key, value)
    return card


def table_errors(card: str) -> list[str]:
    """Rows whose cell count differs from the header of their table."""
    errors, width = [], None
    for number, line in enumerate(card.splitlines(), 1):
        if not line.startswith("|"):
            width = None
            continue
        cells = line.count("|") - 1
        if width is None:
            width = cells
        elif cells != width:
            errors.append(f"line {number}: {cells} cells, header has {width}")
    return errors


def check_card(card: str, record: Record) -> None:
    problems = [f"unfilled {p}" for p in sorted(set(PLACEHOLDER.findall(card)))] + table_errors(card)
    problems += [f"{m['label']} is not named" for m in record["models"] if m["label"] not in card]
    if problems:
        raise ValueError("Dataset card: " + "; ".join(problems))
