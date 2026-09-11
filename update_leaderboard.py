#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["matplotlib>=3.7", "numpy>=1.24"]
# ///
"""Build the Vehicle_Cutin benchmark leaderboard from prediction files."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FixedFormatter, FixedLocator, NullFormatter

from evaluate_utils import Judge_criterion_QA

# eventual.ai tokens: midnight field, magenta signal, steel type, mono UI.
EVENTUAL = {
    "midnight": "#000000",
    "panel": "#050505",
    "paper": "#ffffff",
    "steel": "#b0b0b0",
    "mineral": "#8a8a8a",
    "signal": "#ff00ff",
    "cream": "#f5f4ef",
    "amber": "#c98016",
    "hairline": (1.0, 1.0, 1.0, 0.16),
    "grid": "#1a1a1a",
    "grid_minor": "#111111",
}
REASONING_STYLES = {
    "Disabled": {
        "color": EVENTUAL["cream"],
        "marker": "o",
        "label": "reasoning off",
    },
    "Enabled": {
        "color": EVENTUAL["signal"],
        "marker": "s",
        "label": "reasoning on",
    },
    "Low": {
        "color": EVENTUAL["amber"],
        "marker": "^",
        "label": "reasoning low",
    },
}


def _eventual_font(prefer: tuple[str, ...], fallback: str) -> str:
    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in prefer:
        if name in available:
            return name
    return fallback


DISPLAY_FONT = _eventual_font(
    ("Arial", "Helvetica Neue", "Helvetica"),
    "DejaVu Sans",
)
MONO_FONT = _eventual_font(
    ("Menlo", "SF Mono", "Consolas", "Andale Mono"),
    "DejaVu Sans Mono",
)

TASK = "Vehicle_Cutin"
WEIGHTS = [0.7, 0.1, 0.2]
PROMPT_OFFICIAL = "official"
PROMPT_REWORD = "cutin-reword"
SOURCE_QUESTIONS = 261
EXCLUDED_QUESTIONS = {("3_1_1_86", 2)}
EXPECTED_QUESTIONS = SOURCE_QUESTIONS - len(EXCLUDED_QUESTIONS)
KNOWN_WALL_SECONDS = {
    "Qwen3.8-27B": 166.8,
    "Qwen3.8-27B-reasoning": 1350.6,
}
STATUS_OVERRIDES = {
    "Gemma-4-26B-A4B-it-reasoning": "DNF",
    "GLM-5.3-Flash-reasoning": "DNF",
    "Qwen3.5-35B-A3B-FP8-reasoning": "Blocked",
}
MODEL_NAMES = {
    "GLM-5.3-Flash": "zai-org/GLM-5.3-Flash",
    "Gemini-3.8-Flash": "google/gemini-3.8-flash",
    "Gemma-4-26B-A4B-it": "google/gemma-4-26B-A4B-it",
    "Gemma-4-31B-it": "google/gemma-4-31B-it",
    "Gemma-4-E2B-it": "google/gemma-4-E2B-it",
    "Gemma-4-E4B-it": "google/gemma-4-E4B-it",
    "GPT-5.6-Luna": "openai/gpt-5.6-luna",
    "GPT-6-Astra": "openai/gpt-6-astra",
    "Kimi-K3": "moonshotai/Kimi-K3",
    "Qwen3.5-0.8B": "Qwen/Qwen3.5-0.8B",
    "Qwen3.5-35B-A3B-FP8": "Qwen/Qwen3.5-35B-A3B-FP8",
    "Qwen3.6-35B-A3B": "Qwen/Qwen3.6-35B-A3B",
    "Qwen3.6-35B-A3B-FP8": "Qwen/Qwen3.6-35B-A3B-FP8",
    "Qwen3.6-35B-A3B-FP8-Finetune": "with-feedback-fp8 (fine-tuned)",
    "Qwen3.8-27B": "Qwen/Qwen3.8-27B",
}


def load_json_with_retries(path: Path, retries: int = 5) -> list[dict]:
    """Read an output that another process may currently be replacing."""
    for attempt in range(retries):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            if attempt == retries - 1:
                raise
            time.sleep(0.05)
    raise RuntimeError("unreachable")


def is_scored_question(sample: dict, question_index: int) -> bool:
    return (sample["id"], question_index) not in EXCLUDED_QUESTIONS


def build_scoring_samples(samples: list[dict]) -> list[dict]:
    scoring_samples = []
    for sample in samples:
        filtered_sample = sample.copy()
        for field in ("questions", "reference", "prediction"):
            filtered_sample[field] = [
                value
                for question_index, value in enumerate(sample[field])
                if is_scored_question(sample, question_index)
            ]
        scoring_samples.append(filtered_sample)
    return scoring_samples


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    minutes, remaining = divmod(seconds, 60)
    if minutes:
        return f"{int(minutes)}m {remaining:.1f}s"
    return f"{remaining:.1f}s"


def parse_run(path: Path) -> dict:
    samples = load_json_with_retries(path)
    predictions = [
        prediction
        for sample in samples
        for question_index, prediction in enumerate(
            sample.get("prediction", [])
        )
        if is_scored_question(sample, question_index)
    ]
    completed = sum(bool(prediction.strip()) for prediction in predictions)
    metadata = [
        item
        for sample in samples
        for question_index, item in enumerate(
            sample.get("completion_metadata", [])
        )
        if is_scored_question(sample, question_index)
        if item is not None
    ]

    stem = path.stem
    prompt_variant = PROMPT_OFFICIAL
    if stem.endswith("-reword"):
        prompt_variant = PROMPT_REWORD
        stem = stem.removesuffix("-reword")
    if samples and samples[0].get("prompt_variant"):
        prompt_variant = samples[0]["prompt_variant"]
    reasoning = stem.endswith("-reasoning")
    model_key = stem.removesuffix("-reasoning")
    reasoning_label = "Enabled" if reasoning else "Disabled"
    if reasoning and model_key.endswith("-low"):
        model_key = model_key.removesuffix("-low")
        reasoning_label = "Low"
    result = {
        "path": path,
        "model": MODEL_NAMES.get(model_key, model_key),
        "reasoning": reasoning_label,
        "prompt_variant": prompt_variant,
        "status": STATUS_OVERRIDES.get(path.stem, "Running"),
        "completed": completed,
        "score": None,
        "judge": None,
        "reason": None,
        "obey": None,
        "wall_seconds": KNOWN_WALL_SECONDS.get(stem),
        "median_seconds": None,
        "latency_p25_seconds": None,
        "latency_p75_seconds": None,
        "reasoning_tokens": None,
    }

    if metadata:
        started = min(datetime.fromisoformat(item["started_at"]) for item in metadata)
        finished = max(
            datetime.fromisoformat(item["completed_at"]) for item in metadata
        )
        if completed == EXPECTED_QUESTIONS:
            result["wall_seconds"] = (finished - started).total_seconds()
        latencies = [
            item["api_elapsed_seconds"]
            for item in metadata
        ]
        result["median_seconds"] = statistics.median(latencies)
        latency_quartiles = (
            statistics.quantiles(latencies, n=4, method="inclusive")
            if len(latencies) > 1 else [latencies[0]] * 3
        )
        result["latency_p25_seconds"] = latency_quartiles[0]
        result["latency_p75_seconds"] = latency_quartiles[2]
        reasoning_tokens = [
            item["reasoning_tokens"]
            for item in metadata
            if item.get("reasoning_tokens") is not None
        ]
        if reasoning_tokens:
            result["reasoning_tokens"] = sum(reasoning_tokens)

    if completed == EXPECTED_QUESTIONS:
        scoring_samples = build_scoring_samples(samples)
        total, description_acc, obey, judge_acc = Judge_criterion_QA(
            scoring_samples, result["model"]
        )
        if total != EXPECTED_QUESTIONS:
            raise ValueError(f"Unexpected question count in {path}: {total}")
        result["judge"] = judge_acc
        result["reason"] = description_acc
        result["obey"] = obey
        result["score"] = 100 * (
            judge_acc * WEIGHTS[0]
            + description_acc * WEIGHTS[1]
            + obey * WEIGHTS[2]
        )

    return result


def format_percent(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.1f}%"


def format_score(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def format_integer(value: int | None) -> str:
    return "—" if value is None else f"{value:,}"


PLOT_LABELS = {
    "Qwen3.6-35B-A3B-FP8": "Qwen 3.6 FP8",
    "Qwen3.6-35B-A3B": "Qwen 3.6",
    "Qwen3.5-35B-A3B-FP8": "Qwen 3.5 FP8",
    "gpt-6-astra": "GPT-6 Astra",
    "gpt-5.6-luna": "GPT-5.6 Luna",
    "gemini-3.8-flash": "Gemini 3.8",
    "gemma-4-31B-it": "Gemma 31B",
    "gemma-4-E2B-it": "Gemma E2B",
    "gemma-4-E4B-it": "Gemma E4B",
    "gemma-4-26B-A4B-it": "Gemma 26B",
    "Kimi-K3": "Kimi K3",
}


def short_model_name(model: str) -> str:
    return model.rsplit("/", maxsplit=1)[-1]


def is_feedback_run(result: dict) -> bool:
    name = result["model"].lower()
    return "with-feedback" in name or "fine-tuned" in name or "finetune" in name


def plot_label(result: dict) -> str:
    return PLOT_LABELS.get(short_model_name(result["model"]), short_model_name(result["model"]))


def _boxes_overlap(first: tuple[float, float, float, float], second: tuple[float, float, float, float], pad: float) -> bool:
    return not (
        first[2] + pad < second[0]
        or first[0] - pad > second[2]
        or first[3] + pad < second[1]
        or first[1] - pad > second[3]
    )


def _label_box(px: float, py: float, width: float, height: float, dx: float, dy: float, ha: str, va: str) -> tuple[float, float, float, float]:
    if ha == "left":
        x0 = px + dx
    elif ha == "right":
        x0 = px + dx - width
    else:
        x0 = px + dx - width / 2
    if va == "bottom":
        y0 = py + dy
    elif va == "top":
        y0 = py + dy - height
    else:
        y0 = py + dy - height / 2
    return (x0, y0, x0 + width, y0 + height)


def place_scatter_labels(axes, plotted: list[dict], legend) -> None:
    figure = axes.figure
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    scale = figure.dpi / 72
    axes_box = axes.get_window_extent(renderer)
    occupied: list[tuple[float, float, float, float]] = []
    sizes: dict[str, tuple[float, float]] = {}

    for result in plotted:
        px, py = axes.transData.transform((result["median_seconds"], result["score"]))
        occupied.append((px - 9, py - 9, px + 9, py + 9))
    if legend is not None:
        box = legend.get_window_extent(renderer).padded(6)
        occupied.append((box.x0, box.y0, box.x1, box.y1))

    def measure(text: str) -> tuple[float, float]:
        if text not in sizes:
            artist = axes.text(0, 0, text, fontsize=7.2, fontname=MONO_FONT)
            figure.canvas.draw()
            box = artist.get_window_extent(renderer)
            artist.remove()
            sizes[text] = (box.width, box.height)
        return sizes[text]

    points = [
        (*axes.transData.transform((result["median_seconds"], result["score"])), result)
        for result in plotted
    ]

    def crowding(item: tuple[float, float, dict]) -> int:
        px, py, _ = item
        return sum(
            ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5 < 55
            for qx, qy, _ in points
        )

    candidates = []
    for radius in (12, 18, 26, 36, 48):
        for dx_dir, dy_dir, ha, va in (
            (1, 0.35, "left", "bottom"),
            (1, -0.45, "left", "top"),
            (0.2, 1, "left", "bottom"),
            (0.2, -1, "left", "top"),
            (-1, 0.35, "right", "bottom"),
            (-1, -0.45, "right", "top"),
            (1, 1, "left", "bottom"),
            (1, -1, "left", "top"),
            (-1, 1, "right", "bottom"),
            (-1, -1, "right", "top"),
            (0, 1.15, "center", "bottom"),
            (0, -1.25, "center", "top"),
        ):
            candidates.append((radius * dx_dir, radius * dy_dir, ha, va, radius))

    for px, py, result in sorted(points, key=crowding, reverse=True):
        text = plot_label(result)
        width, height = measure(text)
        chosen = None
        best_hits = None
        for dx_pt, dy_pt, ha, va, radius in candidates:
            box = _label_box(px, py, width, height, dx_pt * scale, dy_pt * scale, ha, va)
            if (
                box[0] < axes_box.x0 + 2
                or box[2] > axes_box.x1 - 2
                or box[1] < axes_box.y0 + 2
                or box[3] > axes_box.y1 - 2
            ):
                continue
            hits = sum(_boxes_overlap(box, other, pad=3) for other in occupied)
            if hits == 0:
                chosen = (dx_pt, dy_pt, ha, va, radius, box)
                break
            if best_hits is None or hits < best_hits[0]:
                best_hits = (hits, dx_pt, dy_pt, ha, va, radius, box)
        if chosen is None and best_hits is not None:
            _, dx_pt, dy_pt, ha, va, radius, box = best_hits
            chosen = (dx_pt, dy_pt, ha, va, radius, box)
        if chosen is None:
            continue
        dx_pt, dy_pt, ha, va, radius, box = chosen
        occupied.append(box)
        arrow = None
        if radius >= 22:
            arrow = {
                "arrowstyle": "-",
                "color": EVENTUAL["mineral"],
                "lw": 0.55,
                "shrinkA": 0,
                "shrinkB": 4,
            }
        axes.annotate(
            text,
            (result["median_seconds"], result["score"]),
            xytext=(dx_pt, dy_pt),
            textcoords="offset points",
            fontsize=7.2,
            fontname=MONO_FONT,
            color=EVENTUAL["paper"],
            ha=ha,
            va=va,
            arrowprops=arrow,
            zorder=4,
        )


def generate_request_latency_plot(
    results: list[dict],
    plot_path: Path,
    reasoning: str | None,
    *,
    kicker: str = "vehicle cut-in",
) -> bool:
    def is_in_scope(result: dict) -> bool:
        if reasoning is None:
            return True
        if reasoning == "Disabled":
            return result["reasoning"] == "Disabled"
        return result["reasoning"] != "Disabled"

    plotted = [
        result
        for result in results
        if result["score"] is not None
        and result["median_seconds"] is not None
        and is_in_scope(result)
        and not is_feedback_run(result)
    ]
    if not plotted:
        return False

    figure, axes = plt.subplots(figsize=(10.5, 6.1), facecolor=EVENTUAL["midnight"])
    axes.set_facecolor(EVENTUAL["panel"])
    reasoning_values = sorted({result["reasoning"] for result in plotted})

    for reasoning_value in reasoning_values:
        group = [
            result
            for result in plotted
            if result["reasoning"] == reasoning_value
        ]
        if not group:
            continue
        style = REASONING_STYLES[reasoning_value]
        median_latencies = [result["median_seconds"] for result in group]
        axes.errorbar(
            median_latencies,
            [result["score"] for result in group],
            xerr=[
                [
                    median - result["latency_p25_seconds"]
                    for median, result in zip(median_latencies, group)
                ],
                [
                    result["latency_p75_seconds"] - median
                    for median, result in zip(median_latencies, group)
                ],
            ],
            color=style["color"],
            ecolor=style["color"],
            alpha=0.95,
            capsize=3,
            elinewidth=1.15,
            linestyle="none",
            marker=style["marker"],
            markersize=8.5,
            markeredgecolor=EVENTUAL["midnight"],
            markeredgewidth=0.6,
            label=style["label"],
            zorder=3,
        )

    minimum_seconds = min(result["latency_p25_seconds"] for result in plotted)
    maximum_seconds = max(result["latency_p75_seconds"] for result in plotted)
    axes.set_xscale("log")
    axes.set_xlim(minimum_seconds * 0.72, maximum_seconds * 1.45)
    scores = [result["score"] for result in plotted]
    score_span = max(scores) - min(scores) or 1
    axes.set_ylim(min(scores) - 0.12 * score_span, max(scores) + 0.14 * score_span)
    visible_ticks = [
        tick
        for tick in (0.5, 1, 2, 5, 10, 20)
        if axes.get_xlim()[0] <= tick <= axes.get_xlim()[1]
    ]
    axes.xaxis.set_major_locator(FixedLocator(visible_ticks))
    axes.xaxis.set_major_formatter(
        FixedFormatter([str(tick) for tick in visible_ticks])
    )
    axes.xaxis.set_minor_formatter(NullFormatter())
    axes.set_xlabel(
        "median request latency  (seconds, log)",
        fontname=MONO_FONT,
        fontsize=9,
        color=EVENTUAL["steel"],
        labelpad=10,
    )
    axes.set_ylabel(
        "VLADBench score",
        fontname=MONO_FONT,
        fontsize=9,
        color=EVENTUAL["steel"],
        labelpad=10,
    )
    scope = (
        "all completed runs"
        if reasoning is None
        else f"reasoning {reasoning.lower()}"
    )
    axes.text(
        0.0,
        1.14,
        f"{kicker}  ·  {scope}",
        transform=axes.transAxes,
        fontname=MONO_FONT,
        fontsize=9,
        color=EVENTUAL["signal"],
        ha="left",
        va="bottom",
    )
    axes.set_title(
        "Latency vs. score",
        fontname=DISPLAY_FONT,
        fontsize=22,
        fontweight="bold",
        color=EVENTUAL["paper"],
        loc="left",
        pad=18,
    )
    axes.grid(True, which="major", color=EVENTUAL["grid"], linewidth=0.7)
    axes.grid(True, which="minor", color=EVENTUAL["grid_minor"], linewidth=0.4)
    axes.tick_params(colors=EVENTUAL["steel"], which="both", labelsize=8.5)
    for label in (*axes.get_xticklabels(), *axes.get_yticklabels()):
        label.set_fontname(MONO_FONT)
        label.set_color(EVENTUAL["steel"])
    for spine in axes.spines.values():
        spine.set_color(EVENTUAL["hairline"])
    axes.spines["top"].set_visible(False)
    axes.spines["right"].set_visible(False)
    legend = None
    if reasoning is None or len(reasoning_values) > 1:
        legend = axes.legend(
            frameon=False,
            loc="upper right",
            prop={"family": MONO_FONT, "size": 8},
            labelcolor=EVENTUAL["paper"],
            handlelength=1.2,
            borderaxespad=0.4,
            labelspacing=0.6,
        )
        for text in legend.get_texts():
            text.set_color(EVENTUAL["paper"])
    figure.subplots_adjust(top=0.78, left=0.10, right=0.97, bottom=0.12)
    place_scatter_labels(axes, plotted, legend)
    figure.savefig(
        plot_path,
        dpi=180,
        facecolor=figure.get_facecolor(),
        edgecolor="none",
        bbox_inches="tight",
        pad_inches=0.28,
    )
    plt.close(figure)
    return True


def generate_plots(results: list[dict], plot_dir: Path) -> list[tuple[str, Path]]:
    plot_dir.mkdir(parents=True, exist_ok=True)
    plot_specs = [
        ("All completed runs", "median-request-latency-vs-score-all.png", None),
        (
            "Reasoning disabled",
            "median-request-latency-vs-score-reasoning-disabled.png",
            "Disabled",
        ),
        (
            "Reasoning enabled",
            "median-request-latency-vs-score-reasoning-enabled.png",
            "Enabled",
        ),
    ]
    generated = []
    for label, filename, reasoning in plot_specs:
        plot_path = plot_dir / filename
        if generate_request_latency_plot(results, plot_path, reasoning):
            generated.append((label, plot_path))
    return generated


def render_leaderboard(
    results: list[dict],
    output_dir: Path,
    plot_links: list[tuple[str, Path]],
    prompt_variant: str = PROMPT_OFFICIAL,
) -> str:
    completed = sorted(
        (result for result in results if result["score"] is not None),
        key=lambda result: result["score"],
        reverse=True,
    )
    running = sorted(
        (result for result in results if result["score"] is None),
        key=lambda result: result["model"],
    )

    if prompt_variant == PROMPT_REWORD:
        title = "# Vehicle_Cutin Leaderboard (cut-in reword)"
        wording = (
            "These are the results from the corrected Vehicle Cut-in sweep. "
            "The prompt asks whether the target vehicle intends to “cut in "
            "(enter or cross into the ego vehicle’s path).” Official-wording "
            "runs live in `LEADERBOARD.md`."
        )
    else:
        title = "# Vehicle_Cutin Leaderboard"
        wording = (
            "These are the results from the original Vehicle Cut-in sweep "
            "using the official VLAD wording: “intention to cross the road”. "
            "Reworded runs live in `LEADERBOARD-reword.md`."
        )

    plot_by_label = dict(plot_links)
    lines = [title, "", wording, ""]
    all_completed_plot = plot_by_label.pop("All completed runs", None)
    if all_completed_plot:
        lines.extend(
            [
                "### All completed runs",
                "",
                (
                    "![Vehicle_Cutin All completed runs median request latency "
                    f"versus score]({all_completed_plot.as_posix()})"
                ),
                "",
            ]
        )
    lines.extend(
        [
            "> **Note:**",
            ">",
            f"> - Generated from `{output_dir}`.",
            (
                "> - Official scoring weights: judgment 70%, reason 10%, "
                "instruction following 20%."
            ),
            (
                f"> - Scores are based on a shared {EXPECTED_QUESTIONS}-question "
                "set; `JAAD_video__0246 q3` is excluded from every run."
            ),
            (
                "> - Use the [scoring explorer](scoring-explorer.html) to "
                "adjust the weights."
            ),
            "",
            "",
            "| Rank | Model | Reasoning | Status | Score | Judgment | Reason | Obey | Wall time | Median request | Reasoning tokens |",
            "| ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for rank, result in enumerate(completed, start=1):
        lines.append(
            f"| {rank} | {result['model']} | {result['reasoning']} | "
            f"{result['completed']}/{EXPECTED_QUESTIONS} | "
            f"{format_score(result['score'])} | "
            f"{format_percent(result['judge'])} | "
            f"{format_percent(result['reason'])} | "
            f"{format_percent(result['obey'])} | "
            f"{format_duration(result['wall_seconds'])} | "
            f"{format_duration(result['median_seconds'])} | "
            f"{format_integer(result['reasoning_tokens'])} |"
        )
    for result in running:
        status = (
            f"{result['status']} "
            f"({result['completed']}/{EXPECTED_QUESTIONS})"
        )
        lines.append(
            f"| — | {result['model']} | {result['reasoning']} | "
            f"{status} | — | — | — | — | — | "
            f"{format_duration(result['median_seconds'])} | "
            f"{format_integer(result['reasoning_tokens'])} |"
        )
    if plot_by_label:
        lines.extend(
            [
                "",
                "",
                "## Median Request Latency vs. Score",
                "",
                (
                    "Completed runs with per-request timing metadata only; "
                    "horizontal bars show the p25–p75 request-latency range and "
                    "the x-axis is logarithmic. Qwen 3.8 runs are omitted because "
                    "their legacy outputs lack request timing metadata."
                ),
                "",
            ]
        )
        for label, plot_path in plot_by_label.items():
            lines.extend(
                [
                    f"### {label}",
                    "",
                    (
                        f"![Vehicle_Cutin {label} median request latency versus score]"
                        f"({plot_path.as_posix()})"
                    ),
                    "",
                ]
            )
    return "\n".join(lines)


def list_run_paths(output_dir: Path, prompt_variant: str) -> list[Path]:
    paths = []
    for path in sorted(output_dir.glob("*.json")):
        if "smoke" in path.stem:
            continue
        is_reword = path.stem.endswith("-reword")
        if prompt_variant == PROMPT_REWORD and is_reword:
            paths.append(path)
        elif prompt_variant == PROMPT_OFFICIAL and not is_reword:
            paths.append(path)
    return paths


def update_leaderboard(
    output_dir: Path,
    leaderboard_path: Path,
    prompt_variant: str = PROMPT_OFFICIAL,
) -> None:
    paths = list_run_paths(output_dir, prompt_variant)
    if not paths:
        raise FileNotFoundError(
            f"No {prompt_variant} prediction files found in {output_dir}; "
            "existing leaderboard was not changed. See REPRODUCIBILITY.md."
        )
    results = [parse_run(path) for path in paths]
    plot_links = []
    timed = [
        result
        for result in results
        if result["score"] is not None and result["median_seconds"] is not None
    ]
    if timed:
        plot_dir = leaderboard_path.parent / "plots" / TASK
        if prompt_variant == PROMPT_REWORD:
            plot_dir = plot_dir.with_name(f"{plot_dir.name}-reword")
        generated_plots = generate_plots(results, plot_dir)
        plot_links = [
            (
                label,
                Path(os.path.relpath(plot_path, start=leaderboard_path.parent)),
            )
            for label, plot_path in generated_plots
        ]
    contents = render_leaderboard(
        results,
        output_dir,
        plot_links,
        prompt_variant=prompt_variant,
    )
    temporary_path = leaderboard_path.with_suffix(
        f"{leaderboard_path.suffix}.tmp"
    )
    temporary_path.write_text(contents, encoding="utf-8")
    temporary_path.replace(leaderboard_path)
    print(f"Updated {leaderboard_path} with {len(results)} runs")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output") / TASK,
    )
    parser.add_argument(
        "--leaderboard",
        type=Path,
        default=Path("LEADERBOARD.md"),
    )
    parser.add_argument(
        "--prompt-variant",
        choices=(PROMPT_OFFICIAL, PROMPT_REWORD),
        default=PROMPT_OFFICIAL,
        help="Which run family to score. cutin-reword reads *-reword.json only.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    update_leaderboard(
        args.output_dir,
        args.leaderboard,
        prompt_variant=args.prompt_variant,
    )


if __name__ == "__main__":
    main()
