"""Publish the results dataset and the static results site to Hugging Face, incrementally.

  PYTHONPATH=src python3 scripts/publish_hf.py --dry-run        # build the dataset card and the Space folder, upload nothing
  PYTHONPATH=src python3 scripts/publish_hf.py                  # upload the dataset; only changed files are transferred
  PYTHONPATH=src python3 scripts/publish_hf.py --with-space     # also build and upload the static Space (the blog is the primary host)
  PYTHONPATH=src python3 scripts/publish_hf.py --org-card       # also publish the organisation card (a Space named README)

Needs HF_TOKEN in .env (a write token with access to the target organisation). Run scripts/export_parquet.py first;
the parquet tables in results/dataset/ are what gets published. Uploads are content-addressed by the Hub, so re-running
after a new model lands sends the changed tables and pages only, in one commit per repo.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "results/dataset"
SPACE_BUILD = ROOT / "dist/space"
RERUN = ROOT / "results/rerun.json"
SPEC = ROOT / "results/protocols/full-original.json"
SITE_FILES = ["results.html", "self-test.html", "task-review-data.js", "task-review-audit.js",
              "task-review-published.js", "task-review-results.js"]
TABLES = ["models", "tasks", "questions", "answers", "task_scores"]


def load_json(path: Path):
    return json.loads(path.read_text())


CARD_TEMPLATE_PATH = ROOT / "docs/hf-dataset-card.md"   # edit the card text there; @PLACEHOLDERS@ are filled from results/rerun.json
ORG_CARD_PATH = ROOT / "docs/hf-org-card.md"


def total(model: dict) -> float:
    pairs = [(t["score"], t["questions_scored"]) for t in model["tasks"].values()]
    return sum(v * w for v, w in pairs) / sum(w for _, w in pairs)


def model_row(m: dict) -> str:
    transport = "video" if m["declared"]["input_transport"] == "video_mp4" else "images"
    return (f"| {m.get('lab', '')} | {m['label']} | `{m['model']}` | {m.get('parameters', 'undisclosed')} | {transport} | "
            f"{m['reasoning']} | {m['completion_cap']} | {m['truncated_answers'] or 0} |")


def cap_note(models: list[dict]) -> str:
    capped = [m["label"] for m in models if m["completion_cap"] == 512]
    note = ""
    if capped:
        note = ("The archived first protocol used a 512-token completion guard. " + ", ".join(capped)
                + " ran under it and were not re-run; the Truncated column counts answers that guard cut short. ")
    for m in (m for m in models if m.get("carried_from_superseded_condition")):
        note += (f"{m['label']} first ran under an archived protocol with a 512-token completion guard. Its cut answers were re-asked "
                 f"under the live 8192 guard and the rest carried over ({m['carried_from_superseded_condition']:,} answers, `models.carried_from_512`). ")
    return note


def spend(model: dict) -> str:
    usage = model.get("usage") or {}
    if usage.get("cost_usd") is None:
        return "n/a"
    return f"${usage['cost_usd']:,.2f}"


def usd(model: dict, key: str, digits: int = 2) -> str:
    value = (model.get("usage") or {}).get(key)
    return "n/a" if value is None else f"${value:,.{digits}f}"


def leaderboard_rows(models: list[dict]) -> tuple[str, str, dict]:
    """Featured models ranked by TOTAL, a note on omitted ones, and the best model."""
    ranked = sorted([m for m in models if m.get("featured", True)], key=total, reverse=True)
    omitted = [m for m in models if not m.get("featured", True)]
    rows = "\n".join(f"| {i + 1} | {m['label']} | {total(m):.2f} | {spend(m)} | {usd(m, 'input_cost_per_frame_usd', 5)} | {usd(m, 'output_cost_per_query_usd', 5)} | {usd(m, 'cost_per_video_hour_usd')} |"
                      for i, m in enumerate(ranked))
    note = ("" if not omitted else "Also in the data but left out of the figure and this table: "
            + "; ".join(f"{m['label']} ({total(m):.2f}, {m['not_featured_reason']})" for m in omitted) + ". `models.featured` marks them.")
    return rows, note, ranked[0]


def dataset_card(dataset_repo: str, rerun: dict) -> str:
    """The dataset README from docs/hf-dataset-card.md, with every @PLACEHOLDER@ filled from the results record."""
    models = sorted(rerun["models"], key=lambda m: (m.get("lab", ""), m.get("size_rank", 99)))
    leaderboard, omitted, best = leaderboard_rows(rerun["models"])
    fills = {"@CONFIGS@": "\n".join(f"  - config_name: {n}\n    data_files: {n}.parquet" for n in TABLES),
             "@DATE@": rerun["generated_at"][:10], "@SPEC@": hashlib.sha256(SPEC.read_bytes()).hexdigest()[:12],
             "@N_MODELS@": str(len(models)), "@N_TASKS@": str(rerun["dataset"]["tasks"]),
             "@N_QUESTIONS@": f"{rerun['dataset']['questions_per_model']:,}", "@N_ANSWERS@": f"{rerun['dataset']['responses']:,}",
             "@N_SCORES@": str(len(models) * rerun["dataset"]["tasks"]), "@MODEL_ROWS@": "\n".join(model_row(m) for m in models),
             "@CAP_NOTE@": cap_note(models), "@REPO@": dataset_repo, "@BEST@": best["label"], "@LEADERBOARD@": leaderboard, "@OMITTED@": omitted}
    card = CARD_TEMPLATE_PATH.read_text()
    for key, value in fills.items():
        card = card.replace(key, value)
    return card


def space_readme(dataset_repo: str) -> str:
    return f"""---
title: VLADBench re-evaluation
emoji: 🚗
colorFrom: purple
colorTo: pink
sdk: static
app_file: results.html
pinned: false
license: cc-by-4.0
---

Static results site for the VLADBench re-evaluation. The data behind it is published as parquet at
[{dataset_repo}](https://huggingface.co/datasets/{dataset_repo}).
Source: [Eventual-Inc/VLADBench](https://github.com/Eventual-Inc/VLADBench).
"""


def build_space(dataset_repo: str) -> Path:
    """Assemble the static site with its data source pointed at the published dataset."""
    if SPACE_BUILD.exists():
        shutil.rmtree(SPACE_BUILD)
    SPACE_BUILD.mkdir(parents=True)
    for name in SITE_FILES:
        shutil.copy(ROOT / name, SPACE_BUILD / name)
    shutil.copytree(ROOT / "web", SPACE_BUILD / "web")
    (SPACE_BUILD / "README.md").write_text(space_readme(dataset_repo))
    return SPACE_BUILD


def commit_message(rerun: dict) -> str:
    return f"Results as of {rerun['generated_at'][:19]}Z: {len(rerun['models'])} models, {rerun['dataset']['responses']:,} answers"


def render_figures() -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("plot_cost_score", ROOT / "scripts/plot_cost_score.py")
    plot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(plot)
    plot.render()
    plot.render(plot.OUT.with_name("cost-vs-score-hero.png"), hero=True)


def upload(api, repo_id: str, repo_type: str, folder: Path, message: str, **create) -> None:
    api.create_repo(repo_id, repo_type=repo_type, exist_ok=True, **create)
    info = api.upload_folder(repo_id=repo_id, repo_type=repo_type, folder_path=str(folder), commit_message=message)
    print(f"{repo_type} {repo_id}: {info.commit_url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", default="Eventual-Inc/VLADBench-reeval")
    parser.add_argument("--space", default="Eventual-Inc/vladbench")
    parser.add_argument("--with-space", action="store_true", help="also publish the static site as a Space")
    parser.add_argument("--space-only", action="store_true")
    parser.add_argument("--org-card", action="store_true", help="also publish the organisation card (Eventual-Inc/README Space)")
    parser.add_argument("--dry-run", action="store_true", help="build everything, upload nothing")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    rerun = load_json(RERUN)
    missing = [name for name in TABLES if not (DATASET_DIR / f"{name}.parquet").exists()]
    if missing:
        raise FileNotFoundError(f"Missing {missing}; run scripts/export_parquet.py first")
    (DATASET_DIR / "README.md").write_text(dataset_card(args.dataset, rerun))
    render_figures()
    site = build_space(args.dataset)
    org_dir = ROOT / "dist/org-card"
    if ORG_CARD_PATH.exists():
        org_dir.mkdir(parents=True, exist_ok=True)
        (org_dir / "README.md").write_text(ORG_CARD_PATH.read_text())
    elif args.org_card:
        raise FileNotFoundError(f"{ORG_CARD_PATH} is missing; the organisation card was published from it on 2026-09-16 and can be edited on the Hub")
    print(f"Dataset card written to {DATASET_DIR / 'README.md'}; Space built at {site}")
    if args.dry_run:
        return

    from huggingface_hub import HfApi

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise ValueError("HF_TOKEN is not set in .env")
    api = HfApi(token=token)
    message = commit_message(rerun)
    if not args.space_only:
        upload(api, args.dataset, "dataset", DATASET_DIR, message)
    if args.with_space or args.space_only:
        upload(api, args.space, "space", site, message, space_sdk="static")
    if args.org_card:
        upload(api, args.dataset.split("/")[0] + "/README", "space", org_dir, "Organisation card", space_sdk="static")
    print(f"Published at {datetime.now(timezone.utc).isoformat(timespec='seconds')}")


if __name__ == "__main__":
    main()
