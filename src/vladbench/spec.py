"""Load the experiment specification: one file is one condition. Start from ``load_spec``."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .dataset import DEFAULT_REVISION

TRANSPORTS = {"video_mp4", "ordered_image_urls"}
REASONING_PARAMETERS = {"reasoning_effort", "openrouter_reasoning"}
EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}
MODEL_KEYS = {"id", "provider", "endpoint", "model", "reasoning_effort", "reasoning_parameter", "input_transport",
              "single_frame_policy", "oversize_fallback", "video_options", "credential", "backend_reproducibility"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def check_video_policy(m: dict, label: str) -> None:
    if m["input_transport"] == "video_mp4":
        require(m["single_frame_policy"] == "as_is", f"{label}: single_frame_policy")
        require(m["oversize_fallback"] in {"none", "h264_crf18"}, f"{label}: oversize_fallback")
        return
    require(m["single_frame_policy"] == "not_applicable", f"{label}: image transport declares single_frame_policy not_applicable")
    require(m["oversize_fallback"] == "not_applicable", f"{label}: image transport declares oversize_fallback not_applicable")
    require(not m["video_options"], f"{label}: image transport declares no video_options")


def check_model(m: dict) -> None:
    label = m.get("id", "?")
    require(set(m) == MODEL_KEYS, f"{label}: model keys must be exactly {sorted(MODEL_KEYS)}")
    require(m["reasoning_effort"] in EFFORTS, f"{label}: bad reasoning_effort")
    require(m["reasoning_parameter"] in REASONING_PARAMETERS, f"{label}: bad reasoning_parameter")
    require(m["input_transport"] in TRANSPORTS, f"{label}: bad input_transport")
    require(set(m["video_options"]) <= {"content_part", "payload"}, f"{label}: video_options keys")
    require(m["credential"]["type"] == "environment", f"{label}: credential type")
    check_video_policy(m, label)


def check_protocol(protocol: dict) -> None:
    require(protocol["temperature"] is None, "temperature must be null")
    require(protocol["prompt"] == "original", "prompt must be original")
    require(protocol["coordinate_convention"] == "native_pixels", "coordinates must be native_pixels")
    require(type(protocol["max_tokens"]) is int and protocol["max_tokens"] > 0, "max_tokens must be a positive integer")


def load_spec(path: Path) -> dict:
    path = Path(path)
    raw = path.read_bytes()
    spec = json.loads(raw)
    require(spec["schema_version"] == 2, "schema_version must be 2")
    require(spec["dataset_revision"] == DEFAULT_REVISION, "dataset_revision must be the pinned revision")
    require(spec["tasks"] == "all", "tasks must be 'all'")
    check_protocol(spec["protocol"])
    ids = [m["id"] for m in spec["models"]]
    require(bool(ids) and len(ids) == len(set(ids)), "model ids must be unique and nonempty")
    for m in spec["models"]:
        check_model(m)
    spec["sha256"] = hashlib.sha256(raw).hexdigest()
    spec["path"] = str(path.resolve())
    return spec
