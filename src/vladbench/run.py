"""For each model, for each question: build the request, send it, record the answer.

Start from ``run``. Answers append to ``results/runs/<condition>/<model>/<task>.jsonl``
(gitignored; the scored summaries next to it in ``results/`` are tracked).
Running again skips questions that already have an answer. Any failure that
survives one retry raises and stops the process.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import time
from typing import TextIO
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from .dataset import REPO_ROOT
from .requests import build, canonical_json, questions, tasks
from .video import MediaCache

RUNS = REPO_ROOT / "results/runs"
load_dotenv(REPO_ROOT / ".env")


def credential(model: dict) -> str:
    variable = model["credential"]["variable"]
    value = os.environ.get(variable)
    if not value:
        raise ValueError(f"{model['id']}: set {variable}")
    return value


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


def provenance() -> dict:
    return {"git_commit": git("rev-parse", "HEAD") or None, "git_dirty": bool(git("status", "--porcelain")), "python": platform.python_version()}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # a crash-truncated last line; the question is simply re-asked
    return records


def post(endpoint: str, payload: dict, api_key: str, timeout: float) -> dict:
    url = endpoint.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    request = Request(url, data=canonical_json(payload).encode(), method="POST",
                      headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def http_detail(error: HTTPError) -> str:
    if not hasattr(error, "detail"):
        error.detail = error.read(4000).decode("utf-8", errors="replace")
        error.close()
    return error.detail


TRANSIENT_FETCH_MARKERS = ("429 status code when fetching image", "media_url_not_fetchable", "media_url_origin_error",
                           "failed to download media", "origin returned http 429")


def fetch_failure(error: Exception) -> bool:
    """The provider could not fetch a dataset image from Hugging Face; the origin needs time, not a fast retry."""
    return isinstance(error, HTTPError) and any(marker in http_detail(error).lower() for marker in TRANSIENT_FETCH_MARKERS)


def retryable(error: Exception) -> bool:
    """Server-side trouble, or the provider failing to fetch a dataset image, is worth one more try."""
    if not isinstance(error, HTTPError):
        return True  # timeouts and connection resets
    return error.code in (408, 409, 429) or error.code >= 500 or fetch_failure(error)


def slow_retry(error: Exception) -> bool:
    """Outages and origin throttling clear in tens of seconds, not one."""
    return fetch_failure(error) or (isinstance(error, HTTPError) and error.code >= 500)


def backoff(error: Exception, attempt: int) -> float:
    return (10 if slow_retry(error) else 1) * 2 ** attempt


def describe(model: dict, question: dict, error: Exception) -> RuntimeError:
    detail = f"HTTP {error.code}: {http_detail(error)}" if isinstance(error, HTTPError) else f"{type(error).__name__}: {error}"
    return RuntimeError(f"{model['id']} {question['task']} {question['id']}: {detail}")


def send(model: dict, question: dict, payload: dict, protocol: dict, api_key: str) -> tuple[dict, int]:
    """POST with one retry on transient failure; returns (response, attempts)."""
    for attempt in range(protocol["max_attempts"]):
        try:
            return post(model["endpoint"], payload, api_key, protocol["timeout_seconds"]), attempt + 1
        except (HTTPError, TimeoutError, OSError) as error:
            if not retryable(error) or attempt + 1 == protocol["max_attempts"]:
                raise describe(model, question, error) from None
            time.sleep(backoff(error, attempt))
    raise AssertionError("unreachable")


def text_of(content) -> str | None:
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if p.get("type") == "text")
    return content


def answer_text(response: dict) -> str:
    """The visible answer, or empty when the response carried none."""
    content = text_of(response["choices"][0].get("message", {}).get("content"))
    return content.strip() if isinstance(content, str) else ""


def degenerate(answer: str) -> bool:
    """A long run of one repeated character is a serving fault (seen as '!!!!…' from a quantised host), not an answer."""
    return len(answer) >= 64 and len(set(answer)) == 1


def send_until_answered(model: dict, question: dict, payload: dict, protocol: dict, api_key: str) -> tuple[dict, str, int]:
    """Redraw a response with no usable answer: nothing visible, the guard cut it off, or a degenerate repeated character.

    The last attempt is recorded either way; an empty or degenerate answer is scored as unanswered.
    """
    used = 0
    for _ in range(protocol["max_attempts"]):
        response, attempts = send(model, question, payload, protocol, api_key)
        used += attempts
        answer = answer_text(response)
        if answer and not degenerate(answer):
            break
    return response, answer, used


def record(question: dict, protocol_sha256: str, receipt: dict | None, response: dict, answer: str, elapsed: float, attempts: int) -> dict:
    receipt = receipt or {}
    return dict(id=question["id"], task=question["task"], sample_index=question["sample_index"], question_index=question["question_index"],
                protocol_sha256=protocol_sha256, answer=answer, finish_reason=response["choices"][0].get("finish_reason"),
                usage=response.get("usage"), elapsed_seconds=elapsed, attempt=attempts,
                video_sha256=receipt.get("encoded_sha256"), lossy_fallback=bool(receipt.get("provider_size_fallback")),
                response=response, timestamp=datetime.now(timezone.utc).isoformat())


def ask(spec: dict, model: dict, question: dict, media: MediaCache, api_key: str) -> dict:
    payload, protocol_sha256, receipt = build(spec, model, question, media)
    started = time.monotonic()
    response, answer, attempts = send_until_answered(model, question, payload, spec["protocol"], api_key)
    return record(question, protocol_sha256, receipt, response, answer, time.monotonic() - started, attempts)


def collect(pool: ThreadPoolExecutor, futures: dict[Future, str], folder: Path, finished: Callable[[str], None]) -> None:
    """Append each answer to its task's file as it completes, calling ``finished`` as each task's last answer lands;
    stop everything on the first failure."""
    left = Counter(futures.values())
    files: dict[str, TextIO] = {}
    try:
        for future in as_completed(futures):
            task = futures[future]
            if task not in files:
                files[task] = (folder / f"{task}.jsonl").open("a")
            files[task].write(canonical_json(future.result()) + "\n")
            files[task].flush()
            left[task] -= 1
            if not left[task]:
                finished(task)
    except BaseException:
        pool.shutdown(cancel_futures=True)
        raise
    finally:
        for out in files.values():
            out.close()


def pending_questions(spec: dict, task: str, path: Path, smoke: bool) -> tuple[int, list[dict]]:
    """(already answered, still to ask) for one task."""
    done = {r["id"] for r in read_jsonl(path)}
    pending = [q for q in questions(task, spec["dataset_revision"], smoke=smoke) if q["id"] not in done]
    return len(done), pending


def run_model(spec: dict, model: dict, folder: Path, media: MediaCache, smoke: bool) -> None:
    """Every task's unanswered questions share one pool, so a smoke run's one question per task is asked in parallel too."""
    api_key = credential(model)
    folder.mkdir(parents=True, exist_ok=True)
    meta = {"specification": spec["path"], "specification_sha256": spec["sha256"], "model": model, "protocol": spec["protocol"],
            "smoke": smoke, "started_at": datetime.now(timezone.utc).isoformat(), **provenance()}
    (folder / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    plan = {task: pending_questions(spec, task, folder / f"{task}.jsonl", smoke) for task in tasks(spec["dataset_revision"])}

    def finished(task: str) -> None:
        done, pending = plan[task]
        print(f"{model['id']} {task}: {done + len(pending)} answered", flush=True)

    for task, (_, pending) in plan.items():
        if not pending:
            finished(task)
    with ThreadPoolExecutor(max_workers=spec["protocol"]["concurrency_per_model"]) as pool:
        futures = {pool.submit(ask, spec, model, q, media, api_key): task for task, (_, pending) in plan.items() for q in pending}
        collect(pool, futures, folder, finished)


def wanted_ids(spec: dict, model_ids: list[str] | None) -> set[str]:
    known = {m["id"] for m in spec["models"]}
    wanted = set(model_ids) if model_ids else known
    if wanted - known:
        raise ValueError(f"unknown model ids {sorted(wanted - known)}")
    return wanted


def select_models(spec: dict, model_ids: list[str] | None) -> list[dict]:
    wanted = wanted_ids(spec, model_ids)
    return [m for m in spec["models"] if m["id"] in wanted]


def run(spec: dict, model_ids: list[str] | None = None, *, smoke: bool = False, runs_dir: Path = RUNS) -> None:
    condition = spec["name"] + ("-smoke" if smoke else "")
    models = select_models(spec, model_ids)
    for model in models:
        credential(model)  # every key before anything is written or billed
    media = MediaCache(runs_dir / "media", fps=spec["protocol"]["video"]["fps"])
    for model in models:
        run_model(spec, model, runs_dir / condition / model["id"], media, smoke)
