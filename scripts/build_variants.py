"""Scoring variants for the results page's Analysis tab: task-review-variants.js.

  PYTHONPATH=src python3 scripts/build_variants.py

For every model, the TOTAL under three readings of the three bounding-box tasks:
  pixels   the protocol: boxes scored in native pixels for every model (what the leaderboard shows)
  grid     the paper's per-family rescale: a box read on a 0-1000 grid scaled by the frame size, y-first for Gemini
  none     the three box tasks left out of TOTAL entirely
plus the per-task grid composites, so the page can show which tasks move. The grid reading re-marks only the box
questions; choice questions and the format component are taken from the released scorer's marks.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from vladbench.requests import questions
from vladbench.scoring import load_scorer

ROOT = Path(__file__).resolve().parents[1]
BOX_TASKS = ["VRU_Recognition", "Vehicle_Recognition", "Obstruction_Recognition"]
BOX = re.compile(r"\[\s*([^\],]*\d+[^\],]*)\s*,\s*([^\],]*\d+[^\],]*)\s*,\s*([^\],]*\d+[^\],]*)\s*,\s*([^\],]*\d+[^\],]*)\s*\]")
# Which models answer on a 0-1000 grid, and whether they write y before x. OpenAI models answer in pixels.
GRID = {"gemini38": True, "gemini25lite": True, "gemma431": False, "qwen38max": False, "qwen36or": False, "qwen38or": False,
        "muse13": False, "minimax3": False, "rekaedge": False}


def load_js(path: Path):
    text = path.read_text()
    return json.loads(text[text.index("=") + 1:].strip().rstrip(";"))


def grid_composite(model: dict, task: str, answers: dict, dims: dict, yfirst: bool, box_iou) -> tuple[float, dict]:
    result = model["tasks"][task]
    weights, components = result["weights"], result["components"]
    rows = answers["questions"]
    acc = sum(q["answers"][model["id"]][1] for q in rows if q["kind"] != "box")
    ious = []
    for q in rows:
        if q["kind"] != "box":
            continue
        w, h = dims[q["id"]]
        matches = BOX.findall(q["answers"][model["id"]][0])
        if len(matches) != 1:
            ious.append(0.0)
            continue
        box = [float(re.sub(r"[^0-9.]", "", part)) for part in matches[0]]
        if sum(box) < 4:
            box = [x * 1000 for x in box]
        if yfirst:
            box = [box[1], box[0], box[3], box[2]]
        scaled = [box[0] * w / 1000, box[1] * h / 1000, box[2] * w / 1000, box[3] * h / 1000]
        ious.append(box_iou(scaled, q["gold"]))
    acc += sum(i > 0.5 for i in ious)
    accuracy, mean_iou = acc / len(rows), sum(ious) / len(ious)
    composite = 100 * (weights["accuracy"] * accuracy + weights["other"] * mean_iou + weights["instruction_following"] * components["instruction_following"])
    return composite, {"accuracy": accuracy, "mean_iou": mean_iou, "box_hits": sum(i > 0.5 for i in ious) / len(ious), "boxes": len(ious)}


def total(model: dict, override: dict, skip: set) -> float | None:
    pairs = [((override[t] if t in override else r["score"]), r["questions_scored"])
             for t, r in model["tasks"].items() if r.get("score") is not None and t not in skip]
    return sum(a * b for a, b in pairs) / sum(b for _, b in pairs) if pairs else None


def main() -> None:
    published = load_js(ROOT / "task-review-results.js")
    box_iou = load_scorer()[0].box_iou
    answers = {t: json.loads((ROOT / "answers" / f"{t}.json").read_text()) for t in BOX_TASKS}
    dims = {t: {q["id"]: q["sample"]["dimension"] for q in questions(t) if "dimension" in q["sample"]} for t in BOX_TASKS}   # only box samples carry a frame size
    out = {"box_tasks": BOX_TASKS, "models": {}}
    for model in published["models"]:
        if not all(model["tasks"].get(t, {}).get("score") is not None for t in BOX_TASKS):
            continue
        grid_scores, detail = {}, {}
        for t in BOX_TASKS:
            if model["id"] in GRID and model["id"] in answers[t]["models"]:
                grid_scores[t], detail[t] = grid_composite(model, t, answers[t], dims[t], GRID[model["id"]], box_iou)
            else:
                grid_scores[t] = model["tasks"][t]["score"]
                detail[t] = {"accuracy": model["tasks"][t]["components"]["accuracy"], "mean_iou": model["tasks"][t]["components"]["other"], "native": True}
        out["models"][model["id"]] = {
            "convention": "grid" if model["id"] in GRID else "pixels", "y_first": GRID.get(model["id"], False),
            "total": {"pixels": total(model, {}, set()), "grid": total(model, grid_scores, set()), "none": total(model, {}, set(BOX_TASKS))},
            "tasks": {t: {"pixels": model["tasks"][t]["score"], "grid": grid_scores[t], **detail[t]} for t in BOX_TASKS},
        }
        print(f"{model['label']:24} pixels {out['models'][model['id']]['total']['pixels']:5.1f}  grid {out['models'][model['id']]['total']['grid']:5.1f}  without {out['models'][model['id']]['total']['none']:5.1f}")
    (ROOT / "task-review-variants.js").write_text("window.VARIANTS = " + json.dumps(out, separators=(",", ":")) + ";\n")


if __name__ == "__main__":
    main()
