"""Read pinned annotation JSON; hand remote image URLs to the provider.

Start from ``list_tasks``, ``load_task``, and ``image_urls``. Only annotation
bytes are cached. Image lists preserve annotation order, including source
sequences whose filenames are not chronologically sorted.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from urllib.parse import quote
from urllib.request import urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REVISION = "1895f22252f9a702fed95334c8e3b60280b4c626"
DATASET_REPO = "depth2world/VLADBench"
ANNOTATION_LIMIT = 32 * 1024 * 1024


def validate_revision(revision: str) -> str:
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Dataset revision must be an immutable 40-character commit SHA")
    return revision


def invalid_path(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return not parts or path.startswith("/") or any(p in (".", "..") for p in parts) or "\\" in path


def remote_url(path: str, revision: str = DEFAULT_REVISION) -> str:
    validate_revision(revision)
    if invalid_path(path):
        raise ValueError("Invalid dataset-relative path")
    return f"https://huggingface.co/datasets/{DATASET_REPO}/resolve/{revision}/{quote(path, safe='/')}"


def task_entry(category: str, group: str, name: str, revision: str) -> dict:
    available = name != "Trajectory"
    annotation_path = f"{category}/{group}/{name}_E.json"
    return dict(name=name, category=category, group=group, available=available,
                unavailable_reason=None if available else "No released English annotation or registered scorer",
                annotation_path=annotation_path, annotation_url=remote_url(annotation_path, revision), revision=revision)


def list_tasks(revision: str = DEFAULT_REVISION) -> list[dict]:
    validate_revision(revision)
    catalog = json.loads((REPO_ROOT / "original/all_task.json").read_text())
    return [task_entry(category, group, name, revision)
            for category, groups in catalog.items() for group, names in groups.items() for name in names]


def task_info(task: str, revision: str = DEFAULT_REVISION) -> dict:
    for item in list_tasks(revision):
        if item["name"] == task:
            return item
    raise ValueError(f"Unknown task: {task}")


# ---- annotation bytes: local cache, then the audited copy, then the network ----

def cache_paths(info: dict, revision: str, cache_dir: Path | None) -> tuple[Path, Path]:
    root = cache_dir or Path(os.environ.get("VLADBENCH_CACHE", REPO_ROOT / ".cache/vladbench"))
    cache = root / revision / info["annotation_path"]
    return cache, cache.with_suffix(".sha256")


def cached_bytes(cache: Path, digest_path: Path, task: str) -> bytes | None:
    if not (cache.exists() and digest_path.exists()):
        return None
    data = cache.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest_path.read_text().strip():
        raise ValueError(f"Annotation cache checksum mismatch for {task}")
    return data


def audited_hash(report: dict, task: str) -> str | None:
    for entry in report.get("tasks", []):
        if entry["name"] == task:
            return entry.get("sha256")
    return None


def audited_bytes(info: dict, task: str, revision: str) -> bytes | None:
    """The copy under results/audit/gold_metadata, only if its recorded hash still matches."""
    audit = REPO_ROOT / "results/audit/gold-distributions.json"
    audited = REPO_ROOT / "results/audit/gold_metadata" / info["annotation_path"]
    if not (audited.exists() and audit.exists()):
        return None
    report = json.loads(audit.read_text())
    candidate = audited.read_bytes()
    matches = report.get("revision") == revision and audited_hash(report, task) == hashlib.sha256(candidate).hexdigest()
    return candidate if matches else None


def download(info: dict) -> bytes:
    with urlopen(info["annotation_url"], timeout=60) as response:
        data = response.read(ANNOTATION_LIMIT + 1)
    if len(data) > ANNOTATION_LIMIT:
        raise ValueError("Annotation exceeds 32 MiB limit")
    return data


def annotation_bytes(task: str, revision: str, cache_dir: Path | None = None) -> bytes:
    info = task_info(task, revision)
    if not info["available"]:
        raise ValueError(f"{task}: {info['unavailable_reason']}")
    cache, digest_path = cache_paths(info, revision, cache_dir)
    data = cached_bytes(cache, digest_path, task)
    if data is not None:
        return data
    data = audited_bytes(info, task, revision) or download(info)
    json.loads(data)  # Never cache a non-JSON error page.
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    digest_path.write_text(hashlib.sha256(data).hexdigest() + "\n")
    return data


# ---- sample validation ----

def aligned_lists(questions, references) -> bool:
    return isinstance(questions, list) and bool(questions) and isinstance(references, list) and len(questions) == len(references)


def check_structure(sample, label: str) -> None:
    if not isinstance(sample, dict):
        raise ValueError(f"{label} is not an object")
    if not aligned_lists(sample.get("questions"), sample.get("reference")):
        raise ValueError(f"{label}: questions and references must be nonempty aligned lists")
    if not isinstance(sample.get("country"), str):
        raise ValueError(f"{label}: missing country")


def check_question(question, label: str) -> str:
    """Return the selector of a well-formed ``selector;question`` string."""
    if not isinstance(question, str) or ";" not in question:
        raise ValueError(f"{label}: invalid question/selector")
    selector, text = question.split(";", 1)
    if not selector.strip() or not text.strip():
        raise ValueError(f"{label}: empty selector/question")
    return selector.strip()


def valid_sequence_key(sample: dict, selector: str) -> bool:
    key = selector[1:-1]
    return selector.endswith("]") and isinstance(sample.get(key), list) and bool(sample[key])


def check_selector(sample: dict, selector: str, label: str) -> None:
    if not selector.startswith("["):
        return
    if not valid_sequence_key(sample, selector):
        raise ValueError(f"{label}: invalid sequence selector")
    if not isinstance(sample.get("sequence"), str) or not sample["sequence"]:
        raise ValueError(f"{label}: missing sequence folder")


def validate_sample(sample: dict, task: str, index: int) -> None:
    label = f"{task} sample {index}"
    check_structure(sample, label)
    for question in sample["questions"]:
        check_selector(sample, check_question(question, label), label)


def load_task(task: str, revision: str = DEFAULT_REVISION, *, cache_dir: Path | None = None) -> list[dict]:
    data = json.loads(annotation_bytes(task, revision, cache_dir))
    if not isinstance(data, list) or not data:
        raise ValueError(f"{task}: annotations must be a nonempty list")
    for index, sample in enumerate(data):
        validate_sample(sample, task, index)
    return data


def annotation_sha256(task: str, revision: str = DEFAULT_REVISION) -> str:
    return hashlib.sha256(annotation_bytes(task, revision)).hexdigest()


def image_urls(sample: dict, question: str, task: str, revision: str = DEFAULT_REVISION) -> list[str]:
    info = task_info(task, revision)
    folder = f"{info['category']}/{info['group']}/{task}"
    selector = question.split(";", 1)[0].strip()
    if selector.startswith("[") and selector.endswith("]"):
        paths = [f"{folder}/{sample['sequence']}/{frame}" for frame in sample[selector[1:-1]]]
    else:
        paths = [f"{folder}/{selector}"]
    return [remote_url(path, revision) for path in paths]
