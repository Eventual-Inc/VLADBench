"""The Cost vs Score PNGs for the dataset card and the site: TOTAL against sweep cost, with the frontier staircase.

matplotlib is imported inside render_cost_score, so the core package keeps its three dependencies (uv group: scripts).
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .aggregate import Point, frontier, total
from .record import Record
from .registry import ModelInfo

BG, PANEL, INK, MUTED, LINE, ACCENT = "#000000", "#090909", "#ffffff", "#b0b0b0", "#2a2a2a", "#ff00ff"
FOOTNOTE = "Cost is what each model's full sweep was billed. Models flagged not featured in the data are omitted."
CANDIDATES = [(10, 0, "left"), (-10, 0, "right"), (0, 12, "center"), (0, -12, "center"), (10, 12, "left"), (10, -12, "left"),
              (-10, 12, "right"), (-10, -12, "right")]


def cost_points(record: Record, registry: Mapping[str, ModelInfo]) -> list[dict]:
    """Featured models with a billed cost: label, cost, TOTAL, and colour."""
    out = []
    for m in record["models"]:
        cost = (m.get("usage") or {}).get("cost_usd")
        if cost is None or not m.get("featured", True):
            continue
        out.append({"id": m["id"], "label": m["label"], "cost": cost, "score": total(m["tasks"]), "colour": registry[m["id"]].color})
    return out


def _overlaps(a: tuple, b: tuple) -> bool:
    return a[0] < b[0] + b[2] and a[0] + a[2] > b[0] and a[1] < b[1] + b[3] and a[1] + a[3] > b[1]


def _label_box(cx: float, cy: float, dx: float, dy: float, ha: str, w: float, h: float, px_per_pt: float) -> tuple:
    lx, ly = cx + dx * px_per_pt, cy + dy * px_per_pt
    bx = lx if ha == "left" else lx - w if ha == "right" else lx - w / 2
    return (bx, ly - h / 2, w, h)


def _inside(box: tuple, bounds: tuple) -> bool:
    x0, y0, x1, y1 = bounds
    return box[0] >= x0 and box[0] + box[2] <= x1 and box[1] >= y0 and box[1] + box[3] <= y1


def _choose_anchor(cx, cy, w, h, px_per_pt, boxes, bounds):
    """First candidate anchor, pushed outward step by step, whose label box overlaps nothing placed so far."""
    line_pt = h / px_per_pt
    for step in range(6):
        for dx, dy, ha in CANDIDATES:
            push = -step * line_pt if dy <= 0 else step * line_pt
            box = _label_box(cx, cy, dx, dy + push, ha, w, h, px_per_pt)
            if _inside(box, bounds) and not any(_overlaps(box, b) for b in boxes):
                return dx, dy + push, ha, box
    return 10, 0, "left", _label_box(cx, cy, 10, 0, "left", w, h, px_per_pt)


def _segment_boxes(ax, xs: Sequence[float], ys: Sequence[float], pad: float) -> list[tuple]:
    """Pixel boxes around each segment of a staircase, so labels avoid crossing it."""
    pts = [ax.transData.transform((x, y)) for x, y in zip(xs, ys, strict=True)]
    return [(min(a[0], b[0]) - pad, min(a[1], b[1]) - pad, abs(a[0] - b[0]) + 2 * pad, abs(a[1] - b[1]) + 2 * pad)
            for a, b in zip(pts, pts[1:], strict=False)]


def _place_labels(ax, points: Sequence[dict], stair: tuple[list[float], list[float]]) -> None:
    """Greedy placement in pixel space: each label takes the first anchor that overlaps no dot or earlier label.

    Label sizes are measured with the renderer. A label pushed away from its dot gets a thin leader line.
    """
    import matplotlib.pyplot as plt

    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()  # type: ignore[attr-defined]
    to_px = ax.transData.transform
    px_per_pt = fig.dpi / 72
    fs = plt.rcParams["font.size"] * 0.9
    boxes = [(*(to_px((p["cost"], p["score"])) - 9 * px_per_pt), 18 * px_per_pt, 18 * px_per_pt) for p in points]
    boxes += _segment_boxes(ax, *stair, pad=2 * px_per_pt)
    bounds = (ax.bbox.x0, ax.bbox.y0, ax.bbox.x1, ax.bbox.y1)
    placed: list[dict[str, Any]] = []
    for p in sorted(points, key=lambda p: -p["score"]):
        text = f"{p['label']}  {p['score']:.1f}"
        probe = ax.text(0, 0, text, fontsize=fs)
        extent = probe.get_window_extent(renderer)
        probe.remove()
        cx, cy = to_px((p["cost"], p["score"]))
        dx, dy, ha, box = _choose_anchor(cx, cy, extent.width + 4, extent.height + 2, px_per_pt, boxes, bounds)
        boxes.append(box)
        placed.append({"p": p, "text": text, "dot": (cx, cy), "centre": (box[0] + box[2] / 2, box[1] + box[3] / 2),
                       "leader": abs(dy) > 12})
    _uncross(placed)
    for q in placed:
        (cx, cy), (lx, ly) = q["dot"], q["centre"]
        leader = {"arrowstyle": "-", "color": MUTED, "linewidth": 1.0, "shrinkA": 0, "shrinkB": 7} if q["leader"] else None
        ax.annotate(q["text"], (q["p"]["cost"], q["p"]["score"]), xytext=((lx - cx) / px_per_pt, (ly - cy) / px_per_pt),
                    textcoords="offset points", ha="center", va="center", fontsize=fs, color=INK, arrowprops=leader)


def _uncross(placed: list[dict]) -> None:
    """Swap the label positions of two leader lines when that shortens them; this also removes every crossing."""
    import math

    for a in placed:
        for b in placed:
            if a is b or not (a["leader"] and b["leader"]):
                continue
            now = math.dist(a["dot"], a["centre"]) + math.dist(b["dot"], b["centre"])
            if math.dist(a["dot"], b["centre"]) + math.dist(b["dot"], a["centre"]) < now:
                a["centre"], b["centre"] = b["centre"], a["centre"]


def _style_axes(ax, points: Sequence[dict]) -> None:
    import matplotlib.ticker

    ax.set_facecolor(PANEL)
    ax.set_xscale("log")
    ax.grid(True, color=LINE, linewidth=1.0)
    for spine in ax.spines.values():
        spine.set_color(LINE)
    ax.tick_params(colors=MUTED, labelsize=15)
    scores, costs = [p["score"] for p in points], [p["cost"] for p in points]
    ax.set_ylim(min(scores) - 4, max(scores) + 6)
    ax.set_xlim(min(costs) / 4, max(costs) * 3)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"${v:g}"))
    ax.set_xlabel("Cost of the full sweep, 11,193 answers (USD, log scale)", color=MUTED, fontsize=15)
    ax.set_ylabel("TOTAL score", color=MUTED, fontsize=15)


def _draw(ax, points: Sequence[dict]) -> None:
    front = frontier(Point(p["id"], p["cost"], p["score"]) for p in points)
    xs, ys = [front[0].cost], [front[0].score]
    for a, b in zip(front, front[1:], strict=False):
        xs += [b.cost, b.cost]
        ys += [a.score, b.score]
    xs.append(max(p["cost"] for p in points) * 1.6)
    ys.append(ys[-1])
    ax.plot(xs, ys, color=ACCENT, linestyle="--", linewidth=2.8, label="Cost-performance frontier: best TOTAL at each cost")
    for p in points:
        ax.scatter(p["cost"], p["score"], s=170, color=p["colour"], edgecolors=BG, linewidths=1.5, zorder=3)
    _place_labels(ax, points, (xs, ys))
    ax.legend(loc="upper left", fontsize=14, frameon=False, labelcolor=MUTED)


def render_cost_score(record: Record, registry: Mapping[str, ModelInfo], out: Path, *, hero: bool = False) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    points = cost_points(record, registry)
    families = {f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams["font.family"] = "Helvetica Neue" if "Helvetica Neue" in families else "Helvetica"
    # Sized for a blog column about 650 px wide: at 10 in across, 1 pt renders as about 0.9 px on screen.
    plt.rcParams["font.size"] = 16
    fig, ax = plt.subplots(figsize=(10, 5.625), dpi=192 if hero else 200, facecolor=BG)
    _style_axes(ax, points)
    _draw(ax, points)
    ax.set_title("VLADBench re-evaluation: Cost vs Score" if hero else "Cost vs Score", loc="left", color=INK, fontsize=26 if hero else 22, fontweight="bold", pad=14)
    if not hero:   # the hero is a cover image; the plot gets the space
        fig.text(0.01, 0.01, FOOTNOTE, color=MUTED, fontsize=12, va="bottom")
    fig.tight_layout(rect=(0, 0 if hero else 0.05, 1, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=BG)
    plt.close(fig)
    return out


def render_figures(record: Record, registry: Mapping[str, ModelInfo], out: Path) -> list[Path]:
    return [render_cost_score(record, registry, out / "cost-vs-score.png"),
            render_cost_score(record, registry, out / "cost-vs-score-hero.png", hero=True)]
