#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "huggingface-hub>=0.24",
#     "matplotlib>=3.7",
#     "numpy>=1.24",
#     "openai>=1.30",
#     "pillow>=10",
# ]
# ///
"""Run VLADBench Vehicle_Cutin through an OpenAI-compatible chat API.

    # Download and run one request against a Modal-hosted Qwen endpoint.
    uv run run_vehicle_cutin.py --download --limit 1 --max-calls 1 \
        --base-url https://example.modal.run/v1 --model MODEL_ID

    # Run the complete task after the smoke test succeeds.
    uv run run_vehicle_cutin.py --data-root ./data/VLADBench \
        --base-url https://example.modal.run/v1 --model MODEL_ID

    # Same labels, cut-in wording. Writes *-reword.json and skips LEADERBOARD.md.
    uv run run_vehicle_cutin.py --reword --data-root ./data/VLADBench \
        --base-url https://example.modal.run/v1 --model MODEL_ID

Environment:
    OPENAI_API_KEY
    OPENAI_BASE_URL   default https://api.openai.com/v1
    OPENAI_MODEL      default gpt-4o
    MODAL_KEY         optional proxy-auth key
    MODAL_SECRET      optional proxy-auth secret
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from PIL import Image

from evaluate_utils import Judge_criterion_QA, load_json_data, save_json_data

TASK = "Vehicle_Cutin"
TASK_RELATIVE = Path("Target_Attribute_Comprehension") / "Intention_Judgment"
HF_REPO = "depth2world/VLADBench"
CUTIN_WEIGHTS = [0.7, 0.1, 0.2]
PROMPT_OFFICIAL = "official"
PROMPT_REWORD = "cutin-reword"
CUT_IN_JUDGE = (
    "intend to cut in (enter or cross into the ego vehicle's path)"
)
CUT_IN_ASSERT = (
    "intends to cut in (enter or cross into the ego vehicle's path)"
)
CROSS_THE_ROAD_QUESTION = re.compile(
    r"have the intention to cross the road\?",
    re.IGNORECASE,
)
CROSS_THE_ROAD_ASSERTION = re.compile(
    r"have the intention to cross the road\.",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CompletionMetadata:
    started_at: str
    completed_at: str
    api_elapsed_seconds: float
    attempts: int
    finish_reason: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    reasoning_tokens: int | None


def resolve_paths(data_root: Path) -> tuple[Path, Path]:
    """Accept either the VLADBench root or the Vehicle_Cutin folder itself."""
    json_at_root = data_root / TASK_RELATIVE / f"{TASK}_E.json"
    images_at_root = data_root / TASK_RELATIVE / TASK
    if json_at_root.is_file() and images_at_root.is_dir():
        return json_at_root, images_at_root

    json_beside = data_root.parent / f"{TASK}_E.json"
    if data_root.name == TASK and json_beside.is_file():
        return json_beside, data_root

    raise FileNotFoundError(
        f"Could not find {TASK} under {data_root}. "
        "Pass --data-root to the VLADBench root, or download first with --download."
    )


def download_vehicle_cutin(data_root: Path, limit: int | None = None) -> None:
    """Download the task, or only the clips needed by a limited run."""
    from huggingface_hub import hf_hub_download, snapshot_download

    data_root.mkdir(parents=True, exist_ok=True)
    task_prefix = f"{TASK_RELATIVE.as_posix()}/{TASK}"
    metadata_name = f"{TASK_RELATIVE.as_posix()}/{TASK}_E.json"

    if limit is not None:
        hf_hub_download(
            repo_id=HF_REPO,
            repo_type="dataset",
            filename=metadata_name,
            local_dir=str(data_root),
        )
        samples = load_json_data(str(data_root / metadata_name))[:limit]
        filenames = {
            f"{task_prefix}/{sample['sequence']}/{frame_name}"
            for sample in samples
            for question in sample["questions"]
            for frame_name in sample[split_question(question)[0]]
        }
        print(
            f"Downloading {len(filenames)} images for {len(samples)} "
            f"{TASK} clips from {HF_REPO}"
        )
        for filename in sorted(filenames):
            hf_hub_download(
                repo_id=HF_REPO,
                repo_type="dataset",
                filename=filename,
                local_dir=str(data_root),
            )
        return

    print(f"Downloading all {TASK} data from {HF_REPO} into {data_root}")
    snapshot_download(
        repo_id=HF_REPO,
        repo_type="dataset",
        local_dir=str(data_root),
        allow_patterns=[
            f"{task_prefix}/**",
            metadata_name,
        ],
    )


def encode_image(path: Path, max_side: int) -> str:
    with Image.open(path) as source:
        image = source.convert("RGB")
        if max_side > 0 and max(image.size) > max_side:
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def split_question(raw: str) -> tuple[str, str]:
    frame_key, question = raw.split(";", 1)
    return frame_key.strip().strip("[]"), question.strip()


def reword_cutin_question(text: str) -> str:
    """Replace VLAD's 'cross the road' ask with a cut-in ask.

    Gold answers and scoring still use the original dataset strings.
    """
    rewritten, replaced = CROSS_THE_ROAD_QUESTION.subn(
        f"{CUT_IN_JUDGE}?",
        text,
        count=1,
    )
    if replaced:
        return rewritten
    rewritten, replaced = CROSS_THE_ROAD_ASSERTION.subn(
        f"{CUT_IN_ASSERT}.",
        text,
        count=1,
    )
    if replaced:
        return rewritten
    raise ValueError(
        "Question does not contain 'intention to cross the road': "
        f"{text[:160]!r}"
    )


def normalize_base_url(raw_url: str) -> str:
    """Accept either an API root or a pasted chat-completions URL."""
    parts = urlsplit(raw_url.rstrip("/"))
    path = parts.path.removesuffix("/chat/completions")
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def build_user_content(
    sample: dict,
    question: str,
    image_dir: Path,
    max_side: int,
    detail: str,
    reword: bool = False,
) -> list[dict]:
    frame_key, text = split_question(question)
    if reword:
        text = reword_cutin_question(text)
    frames = sample[frame_key]
    country = sample["country"]
    content = []
    for name in frames:
        path = image_dir / sample["sequence"] / name
        if not path.is_file():
            raise FileNotFoundError(path)
        payload = encode_image(path, max_side)
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{payload}",
                    "detail": detail,
                },
            }
        )
    content.append(
        {
            "type": "text",
            "text": f"The sequence is from {country}. {text}",
        }
    )
    return content


def complete(
    client,
    model: str,
    content: list[dict],
    max_tokens: int | None,
    retries: int,
    reasoning: str,
    reasoning_effort: str | None,
) -> tuple[str, CompletionMetadata]:
    started_at = datetime.now(timezone.utc)
    started_timer = time.perf_counter()
    last_error = None
    for attempt in range(retries):
        try:
            request_options = {}
            use_reasoning = reasoning == "enabled"
            disable_reasoning = reasoning == "disabled" or (
                reasoning == "auto" and "qwen" in model.lower()
            )
            if reasoning_effort:
                request_options["extra_body"] = {
                    "reasoning_effort": reasoning_effort,
                }
            elif use_reasoning:
                request_options["extra_body"] = {
                    "reasoning": {"enabled": True},
                }
            elif disable_reasoning:
                request_options["extra_body"] = {
                    "reasoning": {"enabled": False},
                    "chat_template_kwargs": {"enable_thinking": False},
                }
            if max_tokens is not None:
                request_options["max_tokens"] = max_tokens

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": content}],
                temperature=0,
                **request_options,
            )
            choice = response.choices[0]
            answer = (choice.message.content or "").strip()
            if not answer:
                reasoning_content = getattr(
                    choice.message, "reasoning_content", None
                )
                detail = (
                    "reasoning was generated without a final answer"
                    if reasoning_content
                    else "the response contained no text"
                )
                raise ValueError(
                    f"Empty completion ({detail}; finish_reason={choice.finish_reason})"
                )
            completed_at = datetime.now(timezone.utc)
            usage = response.usage
            completion_details = (
                getattr(usage, "completion_tokens_details", None) if usage else None
            )
            reasoning_tokens = getattr(usage, "reasoning_tokens", None)
            if reasoning_tokens is None and completion_details is not None:
                reasoning_tokens = getattr(
                    completion_details, "reasoning_tokens", None
                )
            metadata = CompletionMetadata(
                started_at=started_at.isoformat(),
                completed_at=completed_at.isoformat(),
                api_elapsed_seconds=round(time.perf_counter() - started_timer, 3),
                attempts=attempt + 1,
                finish_reason=choice.finish_reason,
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                reasoning_tokens=reasoning_tokens,
            )
            return answer, metadata
        except Exception as error:  # noqa: BLE001 - retry provider and transport errors
            last_error = error
            status_code = getattr(error, "status_code", None)
            retryable = (
                status_code is None
                or status_code in {408, 409, 429}
                or status_code >= 500
            )
            if not retryable:
                break
            if attempt < retries - 1:
                wait = 2 ** attempt
                print(f"  retry {attempt + 1}/{retries} after {wait}s: {error}")
                time.sleep(wait)
    raise RuntimeError(
        f"API call failed after {retries} attempts: {last_error}"
    ) from last_error


def prompt_variant_of(samples: list[dict]) -> str | None:
    variants = {
        sample.get("prompt_variant")
        for sample in samples
        if sample.get("prompt_variant")
    }
    if len(variants) > 1:
        raise ValueError(f"Mixed prompt variants in one file: {sorted(variants)}")
    if variants:
        return next(iter(variants))
    has_predictions = any(
        prediction
        for sample in samples
        for prediction in sample.get("prediction", [])
    )
    if has_predictions:
        return PROMPT_OFFICIAL
    return None


def sent_question(raw: str) -> str:
    frame_key, text = split_question(raw)
    return f"[{frame_key}]; {reword_cutin_question(text)}"


def stamp_reword_samples(samples: list[dict]) -> None:
    for sample in samples:
        sample["prompt_variant"] = PROMPT_REWORD
        sample["questions_sent"] = [
            sent_question(question) for question in sample["questions"]
        ]


def merge_predictions(samples: list[dict], previous_samples: list[dict]) -> int:
    """Copy completed predictions into fresh benchmark metadata."""
    previous_by_id = {sample["id"]: sample for sample in previous_samples}
    resumed = 0
    for sample in samples:
        previous = previous_by_id.get(sample["id"])
        if previous is None or "prediction" not in previous:
            continue
        predictions = previous["prediction"]
        if len(predictions) != len(sample["questions"]):
            raise ValueError(
                f"Prediction count changed for sample {sample['id']}: "
                f"{len(predictions)} != {len(sample['questions'])}"
            )
        sample["prediction"] = predictions
        if "completion_metadata" in previous:
            metadata = previous["completion_metadata"]
            if len(metadata) != len(sample["questions"]):
                raise ValueError(
                    f"Completion metadata count changed for sample {sample['id']}: "
                    f"{len(metadata)} != {len(sample['questions'])}"
                )
            sample["completion_metadata"] = metadata
        if "questions_sent" in previous:
            sample["questions_sent"] = previous["questions_sent"]
        if "prompt_variant" in previous:
            sample["prompt_variant"] = previous["prompt_variant"]
        resumed += sum(bool(prediction) for prediction in predictions)
    return resumed


def official_score(samples: list[dict], model_name: str) -> dict:
    total, description_acc, obey, judge_acc = Judge_criterion_QA(samples, model_name)
    score = (
        100 * judge_acc * CUTIN_WEIGHTS[0]
        + 100 * description_acc * CUTIN_WEIGHTS[1]
        + 100 * obey * CUTIN_WEIGHTS[2]
    )
    return {
        "questions": total,
        "judge_accuracy": judge_acc,
        "description_accuracy": description_acc,
        "instruction_follow": obey,
        "official_score": score,
    }


def print_score(metrics: dict, prompt_variant: str = PROMPT_OFFICIAL) -> None:
    print(
        f"{TASK}  prompt={prompt_variant}  n={metrics['questions']}  "
        f"judge={metrics['judge_accuracy']:.3f}  "
        f"reason={metrics['description_accuracy']:.3f}  "
        f"obey={metrics['instruction_follow']:.3f}  "
        f"official={metrics['official_score']:.2f}"
    )


def default_output_path(model: str, reword: bool) -> Path:
    path = Path("output") / TASK / f"{model}.json"
    if reword:
        return path.with_name(f"{path.stem}-reword{path.suffix}")
    return path


def run_inference(args: argparse.Namespace) -> Path:
    json_path, image_dir = resolve_paths(args.data_root)
    output_path = args.output or default_output_path(args.model, args.reword)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    samples = load_json_data(str(json_path))
    wanted_variant = PROMPT_REWORD if args.reword else PROMPT_OFFICIAL
    if output_path.is_file():
        previous_samples = load_json_data(str(output_path))
        previous_variant = prompt_variant_of(previous_samples)
        if previous_variant and previous_variant != wanted_variant:
            raise SystemExit(
                f"Refusing to mix {previous_variant} predictions into a "
                f"{wanted_variant} run: {output_path}"
            )
        resumed = merge_predictions(samples, previous_samples)
        print(f"Resuming {resumed} completed questions from {output_path}")
    if args.reword:
        stamp_reword_samples(samples)

    work = samples[: args.limit] if args.limit else samples

    from openai import OpenAI

    if bool(args.modal_key) != bool(args.modal_secret):
        raise ValueError("Both MODAL_KEY and MODAL_SECRET are required")
    modal_api_key = (
        f"{args.modal_key}.{args.modal_secret}"
        if args.modal_key and args.modal_secret
        else None
    )
    hostname = urlsplit(args.base_url).hostname
    provider_api_key = (
        os.environ.get("OPENROUTER_API_KEY")
        if hostname == "openrouter.ai"
        else None
    )
    default_api_key = (
        provider_api_key if hostname == "openrouter.ai" else modal_api_key
    )

    client_options = {
        "api_key": (
            args.api_key
            or default_api_key
            or "not-needed"
        ),
        "base_url": normalize_base_url(args.base_url),
        "max_retries": 0,
    }
    if args.timeout is not None:
        client_options["timeout"] = args.timeout
    client = OpenAI(**client_options)
    jobs = []
    for sample in work:
        if "prediction" not in sample:
            sample["prediction"] = [""] * len(sample["questions"])
        if "completion_metadata" not in sample:
            sample["completion_metadata"] = [None] * len(sample["questions"])
        for index, question in enumerate(sample["questions"]):
            if not sample["prediction"][index]:
                jobs.append((sample, index, question))
    if args.max_calls is not None:
        jobs = jobs[: args.max_calls]

    print(
        f"{len(work)} clips, {len(jobs)} calls scheduled at "
        f"concurrency {args.concurrency}, "
        f"images in {image_dir}, writing {output_path}"
    )
    if args.reword:
        print("Rewording 'cross the road' to a cut-in ask")
        if jobs:
            _, _, question = jobs[0]
            original = split_question(question)[1]
            print(f"  in:  {original}")
            print(f"  out: {reword_cutin_question(original)}")

    def infer(job: tuple[dict, int, str]) -> tuple[str, CompletionMetadata]:
        sample, _, question = job
        content = build_user_content(
            sample,
            question,
            image_dir,
            args.max_side,
            args.detail,
            args.reword,
        )
        return complete(
            client,
            args.model,
            content,
            args.max_tokens,
            args.retries,
            args.reasoning,
            args.reasoning_effort,
        )

    done = 0
    failures = []
    start = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        future_jobs = {executor.submit(infer, job): job for job in jobs}
        for future in as_completed(future_jobs):
            sample, index, _ = future_jobs[future]
            try:
                answer, metadata = future.result()
            except Exception as error:  # noqa: BLE001 - report all failed jobs
                failures.append((sample["sequence"], index + 1, error))
                print(f"FAILED {sample['sequence']} q{index + 1}: {error}")
                continue
            sample["prediction"][index] = answer
            sample["completion_metadata"][index] = asdict(metadata)
            done += 1
            print(
                f"[{done}/{len(jobs)}] {sample['sequence']} q{index + 1}  "
                f"{metadata.api_elapsed_seconds:.3f}s  "
                f"ref={sample['reference'][index]!r}  pred={answer!r}"
            )
            save_json_data(str(output_path), samples)

    print(f"Finished {done} calls in {time.time() - start:.1f}s")
    if failures:
        raise RuntimeError(
            f"{len(failures)} calls failed; rerun the command to retry them"
        )
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("VLADBENCH_ROOT", "./data/VLADBench")),
        help="VLADBench root, or the Vehicle_Cutin image folder",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Prediction JSON. Default: output/Vehicle_Cutin/<model>.json, or *-reword.json with --reword",
    )
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o"))
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENAI_API_KEY"),
    )
    parser.add_argument("--modal-key", default=os.environ.get("MODAL_KEY"), help="Modal proxy token ID.")
    parser.add_argument("--modal-secret", default=os.environ.get("MODAL_SECRET"), help="Modal proxy token secret.")
    parser.add_argument(
        "--timeout",
        type=float,
        help="Optional per-request timeout in seconds. Default: no timeout.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        help="Optional output-token cap. By default the request has no explicit cap.",
    )
    parser.add_argument(
        "--reasoning",
        choices=("auto", "enabled", "disabled"),
        default="auto",
        help="Reasoning mode. Auto disables thinking for Qwen benchmark answers.",
    )
    parser.add_argument(
        "--reasoning-effort",
        help="Provider-specific reasoning effort, such as xhigh. Overrides --reasoning.",
    )
    parser.add_argument("--max-side", type=int, default=1280, help="Resize long side. 0 keeps originals.")
    parser.add_argument("--detail", choices=("low", "high", "auto"), default="low")
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--concurrency", type=int, default=1, help="Maximum simultaneous API requests.")
    parser.add_argument("--limit", type=int, help="Only the first N clips. Use 1 for a smoke test.")
    parser.add_argument("--max-calls", type=int, help="Stop after N API requests. Use 1 for a smoke test.")
    parser.add_argument(
        "--reword",
        action="store_true",
        help=(
            "Replace 'intention to cross the road' with a cut-in ask. "
            "Gold labels and scoring are unchanged. Default output is "
            "*-reword.json; scores go to LEADERBOARD-reword.md."
        ),
    )
    parser.add_argument("--download", action="store_true", help="Fetch only Vehicle_Cutin from Hugging Face.")
    parser.add_argument("--score-only", action="store_true", help="Score an existing prediction JSON and exit.")
    parser.add_argument(
        "--leaderboard",
        type=Path,
        default=Path("LEADERBOARD.md"),
        help="Markdown leaderboard updated after a successful run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.limit is not None and args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    if args.max_calls is not None and args.max_calls < 1:
        raise SystemExit("--max-calls must be at least 1")
    if args.max_tokens is not None and args.max_tokens < 1:
        raise SystemExit("--max-tokens must be at least 1")
    if args.timeout is not None and args.timeout <= 0:
        raise SystemExit("--timeout must be greater than zero")
    if args.retries < 1:
        raise SystemExit("--retries must be at least 1")
    if args.concurrency < 1:
        raise SystemExit("--concurrency must be at least 1")

    if args.download:
        download_vehicle_cutin(args.data_root, args.limit)
        if args.score_only or args.api_key is None:
            is_openai = urlsplit(args.base_url).hostname == "api.openai.com"
            if args.score_only or is_openai:
                json_path, image_dir = resolve_paths(args.data_root)
                print(f"Ready: {json_path}")
                print(f"Images: {image_dir}")
                return

    if args.score_only:
        if args.output is None or not args.output.is_file():
            raise SystemExit("--score-only needs --output pointing at a prediction JSON")
        samples = load_json_data(str(args.output))
        print_score(
            official_score(samples, args.model),
            prompt_variant_of(samples) or PROMPT_OFFICIAL,
        )
        return

    if not args.api_key and urlsplit(args.base_url).hostname == "api.openai.com":
        raise SystemExit("Set OPENAI_API_KEY or pass --api-key")

    output_path = run_inference(args)
    samples = load_json_data(str(output_path))
    work = samples[: args.limit] if args.limit else samples
    remaining = sum(
        not prediction
        for sample in work
        for prediction in sample.get("prediction", [])
    )
    if remaining:
        print(f"Skipping score: {remaining} questions do not have predictions yet")
    else:
        print_score(
            official_score(work, args.model),
            PROMPT_REWORD if args.reword else PROMPT_OFFICIAL,
        )

    from update_leaderboard import update_leaderboard

    output_dir = Path("output") / TASK
    if args.reword:
        reword_board = args.leaderboard
        if reword_board == Path("LEADERBOARD.md"):
            reword_board = Path("LEADERBOARD-reword.md")
        update_leaderboard(
            output_dir,
            reword_board,
            prompt_variant=PROMPT_REWORD,
        )
    else:
        update_leaderboard(output_dir, args.leaderboard)


if __name__ == "__main__":
    main()
