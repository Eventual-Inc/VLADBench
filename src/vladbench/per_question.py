"""Per-question marks under the paper's scoring rules.

The released scorer (original/evaluate_utils.py) returns one accuracy, one instruction-following rate, and one third
component per task. This module applies the same logic one question at a time, calling the scorer's own helper
functions, so the marks it produces sum back to the released components exactly. tests/test_per_question.py checks
that against every recorded sweep.

Each mark is a dict:
  accuracy     0..1 credit for the answer (0/1 for most families, fractional for relation and speed questions)
  instruction  1 if the answer was in the requested form, else 0
  other        the family's third component where it is defined per question: IoU for a box question, the judgment
               flag for a yes/no question; None otherwise
  kind         "box", "choice", "judgment", "description", "relation", "speed", or "boolean"
  pair         for the paired families, on the second question of each pair: 1 if the pair counted toward the
               consistency component, else 0; None elsewhere
"""
from __future__ import annotations

import re

from .scoring import GROUNDING, JUDGE, PAIRED_FAMILIES, load_scorer, question_text

BOX_PATTERN = re.compile(r'\[\s*([^\],]*\d+[^\],]*)\s*,\s*([^\],]*\d+[^\],]*)\s*,\s*([^\],]*\d+[^\],]*)\s*,\s*([^\],]*\d+[^\],]*)\s*\]')
SPEED_PATTERN = re.compile(r'\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]')
_MODULE = None


def scorer():
    global _MODULE
    if _MODULE is None:
        _MODULE = load_scorer()[0]
    return _MODULE


def choice_mark(question: str, reference, prediction: str, judge: bool = False) -> dict:
    """The fixed-choice rule shared by the general, lane-change, and judgment families."""
    m = scorer()
    text = question_text(question)
    tips = m.extract_options(text)
    pred = m.remove_symbols(prediction)
    clean = m.clean_string(pred).lower()
    ref = m.convert_if_number(reference)
    ref = m.clean_string(ref).lower() if judge else ref.lower()
    accuracy = instruction = 0
    if len(clean.split("', '")) == 1:
        obeyed = "".join(clean.split(";")) in text if judge else clean in text
        instruction = int(obeyed)
        if clean == ref:
            accuracy = 1
        elif ref in clean and ref in tips:
            tips.remove(ref)
            if not any(tip in clean for tip in tips):
                accuracy = 1
    kind = "judgment" if judge and ref in ("yes", "no") else "description" if judge else "boolean" if ref in ("true", "false") else "choice"
    return {"accuracy": accuracy, "instruction": instruction, "other": accuracy if kind == "judgment" else None, "kind": kind, "pair": None}


def box_mark(reference, prediction: str) -> dict:
    """A grounding question: one box in the answer, IoU above 0.5 with the reference in pixel coordinates."""
    matches = BOX_PATTERN.findall(prediction)
    if len(matches) == 1:
        box = [float(re.sub(r"[^0-9.]", "", part)) for part in matches[0]]
        instruction = 1
    else:
        box, instruction = [0.0, 0.0, 0.0, 0.0], 0
    if sum(box) < 4:
        box = [x * 1000 for x in box]
    iou = scorer().box_iou(box, reference)
    return {"accuracy": int(iou > 0.5), "instruction": instruction, "other": iou, "kind": "box", "pair": None}


def relation_mark(reference: str, prediction: str) -> dict:
    """Which numbered elements a sign or light corresponds to; any wrong number scores zero."""
    if "corresponds to" in prediction:
        match = re.search(r"corresponds to No.([+-]?\d+|[+-]?\d+/\d+)", prediction)
        numbers, instruction = (match.group(1).split("/") if match else []), 0
    elif "corresponding to" in prediction:
        match = re.search(r"corresponding to.*is\s+(-?\d+(?:/\d+)*)", prediction)
        numbers, instruction = (match.group(1).split("/") if match else []), 0
    else:
        found = re.findall(r"(-?\d+(?:/\d+)*)", prediction)
        numbers, instruction = (found[-1].split("/") if found else []), int(bool(found))
    ref = reference.split("/")
    credit = 0 if any(n not in ref for n in numbers) else sum(1 / len(ref) for n in numbers if n in ref)
    return {"accuracy": credit, "instruction": instruction, "other": None, "kind": "relation", "pair": None}


def speed_mark(reference: str, prediction: str) -> dict:
    """Speed limits as [min, max]; half credit per matching bound."""
    matches = SPEED_PATTERN.findall(prediction)
    gold = SPEED_PATTERN.findall(reference)[0]
    credit = instruction = 0
    if len(matches) == 1:
        instruction = 1
        credit = sum(0.5 for a, b in zip(gold, matches[0], strict=False) if a == b)   # the released scorer truncates to the shorter
    return {"accuracy": credit, "instruction": instruction, "other": None, "kind": "speed", "pair": None}


def question_mark(family: str, question: str, reference, prediction: str) -> dict:
    if family == GROUNDING and "located in the image?" in question_text(question):
        return box_mark(reference, prediction)
    if family == "Relation_criterion_QA":
        return relation_mark(reference, prediction)
    if family == "RoadSpeed_criterion_QA":
        return speed_mark(reference, prediction)
    return choice_mark(question, reference, prediction, judge=(family == JUDGE))


def sample_marks(family: str, sample: dict, predictions: list[str]) -> list[dict]:
    """Marks for every question of one annotation sample, with the paired-consistency flag filled in."""
    marks = [question_mark(family, q, r, p) for q, r, p in zip(sample["questions"], sample["reference"], predictions, strict=True)]
    if family in PAIRED_FAMILIES:
        half = len(marks) // 2
        for first, second in zip(marks[:half], marks[half:], strict=False):   # an odd count leaves the last question unpaired
            a, b = second["accuracy"], first["accuracy"]      # the scorer compares the second half against the first
            second["pair"] = int((a == 1 and b == 1) or a > b)
    return marks


def components_from_marks(family: str, marks: list[dict]) -> tuple[float, float, float]:
    """Re-aggregate marks into the scorer's (accuracy, instruction_following, other) for one task."""
    n = len(marks)
    instruction = sum(m["instruction"] for m in marks) / n
    if family == GROUNDING:
        boxes = [m["other"] for m in marks if m["kind"] == "box"]
        return sum(m["accuracy"] for m in marks) / n, instruction, sum(boxes) / len(boxes)
    if family == JUDGE:
        judged = [m for m in marks if m["kind"] == "judgment"]
        described = [m for m in marks if m["kind"] == "description"]
        description = sum(m["accuracy"] for m in described) / len(described) if described else sum(m["accuracy"] for m in described)
        return description, instruction, sum(m["accuracy"] for m in judged) / len(judged)
    if family in PAIRED_FAMILIES:
        return sum(m["accuracy"] for m in marks) / n, instruction, sum(m["pair"] or 0 for m in marks) * 2 / n
    return sum(m["accuracy"] for m in marks) / n, instruction, 0.0
