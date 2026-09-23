"""Render the Cost vs Score figure for the dataset card as a PNG.

Reads results/rerun.json; writes results/dataset/cost-vs-score.png. Colours follow specification order like the web page,
TOTAL is the question-count-weighted mean of the 28 task composites, and the dashed staircase is the Pareto frontier.
"""

import json
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[1]
RERUN = ROOT / "results/rerun.json"
OUT = ROOT / "results/dataset/cost-vs-score.png"
# Model colours come from the site so the figure and the page agree.
COLOURS = dict(re.findall(r'(\w+): "(#[0-9a-f]{6})"', (ROOT / "web/results.js").read_text().split("const MODEL_COLORS = {")[1].split("};")[0]))
BG, PANEL, INK, MUTED, LINE, ACCENT = "#000000", "#090909", "#ffffff", "#b0b0b0", "#2a2a2a", "#ff00ff"


def total(model: dict) -> float:
    pairs = [(t["score"], t["questions_scored"]) for t in model["tasks"].values()]
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs)


def frontier(points: list[dict]) -> list[dict]:
    """Non-dominated models: no other model scores higher for the same cost or less."""
    dominated = lambda p: any(q["score"] > p["score"] and q["cost"] <= p["cost"] for q in points)
    return sorted([p for p in points if not dominated(p)], key=lambda p: p["cost"])


def points_from(rerun: dict) -> list[dict]:
    out = []
    for m in rerun["models"]:
        usage = m.get("usage") or {}
        if usage.get("cost_usd") is None or not m.get("featured", True):
            continue
        out.append({"label": m["label"], "cost": usage["cost_usd"], "score": total(m), "colour": COLOURS.get(m["id"], MUTED)})
    return out


CANDIDATES = [(10, 0, "left"), (-10, 0, "right"), (0, 12, "center"), (0, -12, "center"), (10, 12, "left"), (10, -12, "left"),
              (-10, 12, "right"), (-10, -12, "right")]


def overlaps(a: tuple, b: tuple) -> bool:
    return a[0] < b[0] + b[2] and a[0] + a[2] > b[0] and a[1] < b[1] + b[3] and a[1] + a[3] > b[1]


def label_box(cx: float, cy: float, dx: float, dy: float, ha: str, w: float, h: float, px_per_pt: float) -> tuple:
    lx, ly = cx + dx * px_per_pt, cy + dy * px_per_pt
    bx = lx if ha == "left" else lx - w if ha == "right" else lx - w / 2
    return (bx, ly - h / 2, w, h)


def inside(box: tuple, bounds: tuple) -> bool:
    x0, y0, x1, y1 = bounds
    return box[0] >= x0 and box[0] + box[2] <= x1 and box[1] >= y0 and box[1] + box[3] <= y1


def choose_anchor(cx, cy, w, h, px_per_pt, boxes, bounds):
    """First candidate anchor, pushed outward step by step, whose label box overlaps nothing placed so far."""
    line_pt = h / px_per_pt
    for step in range(6):
        for dx, dy, ha in CANDIDATES:
            push = -step * line_pt if dy <= 0 else step * line_pt
            box = label_box(cx, cy, dx, dy + push, ha, w, h, px_per_pt)
            if inside(box, bounds) and not any(overlaps(box, b) for b in boxes):
                return dx, dy + push, ha, box
    return 10, 0, "left", label_box(cx, cy, 10, 0, "left", w, h, px_per_pt)


def place_labels(ax, points: list[dict]) -> None:
    """Greedy placement in pixel space: each label takes the first anchor that overlaps no dot or earlier label."""
    fig = ax.figure
    fig.canvas.draw()
    to_px = ax.transData.transform
    px_per_pt = fig.dpi / 72
    fs = plt.rcParams["font.size"] * 0.9
    char_w, h = fs * 0.58 * px_per_pt, fs * 1.25 * px_per_pt
    boxes = [(*(to_px((p["cost"], p["score"])) - 7 * px_per_pt), 14 * px_per_pt, 14 * px_per_pt) for p in points]
    bounds = (ax.bbox.x0, ax.bbox.y0, ax.bbox.x1, ax.bbox.y1)
    for p in sorted(points, key=lambda p: -p["score"]):
        text = f"{p['label']}  {p['score']:.1f}"
        cx, cy = to_px((p["cost"], p["score"]))
        dx, dy, ha, box = choose_anchor(cx, cy, len(text) * char_w, h, px_per_pt, boxes, bounds)
        boxes.append(box)
        ax.annotate(text, (p["cost"], p["score"]), xytext=(dx, dy), textcoords="offset points", ha=ha, va="center", fontsize=fs, color=INK)


def style_axes(ax, points: list[dict]) -> None:
    ax.set_facecolor(PANEL)
    ax.set_xscale("log")
    ax.grid(True, color=LINE, linewidth=0.8)
    for spine in ax.spines.values():
        spine.set_color(LINE)
    ax.tick_params(colors=MUTED, labelsize=9)
    scores, costs = [p["score"] for p in points], [p["cost"] for p in points]
    ax.set_ylim(min(scores) - 4, max(scores) + 4)
    ax.set_xlim(min(costs) / 2.5, max(costs) * 3)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"${v:g}"))
    ax.set_xlabel("Cost of the full sweep, 11,193 answers (USD, log scale)", color=MUTED, fontsize=10)
    ax.set_ylabel("TOTAL score", color=MUTED, fontsize=10)


def draw(ax, points: list[dict]) -> None:
    front = frontier(points)
    xs, ys = [p["cost"] for p in front], [p["score"] for p in front]
    ax.step(xs + [max(p["cost"] for p in points) * 1.6], ys + [ys[-1]], where="post", color=ACCENT, linestyle="--", linewidth=1.4,
            label="Cost-performance frontier: best TOTAL at each cost")
    for p in points:
        ax.scatter(p["cost"], p["score"], s=70, color=p["colour"], edgecolors=BG, linewidths=1.2, zorder=3)
    place_labels(ax, points)
    ax.legend(loc="lower right", fontsize=8.5, frameon=False, labelcolor=MUTED)


def render(out: Path = OUT, hero: bool = False) -> Path:
    rerun = json.loads(RERUN.read_text())
    points = points_from(rerun)
    families = {f.name for f in font_manager.fontManager.ttflist}
    plt.rcParams["font.family"] = "Helvetica Neue" if "Helvetica Neue" in families else "Helvetica"
    plt.rcParams["font.size"] = 14 if hero else 10
    fig, ax = plt.subplots(figsize=(16, 9) if hero else (10, 5.6), dpi=120 if hero else 200, facecolor=BG)
    style_axes(ax, points)
    draw(ax, points)
    ax.set_title("VLADBench re-evaluation: Cost vs Score" if hero else "Cost vs Score", loc="left", color=INK, fontsize=26 if hero else 15, fontweight="bold", pad=14)
    fig.text(0.01, 0.01, "Cost is what each model's full sweep was billed. Models flagged not featured in the data are omitted.", color=MUTED, fontsize=7.5, va="bottom")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=BG)
    plt.close(fig)
    return out


if __name__ == "__main__":
    print(render())
    print(render(OUT.with_name("cost-vs-score-hero.png"), hero=True))
