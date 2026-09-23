"""results/models.json: how each model is labelled, grouped, coloured, and how its boxes are read.

The protocol file declares how requests are sent, and its hash identifies the condition. Everything about presenting
and interpreting a model's answers lives here instead, so adding a model means one protocol entry and one registry entry.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Literal, cast

from . import paths

BoxConvention = Literal["pixels", "grid", "grid_yx"]
BOX_CONVENTIONS: tuple[BoxConvention, ...] = ("pixels", "grid", "grid_yx")
REQUIRED = {"label", "lab", "parameters", "size_rank", "featured", "box_convention", "color"}
OPTIONAL = {"not_featured_reason"}
COLOR = re.compile(r"^#[0-9a-f]{6}$")


@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str
    lab: str
    parameters: str
    size_rank: int
    featured: bool
    box_convention: BoxConvention
    color: str
    not_featured_reason: str | None = None


def model_info(model_id: str, entry: dict) -> ModelInfo:
    keys = set(entry)
    if missing := REQUIRED - keys:
        raise ValueError(f"{model_id}: registry entry is missing {sorted(missing)}")
    if unknown := keys - REQUIRED - OPTIONAL:
        raise ValueError(f"{model_id}: registry entry has unknown keys {sorted(unknown)}")
    if entry["box_convention"] not in BOX_CONVENTIONS:
        raise ValueError(f"{model_id}: box_convention must be one of {BOX_CONVENTIONS}, not {entry['box_convention']!r}")
    if not COLOR.match(entry["color"]):
        raise ValueError(f"{model_id}: color must be a lowercase #rrggbb hex, not {entry['color']!r}")
    if not isinstance(entry["size_rank"], int) or not isinstance(entry["featured"], bool):
        raise ValueError(f"{model_id}: size_rank must be an int and featured a bool")
    if not entry["featured"] and not entry.get("not_featured_reason"):
        raise ValueError(f"{model_id}: a model left out of the headline figures needs a not_featured_reason")
    return ModelInfo(id=model_id, label=entry["label"], lab=entry["lab"], parameters=entry["parameters"], size_rank=entry["size_rank"],
                     featured=entry["featured"], box_convention=cast(BoxConvention, entry["box_convention"]), color=entry["color"],
                     not_featured_reason=entry.get("not_featured_reason"))


def load_registry(path: Path = paths.REGISTRY) -> dict[str, ModelInfo]:
    """Read and validate results/models.json. Unknown keys and missing fields are errors."""
    return {model_id: model_info(model_id, entry) for model_id, entry in json.loads(path.read_text()).items()}


def require_models(registry: dict[str, ModelInfo], model_ids: Iterable[str]) -> None:
    """Fail if any protocol model has no registry entry."""
    if missing := [m for m in model_ids if m not in registry]:
        raise ValueError(f"results/models.json has no entry for {missing}")
