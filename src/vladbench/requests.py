"""Build the exact request for one model and one question.

Start from ``questions`` and ``build``. Everything model-specific is read from
the model's entry in the specification and applied here. The protocol hash
covers the request with the video bytes replaced by the frame URLs they were
built from, so it can be recomputed at scoring time without media.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import json

from .dataset import DEFAULT_REVISION, image_urls, list_tasks, load_task

PROVIDER_BODY_LIMIT = 20_000_000


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def tasks(revision: str = DEFAULT_REVISION) -> list[str]:
    return [t["name"] for t in list_tasks(revision) if t["available"]]


def question_record(task: str, revision: str, sample: dict, sample_index: int, question_index: int, totals: tuple[int, int]) -> dict:
    raw = sample["questions"][question_index]
    selector, text = raw.split(";", 1)
    sequence = selector.strip().startswith("[")
    return dict(
        id=digest([revision, task, sample_index, question_index, digest(sample)])[:24], task=task,
        sample_id=str(sample.get("id", sample.get("sequence", sample_index))), sample_index=sample_index,
        question_index=question_index, sample=sample, raw_question=raw, sequence=sequence,
        prompt=f"The {'sequence' if sequence else 'image'} is from {sample['country']}. {text}",
        image_urls=image_urls(sample, raw, task, revision), task_total_samples=totals[0], task_total_questions=totals[1])


def question_kinds(sample: dict) -> set[str]:
    """The kinds a task's scorer needs at least one of: a bounding-box question, a yes/no judgment."""
    kinds = {"bounding_box" for q in sample["questions"] if "located in the image?" in str(q).lower()}
    return kinds | {"judgment" for r in sample["reference"] if str(r).strip().rstrip(".").lower() in ("yes", "no")}


def smoke_samples(samples: list[dict]) -> list[int]:
    """The first sample, plus the first sample of each question kind the task has and the chosen ones lack.

    The scorer scores whole samples, and some scorers need at least one question of a kind.
    """
    chosen: list[int] = []
    have: set[str] = set()
    for index, sample in enumerate(samples):
        missing = question_kinds(sample) - have
        if not chosen or missing:
            chosen.append(index)
            have |= missing
    return chosen


def questions(task: str, revision: str = DEFAULT_REVISION, *, smoke: bool = False) -> list[dict]:
    """Every question of a task in annotation order; smoke keeps a few whole samples the scorer can score (smoke_samples)."""
    samples = load_task(task, revision)
    totals = (len(samples), sum(len(s["questions"]) for s in samples))
    keep = smoke_samples(samples) if smoke else range(len(samples))
    return [question_record(task, revision, samples[i], i, question_index, totals)
            for i in keep for question_index in range(len(samples[i]["questions"]))]


def reasoning_settings(model: dict) -> dict:
    effort = model["reasoning_effort"]
    if model["reasoning_parameter"] == "reasoning_effort":
        return {"reasoning_effort": effort}
    if effort == "none":
        return {"reasoning": {"enabled": False}}
    return {"reasoning": {"effort": effort}}


def image_content(question: dict, detail: str) -> list[dict]:
    content = [{"type": "image_url", "image_url": {"url": url, "detail": detail}} for url in question["image_urls"]]
    return content + [{"type": "text", "text": question["prompt"]}]


def video_content(model: dict, question: dict) -> tuple[list[dict], dict]:
    """Placeholder video part (frame URLs, frame count) plus the model's payload-level video options."""
    urls = question["image_urls"]
    part = {"type": "video_url", "video_url": {"frames": urls, "encoded_frames": len(urls)}}
    part.update(model["video_options"].get("content_part", {}))
    return [part, {"type": "text", "text": question["prompt"]}], deepcopy(model["video_options"].get("payload", {}))


def data_url(video: bytes) -> str:
    return "data:video/mp4;base64," + base64.b64encode(video).decode("ascii")


def attach_video(payload: dict, model: dict, question: dict, media) -> dict:
    """Replace the placeholder with real bytes; fall back to lossy encoding only if declared."""
    urls = question["image_urls"]
    path, video, receipt = media.lossless(urls)
    part = payload["messages"][0]["content"][0]
    part["video_url"] = {"url": data_url(video)}
    fallback = False
    if len(canonical_json(payload).encode()) >= PROVIDER_BODY_LIMIT:
        if model["oversize_fallback"] == "none":
            raise ValueError(f"{question['id']}: request exceeds the provider body limit and no fallback is declared")
        path, video, receipt = media.compressed(urls, path, receipt)
        part["video_url"] = {"url": data_url(video)}
        fallback = True
    return dict(receipt, provider_size_fallback=fallback, artifact=str(path))


def build(spec: dict, model: dict, question: dict, media=None) -> tuple[dict, str, dict | None]:
    """Return (payload, protocol_sha256, video_receipt).

    With ``media`` None the payload keeps the placeholder video part; the
    protocol hash is identical either way.
    """
    video = question["sequence"] and model["input_transport"] == "video_mp4"
    content, extra = video_content(model, question) if video else (image_content(question, spec["protocol"]["image_detail"]), {})
    payload = {"model": model["model"], "messages": [{"role": "user", "content": content}],
               "max_tokens": spec["protocol"]["max_tokens"], **reasoning_settings(model), **extra}
    protocol_sha256 = digest(payload)
    receipt = attach_video(payload, model, question, media) if video and media is not None else None
    return payload, protocol_sha256, receipt
