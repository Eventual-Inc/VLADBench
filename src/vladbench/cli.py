"""vladbench validate SPEC | run SPEC [--models ...] [--smoke] | score SPEC [--models ...]"""
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


COMMANDS = {"validate": validate, "run": run, "score": score}


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
    return top


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    COMMANDS[args.command](load_spec(args.specification), args)
    return 0
