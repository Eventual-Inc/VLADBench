"""The three bounding-box tasks under three readings.

  pixels   the protocol: every box scored as native pixel coordinates (what the leaderboard shows)
  grid     each box read on the model's own convention (registry box_convention), then scaled to the frame
  none     the three box tasks left out of TOTAL

The grid reading re-marks only the box questions; choice questions and the format component keep the released
scorer's marks.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from . import paths
from .aggregate import total
from .record import Record, TaskResult
from .registry import BoxConvention, ModelInfo

BOX_TASKS: tuple[str, ...] = ("VRU_Recognition", "Vehicle_Recognition", "Obstruction_Recognition")
BOX = re.compile(r"\[\s*([^\],]*\d+[^\],]*)\s*,\s*([^\],]*\d+[^\],]*)\s*,\s*([^\],]*\d+[^\],]*)\s*,\s*([^\],]*\d+[^\],]*)\s*\]")
GRID_SIZE = 1000
HIT_IOU = 0.5
Box = tuple[float, float, float, float]


def parse_box(text: str) -> Box | None:
    """The single [x1, y1, x2, y2] in an answer, or None for zero or several boxes."""
    matches = BOX.findall(text)
    if len(matches) != 1:
        return None
    x1, y1, x2, y2 = (float(re.sub(r"[^0-9.]", "", part)) for part in matches[0])
    return x1, y1, x2, y2


def to_pixels(box: Box, convention: BoxConvention, width: int, height: int) -> Box:
    """A box in the model's own convention as frame pixels. Unit fractions are read as a fraction of the grid first."""
    if convention == "pixels":
        return box
    if sum(box) < 4:
        box = (box[0] * GRID_SIZE, box[1] * GRID_SIZE, box[2] * GRID_SIZE, box[3] * GRID_SIZE)
    if convention == "grid_yx":
        box = (box[1], box[0], box[3], box[2])
    return box[0] * width / GRID_SIZE, box[1] * height / GRID_SIZE, box[2] * width / GRID_SIZE, box[3] * height / GRID_SIZE


@dataclass(frozen=True)
class GridScore:
    composite: float
    accuracy: float
    mean_iou: float
    box_hits: float
    boxes: int


def grid_composite(task: TaskResult, questions: Sequence[dict], model_id: str, dims: Mapping[str, Sequence[int]],
                   convention: BoxConvention, box_iou: Callable[[Box, Box], float]) -> GridScore:
    """Re-mark the box questions on the model's own convention; keep the released marks for every other question."""
    weights, components = task["weights"], task["components"]
    correct = sum(q["answers"][model_id][1] for q in questions if q["kind"] != "box")
    ious = []
    for q in questions:
        if q["kind"] != "box":
            continue
        box = parse_box(q["answers"][model_id][0])
        width, height = dims[q["id"]]
        ious.append(0.0 if box is None else box_iou(to_pixels(box, convention, width, height), q["gold"]))
    hits = sum(i > HIT_IOU for i in ious)
    accuracy, mean_iou = (correct + hits) / len(questions), sum(ious) / len(ious)
    composite = 100 * (weights["accuracy"] * accuracy + weights["other"] * mean_iou + weights["instruction_following"] * components["instruction_following"])
    return GridScore(composite=composite, accuracy=accuracy, mean_iou=mean_iou, box_hits=hits / len(ious), boxes=len(ious))


def frame_sizes(task: str) -> dict[str, Sequence[int]]:
    """Frame width and height per question id; only box samples carry a size."""
    from .requests import questions

    return {q["id"]: q["sample"]["dimension"] for q in questions(task) if "dimension" in q["sample"]}


def variants(record: Record, registry: Mapping[str, ModelInfo], answers: Path = paths.ANSWERS) -> dict:
    """TOTAL per model under the three readings, and per-task grid composites, for task-review-variants.js."""
    from .scoring import load_scorer

    box_iou = load_scorer()[0].box_iou
    per_task = {t: json.loads((answers / f"{t}.json").read_text()) for t in BOX_TASKS}
    dims = {t: frame_sizes(t) for t in BOX_TASKS}
    out: dict = {"box_tasks": list(BOX_TASKS), "models": {}}
    for model in record["models"]:
        if not all(model["tasks"].get(t, {}).get("score") is not None for t in BOX_TASKS):
            continue
        convention = registry[model["id"]].box_convention
        grid_scores: dict[str, float] = {}
        detail: dict[str, dict] = {}
        for t in BOX_TASKS:
            result = model["tasks"][t]
            if convention != "pixels" and model["id"] in per_task[t]["models"]:
                score = grid_composite(result, per_task[t]["questions"], model["id"], dims[t], convention, box_iou)
                grid_scores[t] = score.composite
                detail[t] = {k: v for k, v in asdict(score).items() if k != "composite"}
            else:
                grid_scores[t] = result["score"]
                detail[t] = {"accuracy": result["components"]["accuracy"], "mean_iou": result["components"]["other"], "native": True}
        out["models"][model["id"]] = {
            "convention": "pixels" if convention == "pixels" else "grid", "y_first": convention == "grid_yx",
            "total": {"pixels": total(model["tasks"]), "grid": total(model["tasks"], override=grid_scores), "none": total(model["tasks"], skip=BOX_TASKS)},
            "tasks": {t: {"pixels": model["tasks"][t]["score"], "grid": grid_scores[t], **detail[t]} for t in BOX_TASKS},
        }
    return out
