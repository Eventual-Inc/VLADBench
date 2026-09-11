#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.7", "numpy>=1.24", "Pillow>=10"]
# ///
"""Generate the Eventual-styled figures used by ARTICLE.md."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from textwrap import fill

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from PIL import Image

from update_leaderboard import (
    generate_request_latency_plot,
    list_run_paths,
    parse_run,
)

ROOT = Path(__file__).resolve().parent
TASK = "Vehicle_Cutin"
DATA_PATH = (
    ROOT
    / "data"
    / "VLADBench"
    / "Target_Attribute_Comprehension"
    / "Intention_Judgment"
    / "Vehicle_Cutin_E.json"
)
IMAGE_ROOT = DATA_PATH.with_name(TASK)
RUN_ROOT = ROOT / "output" / TASK
OUTPUT_ROOT = ROOT / "plots" / "article"
COST_PATH = ROOT / "benchmark_costs.json"

COLORS = {
    "midnight": "#000000",
    "panel": "#050505",
    "panel_alt": "#090909",
    "paper": "#ffffff",
    "cream": "#f5f4ef",
    "steel": "#b0b0b0",
    "mineral": "#8a8a8a",
    "signal": "#ff00ff",
    "amber": "#c98016",
    "failure": "#f36a72",
    "grid": "#1a1a1a",
    "grid_minor": "#111111",
}

PROMPT_SAMPLE_ID = "3_1_1_0"
NEGATIVE_SAMPLE_ID = "3_1_1_64"
BOX_FLIP_SAMPLE_ID = "3_1_1_54"
EXCLUDED_REASON_SAMPLE_ID = "3_1_1_86"


def available_font(preferred: tuple[str, ...], fallback: str) -> str:
    """Return the first installed font from a preferred list."""
    installed = {font.name for font in font_manager.fontManager.ttflist}
    return next((name for name in preferred if name in installed), fallback)


DISPLAY_FONT = available_font(
    ("Arial", "Helvetica Neue", "Helvetica"),
    "DejaVu Sans",
)
MONO_FONT = available_font(
    ("Menlo", "SF Mono", "Consolas", "Andale Mono"),
    "DejaVu Sans Mono",
)


def load_json(path: Path) -> list[dict]:
    """Load a benchmark or prediction JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def sample_by_id(samples: list[dict], sample_id: str) -> dict:
    """Find exactly one benchmark sample by ID."""
    matches = [sample for sample in samples if sample["id"] == sample_id]
    if len(matches) != 1:
        raise ValueError(f"Expected one sample for {sample_id}, found {len(matches)}")
    return matches[0]


def sequence_paths(sample: dict, field: str) -> list[Path]:
    """Resolve image paths for a benchmark sequence."""
    paths = [
        IMAGE_ROOT / sample["sequence"] / filename
        for filename in sample[field]
    ]
    missing = [path for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing sequence images: {missing}")
    return paths


def representative_three(paths: list[Path]) -> list[Path]:
    """Select the first, middle, and final frames without duplication."""
    if len(paths) < 3:
        return paths
    return [paths[0], paths[len(paths) // 2], paths[-1]]


def clean_answer(value: str) -> str:
    """Normalize punctuation and capitalization for display."""
    return value.strip().rstrip(".").lower()


def yes_or_no(value: str) -> str:
    """Normalize model output to a yes/no token."""
    normalized = re.sub(r"[^a-z]", "", value.lower())
    if normalized.startswith("yes"):
        return "yes"
    if normalized.startswith("no"):
        return "no"
    raise ValueError(f"Not a yes/no answer: {value!r}")


def new_figure(
    kicker: str,
    title: str,
    subtitle: str | None = None,
    *,
    figsize: tuple[float, float] = (12, 7.5),
) -> plt.Figure:
    """Create a black Eventual-style publication canvas."""
    figure = plt.figure(figsize=figsize, facecolor=COLORS["midnight"])
    figure.text(
        0.065,
        0.94,
        kicker,
        color=COLORS["signal"],
        fontfamily=MONO_FONT,
        fontsize=9,
        va="top",
    )
    figure.text(
        0.065,
        0.885,
        title,
        color=COLORS["paper"],
        fontfamily=DISPLAY_FONT,
        fontsize=24,
        fontweight="bold",
        va="top",
    )
    if subtitle:
        figure.text(
            0.065,
            0.83,
            subtitle,
            color=COLORS["steel"],
            fontfamily=MONO_FONT,
            fontsize=9,
            va="top",
        )
    return figure


def add_footer(figure: plt.Figure, text: str) -> None:
    """Add a compact source note."""
    figure.text(
        0.065,
        0.028,
        text,
        color=COLORS["mineral"],
        fontfamily=MONO_FONT,
        fontsize=6.5,
        va="bottom",
    )


def add_divider(
    figure: plt.Figure,
    y: float,
    *,
    x_start: float = 0.065,
    x_end: float = 0.94,
    color: str = COLORS["grid"],
) -> None:
    """Draw a structural hairline in figure coordinates."""
    figure.add_artist(
        Line2D(
            [x_start, x_end],
            [y, y],
            transform=figure.transFigure,
            color=color,
            linewidth=0.8,
        )
    )


def add_image(
    figure: plt.Figure,
    path: Path,
    bounds: tuple[float, float, float, float],
    *,
    label: str | None = None,
    border: str = COLORS["grid"],
    zorder: int = 1,
) -> None:
    """Place one framed image on a figure."""
    axes = figure.add_axes(bounds, zorder=zorder)
    with Image.open(path) as image:
        axes.imshow(image.convert("RGB"))
    axes.set_axis_off()
    axes.add_patch(
        Rectangle(
            (0, 0),
            1,
            1,
            transform=axes.transAxes,
            fill=False,
            edgecolor=border,
            linewidth=1.0,
        )
    )
    if label:
        axes.text(
            0.025,
            0.95,
            label,
            transform=axes.transAxes,
            color=COLORS["paper"],
            fontfamily=MONO_FONT,
            fontsize=6.5,
            va="top",
            bbox={
                "facecolor": COLORS["midnight"],
                "edgecolor": "none",
                "pad": 2.5,
                "alpha": 0.82,
            },
        )


def add_image_stack(
    figure: plt.Figure,
    paths: list[Path],
    *,
    x: float,
    y: float,
    width: float,
    title: str,
    border: str,
) -> None:
    """Place two or three overlapping sequence frames."""
    chosen = representative_three(paths)
    frame_width = width * 0.82
    figure_width, figure_height = figure.get_size_inches()
    frame_height = frame_width * figure_width / (16 / 9) / figure_height
    x_step = width * 0.085
    y_step = 0.022

    figure.text(
        x,
        y + frame_height + 0.058,
        title,
        color=COLORS["steel"],
        fontfamily=MONO_FONT,
        fontsize=7.5,
    )
    frame_labels = (
        ["t−1", "t"]
        if len(chosen) == 2
        else ["t−2", "t−1", "t"]
    )
    for index, (path, label) in enumerate(zip(chosen, frame_labels)):
        add_image(
            figure,
            path,
            (
                x + index * x_step,
                y + (len(chosen) - index - 1) * y_step,
                frame_width,
                frame_height,
            ),
            label=label,
            border=border if index == len(chosen) - 1 else COLORS["grid"],
            zorder=index + 1,
        )


def save_figure(figure: plt.Figure, filename: str) -> Path:
    """Save and losslessly optimize one PNG."""
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_ROOT / filename
    figure.savefig(
        output_path,
        dpi=150,
        facecolor=figure.get_facecolor(),
        edgecolor="none",
        bbox_inches=None,
    )
    plt.close(figure)
    with Image.open(output_path) as image:
        image.convert("RGB").save(output_path, optimize=True, compress_level=9)
    return output_path


def generate_prompt_anatomy(samples: list[dict]) -> Path:
    """Explain the benchmark's three prompts and their scored labels."""
    sample = sample_by_id(samples, PROMPT_SAMPLE_ID)
    run = load_json(RUN_ROOT / "Qwen3.6-35B-A3B-FP8.json")
    prediction = sample_by_id(run, PROMPT_SAMPLE_ID)["prediction"]

    figure = new_figure(
        "01 · benchmark anatomy",
        "Three questions. Two views. One scored label set.",
        "The official task asks about “crossing the road” inside a benchmark named Vehicle_Cutin.",
    )
    add_image_stack(
        figure,
        sequence_paths(sample, "image_path"),
        x=0.075,
        y=0.455,
        width=0.37,
        title="q1 · raw sequence",
        border=COLORS["cream"],
    )
    add_image_stack(
        figure,
        sequence_paths(sample, "image_path_plot"),
        x=0.555,
        y=0.455,
        width=0.37,
        title="q2 + q3 · same sequence, target boxed",
        border=COLORS["signal"],
    )

    add_divider(figure, 0.415)
    columns = {
        "question": 0.075,
        "model": 0.705,
        "gold": 0.865,
    }
    for heading, x in (
        ("Question sent to model", columns["question"]),
        ("Qwen official", columns["model"]),
        ("Gold label", columns["gold"]),
    ):
        figure.text(
            x,
            0.39,
            heading,
            color=COLORS["mineral"],
            fontfamily=MONO_FONT,
            fontsize=6.8,
            va="top",
        )

    rows = [
        (
            "q1 · raw",
            "Does the Sedan intend to “cross the road”?",
            clean_answer(prediction[0]),
            sample["reference"][0],
        ),
        (
            "q2 · boxed",
            "Does the Sedan in the red box intend to “cross the road”?",
            clean_answer(prediction[1]),
            sample["reference"][1],
        ),
        (
            "q3 · boxed",
            "Choose the most appropriate reason from six labels.",
            clean_answer(prediction[2]),
            sample["reference"][2],
        ),
    ]
    y_positions = (0.345, 0.245, 0.145)
    for index, ((label, question, model, gold), y) in enumerate(
        zip(rows, y_positions)
    ):
        figure.text(
            columns["question"],
            y,
            label,
            color=COLORS["signal"],
            fontfamily=MONO_FONT,
            fontsize=7,
            va="top",
        )
        figure.text(
            columns["question"] + 0.105,
            y,
            fill(question, width=47),
            color=COLORS["paper"],
            fontfamily=MONO_FONT,
            fontsize=9.2,
            linespacing=1.4,
            va="top",
        )
        figure.text(
            columns["model"],
            y,
            model,
            color=COLORS["failure"],
            fontfamily=MONO_FONT,
            fontsize=9.2,
            fontweight="bold",
            va="top",
        )
        figure.text(
            columns["gold"],
            y,
            gold,
            color=COLORS["cream"],
            fontfamily=MONO_FONT,
            fontsize=9.2,
            fontweight="bold",
            va="top",
        )
        if index < len(rows) - 1:
            add_divider(figure, y - 0.065)

    add_footer(
        figure,
        "Source · VLADBench Vehicle_Cutin · sample 3_1_1_0 · Qwen 3.6 35B-A3B FP8",
    )
    return save_figure(figure, "01-benchmark-prompt-anatomy.png")


def generate_latency_plot() -> Path:
    """Regenerate the all-runs latency chart into the article asset folder."""
    results = [
        parse_run(path)
        for path in list_run_paths(RUN_ROOT, "official")
    ]
    output_path = OUTPUT_ROOT / "03-latency-vs-score.png"
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    generated = generate_request_latency_plot(
        results,
        output_path,
        reasoning=None,
        kicker="03 · performance sweep",
    )
    if not generated:
        raise RuntimeError("No timed benchmark runs were available")
    with Image.open(output_path) as image:
        image.convert("RGB").save(output_path, optimize=True, compress_level=9)
    return output_path


def short_cost_model_name(model: str) -> str:
    """Return a compact display name for a billed model."""
    names = {
        "Qwen/Qwen3.8-27B": "Qwen 3.8 27B",
        "Qwen/Qwen3.6-35B-A3B": "Qwen 3.6 35B-A3B",
        "moonshotai/Kimi-K3": "Kimi K3",
        "google/gemma-4-E2B-it": "Gemma 4 E2B-IT",
        "google/gemma-4-26B-A4B-it": "Gemma 4 26B-A4B-IT · DNF",
        "google/gemma-4-31B-it": "Gemma 4 31B-IT",
        "Qwen/Qwen3.5-0.8B": "Qwen 3.5 0.8B · partial",
        "google/gemma-4-E4B-it": "Gemma 4 E4B-IT",
        "Qwen/Qwen3.5-35B-A3B-FP8": "Qwen 3.5 35B-A3B-FP8",
        "Qwen/Qwen3.6-35B-A3B-FP8": "Qwen 3.6 35B-A3B-FP8",
        "openai/gpt-6-astra": "GPT-6 Astra",
        "google/gemini-3.8-flash": "Gemini 3.8 Flash",
        "openai/gpt-5.6-luna": "GPT-5.6 Luna",
    }
    return names.get(model, model.rsplit("/", maxsplit=1)[-1])


def generate_observed_spend() -> Path:
    """Visualize recorded account spend without implying normalized costs."""
    costs = json.loads(COST_PATH.read_text(encoding="utf-8"))
    entries = sorted(
        costs["models"],
        key=lambda entry: entry["total_usd"],
        reverse=True,
    )
    figure = new_figure(
        "02 · observed spend",
        "Where the sweep spend accumulated.",
        "Observed Modal and OpenRouter billing—not normalized per request or configuration.",
    )
    axes = figure.add_axes((0.285, 0.12, 0.66, 0.68))
    axes.set_facecolor(COLORS["midnight"])
    y_positions = list(reversed(range(len(entries))))
    values = [entry["total_usd"] for entry in entries]
    labels = [
        short_cost_model_name(entry["model"])
        for entry in entries
    ]
    colors = [
        (
            COLORS["signal"]
            if entry["provider"] == "OpenRouter"
            or "managed endpoint" in entry["provider"]
            else COLORS["cream"]
        )
        for entry in entries
    ]
    axes.barh(
        y_positions,
        values,
        color=colors,
        height=0.54,
    )
    for y, entry in zip(y_positions, entries):
        amount = entry["total_usd"]
        amount_label = f"${amount:.4f}" if amount < 0.1 else f"${amount:.2f}"
        provider = entry["provider"]
        hardware = entry["hardware"]
        infrastructure = provider if hardware is None else f"{provider} · {hardware}"
        axes.text(
            amount + 0.18,
            y + 0.08,
            amount_label,
            color=(
                COLORS["signal"]
                if provider == "OpenRouter"
                or "managed endpoint" in provider
                else COLORS["paper"]
            ),
            fontfamily=MONO_FONT,
            fontsize=7.5,
            fontweight="bold",
            va="center",
        )
        axes.text(
            amount + 0.18,
            y - 0.16,
            infrastructure,
            color=COLORS["mineral"],
            fontfamily=MONO_FONT,
            fontsize=5.8,
            va="center",
        )
    axes.set_yticks(y_positions, labels)
    axes.set_xlim(0, max(values) * 1.26)
    axes.set_xlabel(
        "recorded spend  (USD)",
        color=COLORS["steel"],
        fontfamily=MONO_FONT,
        fontsize=8,
        labelpad=10,
    )
    axes.grid(axis="x", color=COLORS["grid"], linewidth=0.7)
    axes.set_axisbelow(True)
    axes.tick_params(colors=COLORS["steel"], labelsize=7.2)
    for label in (*axes.get_xticklabels(), *axes.get_yticklabels()):
        label.set_fontfamily(MONO_FONT)
    for spine in axes.spines.values():
        spine.set_visible(False)
    axes.legend(
        handles=[
            Rectangle(
                (0, 0),
                1,
                1,
                facecolor=COLORS["cream"],
                label="Modal GPU endpoint",
            ),
            Rectangle(
                (0, 0),
                1,
                1,
                facecolor=COLORS["signal"],
                label="metered API / managed tokens",
            ),
        ],
        loc="lower right",
        bbox_to_anchor=(1, 1.01),
        frameon=False,
        prop={"family": MONO_FONT, "size": 7},
        labelcolor=COLORS["paper"],
        ncol=2,
    )
    add_footer(
        figure,
        (
            "Source · recorded endpoint and account charges"
            f" · captured total ${costs['known_total_usd']:.2f}"
            " · startup and idle time may be included"
        ),
    )
    return save_figure(figure, "02-observed-sweep-spend.png")


def judgment_accuracy(path: Path) -> float:
    """Return the judgment component as percentage points."""
    result = parse_run(path)
    if result["judge"] is None:
        raise ValueError(f"Run is incomplete: {path}")
    return 100 * result["judge"]


def generate_prompt_rewrite_comparison() -> Path:
    """Show official-versus-reworded judgment accuracy for rerun models."""
    runs = [
        (
            "Qwen 3.6 FP8",
            "Qwen3.6-35B-A3B-FP8.json",
            "Qwen3.6-35B-A3B-FP8-reword.json",
        ),
        (
            "Qwen 3.6",
            "Qwen3.6-35B-A3B.json",
            "Qwen3.6-35B-A3B-reword.json",
        ),
        (
            "GPT-6 Astra · low",
            "GPT-6-Astra-low-reasoning.json",
            "GPT-6-Astra-low-reasoning-reword.json",
        ),
        (
            "Gemini 3.8 · reasoning",
            "Gemini-3.8-Flash-reasoning.json",
            "Gemini-3.8-Flash-reasoning-reword.json",
        ),
    ]
    values = [
        (
            label,
            judgment_accuracy(RUN_ROOT / official),
            judgment_accuracy(RUN_ROOT / reworded),
        )
        for label, official, reworded in runs
    ]
    figure = new_figure(
        "04 · prompt sensitivity",
        "Four words moved Qwen by forty points.",
        "Only the wording changed. Frames, gold labels, and scoring stayed fixed.",
    )
    axes = figure.add_axes((0.27, 0.17, 0.67, 0.57))
    axes.set_facecolor(COLORS["midnight"])
    y_positions = list(reversed(range(len(values))))

    for y, (label, official, reworded) in zip(y_positions, values):
        axes.hlines(
            y,
            official,
            reworded,
            color=COLORS["grid"],
            linewidth=2.0,
            zorder=1,
        )
        axes.scatter(
            official,
            y,
            s=70,
            color=COLORS["cream"],
            edgecolor=COLORS["midnight"],
            linewidth=0.7,
            zorder=3,
        )
        axes.scatter(
            reworded,
            y,
            s=70,
            marker="s",
            color=COLORS["signal"],
            edgecolor=COLORS["midnight"],
            linewidth=0.7,
            zorder=3,
        )
        axes.text(
            official - 1.2,
            y,
            f"{official:.1f}",
            color=COLORS["steel"],
            fontfamily=MONO_FONT,
            fontsize=8,
            ha="right",
            va="center",
        )
        axes.text(
            reworded + 1.2,
            y,
            f"{reworded:.1f}  (+{reworded - official:.1f})",
            color=COLORS["signal"],
            fontfamily=MONO_FONT,
            fontsize=8,
            ha="left",
            va="center",
        )

    axes.set_yticks(y_positions, [value[0] for value in values])
    axes.set_xlim(0, 82)
    axes.set_ylim(-0.6, len(values) - 0.4)
    axes.set_xlabel(
        "judgment accuracy  (%)",
        color=COLORS["steel"],
        fontfamily=MONO_FONT,
        fontsize=8,
        labelpad=12,
    )
    axes.grid(axis="x", color=COLORS["grid"], linewidth=0.7)
    axes.tick_params(colors=COLORS["steel"], labelsize=8)
    for label in (*axes.get_xticklabels(), *axes.get_yticklabels()):
        label.set_fontfamily(MONO_FONT)
    for spine in axes.spines.values():
        spine.set_visible(False)
    axes.legend(
        handles=[
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor=COLORS["cream"],
                markersize=7,
                label="official · “cross the road”",
            ),
            Line2D(
                [0],
                [0],
                marker="s",
                color="none",
                markerfacecolor=COLORS["signal"],
                markersize=7,
                label="reworded · “cut in”",
            ),
        ],
        loc="lower right",
        bbox_to_anchor=(1, 1.04),
        frameon=False,
        prop={"family": MONO_FONT, "size": 7},
        labelcolor=COLORS["paper"],
        ncol=2,
    )
    add_footer(
        figure,
        "Source · completed official and cut-in-reword runs · 174 judgment prompts per model",
    )
    return save_figure(figure, "04-prompt-rewrite-comparison.png")


def generate_label_imbalance(samples: list[dict]) -> Path:
    """Visualize the single negative clip in the benchmark."""
    negative = sample_by_id(samples, NEGATIVE_SAMPLE_ID)
    positive_count = sum(
        sample["reference"][:2] == ["yes", "yes"]
        for sample in samples
    )
    negative_count = len(samples) - positive_count

    figure = new_figure(
        "05 · label distribution",
        "This is a yes-set, not a fleet distribution.",
        "A detector that always says yes scores 98.9% on the judgment prompts.",
    )
    figure.text(
        0.075,
        0.67,
        str(positive_count),
        color=COLORS["paper"],
        fontfamily=DISPLAY_FONT,
        fontsize=76,
        fontweight="bold",
        va="center",
    )
    figure.text(
        0.195,
        0.675,
        f"/ {len(samples)} clips",
        color=COLORS["steel"],
        fontfamily=MONO_FONT,
        fontsize=11,
        va="center",
    )
    figure.text(
        0.08,
        0.565,
        "gold-yes",
        color=COLORS["signal"],
        fontfamily=MONO_FONT,
        fontsize=9,
    )

    columns = 11
    size = 0.018
    gap = 0.007
    for index in range(len(samples)):
        row, column = divmod(index, columns)
        color = (
            COLORS["signal"]
            if index == len(samples) - 1
            else COLORS["cream"]
        )
        figure.add_artist(
            Rectangle(
                (
                    0.08 + column * (size + gap),
                    0.48 - row * (size + gap),
                ),
                size,
                size,
                transform=figure.transFigure,
                facecolor=color,
                edgecolor="none",
            )
        )
    figure.text(
        0.08,
        0.245,
        f"{positive_count * 2} yes labels  ·  {negative_count * 2} no labels",
        color=COLORS["steel"],
        fontfamily=MONO_FONT,
        fontsize=8,
    )
    figure.text(
        0.08,
        0.19,
        "One negative clip, asked twice.",
        color=COLORS["paper"],
        fontfamily=DISPLAY_FONT,
        fontsize=14,
        fontweight="bold",
    )

    raw_path = sequence_paths(negative, "image_path")[-1]
    boxed_path = sequence_paths(negative, "image_path_plot")[-1]
    add_image(
        figure,
        raw_path,
        (0.47, 0.36, 0.42, 0.378),
        label="The only gold-no clip · raw",
        border=COLORS["cream"],
        zorder=1,
    )
    add_image(
        figure,
        boxed_path,
        (0.56, 0.16, 0.36, 0.324),
        label="The same clip · target boxed",
        border=COLORS["signal"],
        zorder=2,
    )
    add_footer(
        figure,
        "Source · VLADBench Vehicle_Cutin · 87 clips / 174 yes-no judgments",
    )
    return save_figure(figure, "05-label-imbalance.png")


def reason_distribution(samples: list[dict]) -> list[tuple[str, int]]:
    """Return reason-label counts on the scored 86-question set."""
    return Counter(
        sample["reference"][2]
        for sample in samples
        if sample["id"] != EXCLUDED_REASON_SAMPLE_ID
    ).most_common()


def generate_reason_taxonomy(samples: list[dict]) -> Path:
    """Show the concentration and fragmentation of reason labels."""
    counts = dict(reason_distribution(samples))
    featured = [
        "commuting efficiency",
        "intersection turning",
        "merge onto main road",
        "start entering main road",
        "borrow lane driving",
        "yield to left-side vehicles",
        "lane change",
        "yield to right-side vehicles",
        "start merging into main road",
    ]
    other_count = sum(
        count for label, count in counts.items() if label not in featured
    )
    values = [(label, counts[label]) for label in featured]
    values.append(("8 other labels", other_count))

    figure = new_figure(
        "07 · reason labels",
        "The dominant “reason” is not visible in the pixels.",
        "The benchmark mixes motive, geometry, and maneuver labels in one answer list.",
    )
    axes = figure.add_axes((0.30, 0.12, 0.64, 0.66))
    axes.set_facecolor(COLORS["midnight"])
    labels = [label for label, _ in values]
    quantities = [count for _, count in values]
    y_positions = list(reversed(range(len(values))))
    bar_colors = [
        (
            COLORS["signal"]
            if label == "commuting efficiency"
            else COLORS["cream"]
            if label == "lane change"
            else COLORS["mineral"]
        )
        for label in labels
    ]
    axes.barh(
        y_positions,
        quantities,
        color=bar_colors,
        height=0.52,
    )
    for y, label, quantity in zip(y_positions, labels, quantities):
        axes.text(
            quantity + 0.7,
            y,
            f"{quantity}  ·  {100 * quantity / 86:.0f}%",
            color=(
                COLORS["signal"]
                if label == "commuting efficiency"
                else COLORS["paper"]
            ),
            fontfamily=MONO_FONT,
            fontsize=8,
            va="center",
        )
    axes.set_yticks(y_positions, labels)
    axes.set_xlim(0, 50)
    axes.set_xlabel(
        "gold answers  (n = 86)",
        color=COLORS["steel"],
        fontfamily=MONO_FONT,
        fontsize=8,
        labelpad=12,
    )
    axes.grid(axis="x", color=COLORS["grid"], linewidth=0.7)
    axes.set_axisbelow(True)
    axes.tick_params(colors=COLORS["steel"], labelsize=7.5)
    for label in (*axes.get_xticklabels(), *axes.get_yticklabels()):
        label.set_fontfamily(MONO_FONT)
    for spine in axes.spines.values():
        spine.set_visible(False)
    add_footer(
        figure,
        "Source · VLADBench Vehicle_Cutin gold reason labels · malformed q3 excluded",
    )
    return save_figure(figure, "07-reason-label-distribution.png")


def generate_box_flip(samples: list[dict]) -> Path:
    """Show one real answer that changes when a target box is added."""
    sample = sample_by_id(samples, BOX_FLIP_SAMPLE_ID)
    run = load_json(RUN_ROOT / "Qwen3.6-35B-A3B-FP8.json")
    prediction = sample_by_id(run, BOX_FLIP_SAMPLE_ID)["prediction"]

    all_flips = sum(
        yes_or_no(item["prediction"][0])
        != yes_or_no(item["prediction"][1])
        for item in run
    )
    figure = new_figure(
        "06 · attribution sensitivity",
        "Draw a box. Get a different answer.",
        "Same frames. Same words. Only the red target rectangle changed.",
        figsize=(12, 6.75),
    )
    add_image_stack(
        figure,
        sequence_paths(sample, "image_path"),
        x=0.075,
        y=0.39,
        width=0.37,
        title="without target box",
        border=COLORS["cream"],
    )
    add_image_stack(
        figure,
        sequence_paths(sample, "image_path_plot"),
        x=0.555,
        y=0.39,
        width=0.37,
        title="with target box",
        border=COLORS["signal"],
    )
    figure.text(
        0.20,
        0.17,
        clean_answer(prediction[0]),
        color=COLORS["failure"],
        fontfamily=DISPLAY_FONT,
        fontsize=32,
        fontweight="bold",
        ha="center",
    )
    figure.text(
        0.50,
        0.18,
        "→",
        color=COLORS["signal"],
        fontfamily=MONO_FONT,
        fontsize=24,
        ha="center",
    )
    figure.text(
        0.70,
        0.17,
        clean_answer(prediction[1]),
        color=COLORS["signal"],
        fontfamily=DISPLAY_FONT,
        fontsize=32,
        fontweight="bold",
        ha="center",
    )
    figure.text(
        0.92,
        0.18,
        f"{all_flips} / 87",
        color=COLORS["paper"],
        fontfamily=DISPLAY_FONT,
        fontsize=18,
        fontweight="bold",
        ha="right",
    )
    figure.text(
        0.92,
        0.135,
        "Qwen answers flipped",
        color=COLORS["steel"],
        fontfamily=MONO_FONT,
        fontsize=7,
        ha="right",
    )
    add_footer(
        figure,
        "Source · official prompt · Qwen 3.6 35B-A3B FP8 · sample 3_1_1_54",
    )
    return save_figure(figure, "06-bounding-box-answer-flip.png")


def main() -> None:
    samples = load_json(DATA_PATH)
    outputs = [
        generate_prompt_anatomy(samples),
        generate_observed_spend(),
        generate_latency_plot(),
        generate_prompt_rewrite_comparison(),
        generate_label_imbalance(samples),
        generate_box_flip(samples),
        generate_reason_taxonomy(samples),
    ]
    for output in outputs:
        print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
