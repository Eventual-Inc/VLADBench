"""vladbench validate SPEC | run SPEC [--models ...] [--smoke] | score SPEC [--models ...] | build [--steps ...] | publish [--dry-run]"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .spec import load_spec


def validate(spec: dict, args) -> None:
    print(json.dumps({"name": spec["name"], "sha256": spec["sha256"], "models": [m["id"] for m in spec["models"]],
                      "protocol": spec["protocol"]}, indent=2))


def run(spec: dict, args) -> None:
    from .run import run as run_models
    run_models(spec, args.models, smoke=args.smoke)


def score(spec: dict, args) -> None:
    from .run import select_models
    from .scoring import score_model
    superseded = [load_spec(path) for path in args.accept_superseded]
    for model in select_models(spec, args.models):
        result = score_model(spec, model, superseded=superseded)
        print(json.dumps({k: result[k] for k in ("model_id", "dataset_complete", "protocol_complete", "truncated_answers", "request_success")}))


def build(args) -> None:
    from .build import STEPS
    from .build import build as build_all
    steps = args.steps.split(",") if args.steps else STEPS
    report = build_all(steps=steps, allow_incomplete=args.allow_incomplete, site_out=args.site, article=args.article)
    print(f"{len(report.models)} models: {', '.join(report.models)}")
    for step, written in report.written.items():
        print(f"{step:10} {len(written)} file{'s' if len(written) != 1 else ''}")


def publish(args) -> None:
    import os

    from dotenv import load_dotenv

    from . import paths
    from .export import TABLES
    from .publish import commit_message, publish_dataset
    from .record import load_record
    missing = [name for name in (*(f"{t}.parquet" for t in TABLES), "README.md") if not (paths.DATASET / name).exists()]
    if missing:
        raise SystemExit(f"Missing {missing} in {paths.DATASET}; run vladbench build first")
    record = load_record()
    if args.dry_run:
        print(f"Would publish {paths.DATASET} to {args.repo}: {commit_message(record)}")
        return
    load_dotenv(paths.ROOT / ".env")
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN is not set in .env")
    print(publish_dataset(record, repo=args.repo, token=token))


COMMANDS = {"validate": validate, "run": run, "score": score}
OTHER = {"build": build, "publish": publish}


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(description=__doc__)
    sub = top.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        p = sub.add_parser(name)
        p.add_argument("specification", type=Path)
        p.add_argument("--models", nargs="+")
    sub.choices["run"].add_argument("--smoke", action="store_true", help="First question of every task only")
    sub.choices["score"].add_argument("--accept-superseded", type=Path, action="append", default=[], metavar="SPEC",
                                      help="Accept answers carried from this earlier specification when its cap did not bind them")
    b = sub.add_parser("build", help="Rebuild every derived file from the score files, in order")
    b.add_argument("--steps", help="Comma-separated subset of: record,site-data,answers,variants,export,figures,card,site")
    b.add_argument("--allow-incomplete", action="store_true", help="Leave out models whose run is partial instead of stopping")
    b.add_argument("--site", type=Path, help="Where the Pages site goes (default dist/pages)")
    b.add_argument("--article", help="Article URL for the nav; empty hides the link")
    pub = sub.add_parser("publish", help="Upload results/dataset/ to the Hugging Face dataset")
    pub.add_argument("--repo", default="Eventual-Inc/VLADBench-reeval")
    pub.add_argument("--dry-run", action="store_true")
    return top


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    if args.command in OTHER:
        OTHER[args.command](args)
    else:
        COMMANDS[args.command](load_spec(args.specification), args)
    return 0
