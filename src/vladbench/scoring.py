"""Score recorded answers with the released scorer, preserved byte for byte.

Start from ``score_model`` (one model, one condition) and ``score_task``.

The only change to the released source is a disclosed syntax-only repair made
in memory at load time. See original/PROVENANCE.md. Requests come from
``vladbench.requests.questions`` and answers are hash-verified before they get
here, so this module validates annotations and completeness, not request shape.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import re
import time
import types
from pathlib import Path
from collections.abc import Sequence
from typing import Any

from .requests import build, questions, tasks
from .run import RUNS, read_jsonl

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "original"
SCORER_FILE = "evaluate_utils.py"
PAIRED_FAMILIES = {"Relation_criterion_QA", "RoadChange_criterion_QA", "RoadSpeed_criterion_QA"}
GROUNDING, JUDGE = "Grounding_criterion_QA", "Judge_criterion_QA"
OTHER_NAMES = {GROUNDING: "mean_iou", JUDGE: "judgment_accuracy", **{f: "paired_improvement" for f in PAIRED_FAMILIES}}
REQUIRED_DOMAIN = {GROUNDING: "bounding_box", JUDGE: "judgment"}
NORMALIZED_GROUNDING_MODELS = ("qwen", "internvl", "gemini", "drivemm", "ivl")
SCORER_ERRORS = (ValueError, TypeError, ZeroDivisionError, IndexError, AttributeError, OverflowError)


# ---- the released scorer -------------------------------------------------------

def verified_bytes(filename: str, provenance: dict) -> bytes:
    data = (ORIGINAL / filename).read_bytes()
    if hashlib.sha256(data).hexdigest() != provenance["files"][filename]:
        raise ValueError(f"Preserved scorer provenance mismatch: {filename}")
    return data


def scorer_metadata() -> dict:
    """Immutable source identity of the released scorer, including the runtime repair."""
    provenance = json.loads((ORIGINAL / "provenance.json").read_text())
    verified_bytes(SCORER_FILE, provenance)
    return {
        "variant": "upstream", "source_repository": provenance["source_repository"],
        "source_commit": provenance["source_commit"], "source_file": f"original/{SCORER_FILE}",
        "sha256": provenance["files"][SCORER_FILE], "runtime_patches": provenance["runtime_patches"]["upstream"],
        "wrapper_version": 1,
    }


def original_weights(provenance: dict) -> dict:
    """Read the ``weights`` literal from evaluate_vlm.py without executing the script."""
    tree = ast.parse(verified_bytes("evaluate_vlm.py", provenance))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "weights" for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("evaluate_vlm.py no longer defines weights")


def load_scorer() -> tuple[types.ModuleType, dict, dict]:
    metadata = scorer_metadata()
    provenance = json.loads((ORIGINAL / "provenance.json").read_text())
    source = verified_bytes(SCORER_FILE, provenance).decode("utf-8")
    for patch in metadata["runtime_patches"]:
        if source.count(patch["old"]) != 1:
            raise ValueError("Upstream syntax repair no longer matches exactly once")
        source = source.replace(patch["old"], patch["new"])
    module = types.ModuleType("vladbench_preserved_scorer")
    exec(compile(source, metadata["source_file"], "exec"), module.__dict__)
    metadata["weights_sha256"] = provenance["files"]["evaluate_vlm.py"]
    return module, original_weights(provenance), metadata


# ---- annotation validation ----------------------------------------------------------

def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def question_text(question: str) -> str:
    # This intentionally reproduces upstream's removal of every semicolon.
    return "".join(question.lower().split(";")[1:])


def sample_questions(sample: Any) -> list:
    questions = sample.get("questions") if isinstance(sample, dict) else None
    return questions if isinstance(questions, list) else []


def validquestion_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(q, str) and ";" in q for q in value)


def structure_errors(sample: Any) -> list[str]:
    if not isinstance(sample, dict):
        return ["sample must contain the full annotation object"]
    if not validquestion_list(sample.get("questions")):
        return ["questions must be a nonempty list of original selector;question strings"]
    references = sample.get("reference")
    if not isinstance(references, list) or len(references) != len(sample["questions"]):
        return ["question/reference length mismatch"]
    return []


def positive_pair(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 2 and all(is_number(n) and n > 0 for n in value)


def dimension_error(sample: dict) -> str | None:
    return None if positive_pair(sample.get("dimension")) else "normalized grounding requires positive width/height dimension"


def is_box(reference: Any) -> bool:
    return isinstance(reference, list) and len(reference) == 4 and all(is_number(n) for n in reference)


def box_error(reference: Any) -> str | None:
    if not is_box(reference):
        return "bounding box reference must contain four finite numbers"
    if reference[2] < reference[0] or reference[3] < reference[1]:
        return "bounding box reference has reversed coordinates"
    return None


def grounding_error(question: str, reference: Any, sample: dict, model: str) -> str | None:
    if "located in the image?" not in question_text(question):
        return None
    error = box_error(reference)
    if error:
        return error
    if any(name in model.lower() for name in NORMALIZED_GROUNDING_MODELS):
        return dimension_error(sample)
    return None


def relation_error(question: str, reference: Any, sample: dict, model: str) -> str | None:
    ok = isinstance(reference, str) and re.fullmatch(r"-?\d+(?:/-?\d+)*", reference)
    return None if ok else "relation reference must be slash-separated integer IDs"


def speed_error(question: str, reference: Any, sample: dict, model: str) -> str | None:
    ok = isinstance(reference, str) and re.search(r"\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]", reference)
    return None if ok else "speed reference must contain an integer [low, high] pair"


def plain_error(question: str, reference: Any, sample: dict, model: str) -> str | None:
    if isinstance(reference, str):
        return None if reference else "reference must be a nonempty string or finite number"
    # bool is an int here on purpose: the released annotations use True/False references.
    finite = isinstance(reference, (int, float)) and math.isfinite(reference)
    return None if finite else "reference must be a nonempty string or finite number"


REFERENCE_CHECK = {GROUNDING: grounding_error, "Relation_criterion_QA": relation_error, "RoadSpeed_criterion_QA": speed_error}


def parity_errors(sample: dict, family: str) -> list[str]:
    if family in PAIRED_FAMILIES and len(sample["questions"]) % 2:
        return ["paired scorer requires equal first and second question halves"]
    return []


def validate_sample(sample: Any, family: str, model: str) -> list[str]:
    errors = structure_errors(sample)
    if errors:
        return errors
    errors = parity_errors(sample, family)
    check = REFERENCE_CHECK.get(family, plain_error)
    for index, (question, reference) in enumerate(zip(sample["questions"], sample["reference"], strict=True)):
        error = check(question, reference, sample, model)
        if error:
            errors.append(f"question {index}: {error}")
    return errors


# ---- completeness ----------------------------------------------------------------------

def blank(answer: Any) -> bool:
    return not isinstance(answer, str) or not answer.strip()


def answers_by_index(result: dict, group: list[dict], responses: dict) -> dict[int, str]:
    """Answered question indexes for one sample; records what is missing."""
    answers: dict[int, str] = {}
    for request in group:
        answer = responses.get(request["id"])
        if not isinstance(answer, str) or blank(answer):
            result["missing_request_ids"].append(request["id"])
            continue
        answers[request["question_index"]] = answer
        result["denominators"]["responses_received"] += 1
    return answers


def group_by_sample(requests: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for request in requests:
        groups.setdefault(str(request["sample_id"]), []).append(request)
    return groups


def exclusion(sample_id: str, errors: list[str], missing: list[int], questions: list) -> dict:
    return {
        "sample_id": sample_id, "code": "invalid_sample" if errors else "incomplete_sample",
        "reason": "; ".join(dict.fromkeys(errors)) if errors else "Every question in the original sample must have a recorded response",
        "missing_question_indices": missing, "questions_excluded": len(questions),
    }


def missing_indexes(result: dict, sample_id: str, question_count: int, answers: dict) -> list[int]:
    missing = [i for i in range(question_count) if i not in answers]
    result["missing_questions"].extend({"sample_id": sample_id, "question_index": i, "reason": "missing_response"} for i in missing)
    return missing


def adapt(result: dict, sample_id: str, group: list[dict], responses: dict, family: str, model: str) -> dict | None:
    """The sample with predictions attached, or None after recording why it is excluded."""
    sample = group[0]["sample"]
    question_list = sample_questions(sample)
    result["denominators"]["questions_expected"] += len(question_list)
    errors = validate_sample(sample, family, model)
    answers = answers_by_index(result, group, responses)
    missing = missing_indexes(result, sample_id, len(question_list), answers)
    if errors or missing:
        result["exclusions"].append(exclusion(sample_id, errors, missing, question_list))
        return None
    adapted = copy.deepcopy(sample)
    adapted["prediction"] = [answers[i] for i in range(len(question_list))]
    return adapted


def eligible_samples(result: dict, requests: list[dict], responses: dict, family: str, model: str) -> tuple[list[dict], list[str]]:
    """Complete, valid samples with predictions attached; everything else becomes an exclusion."""
    eligible, ids = [], []
    for sample_id, group in group_by_sample(requests).items():
        adapted = adapt(result, sample_id, group, responses, family, model)
        if adapted is not None:
            eligible.append(adapted)
            ids.append(sample_id)
    result["denominators"]["samples_total"] = len(result["exclusions"]) + len(eligible)
    return eligible, ids


# ---- metric domains ------------------------------------------------------------------------

def count_grounding(sample: dict, module, denominators: dict) -> None:
    for question in sample["questions"]:
        if "located in the image?" in question_text(question):
            denominators["bounding_box"] += 1


def count_judge(sample: dict, module, denominators: dict) -> None:
    for reference in sample["reference"]:
        normalized = module.clean_string(module.convert_if_number(reference)).lower()
        denominators["judgment" if normalized in ("yes", "no") else "description"] += 1


def count_paired(sample: dict, module, denominators: dict) -> None:
    denominators["comparison_pairs"] += len(sample["questions"]) // 2


DOMAIN_COUNTER = {GROUNDING: count_grounding, JUDGE: count_judge, **{f: count_paired for f in PAIRED_FAMILIES}}


def count_domains(result: dict, module, family: str, eligible: list) -> None:
    counter = DOMAIN_COUNTER.get(family)
    if counter is None:
        return
    for sample in eligible:
        counter(sample, module, result["denominators"])


def undefined_domain(result: dict, family: str, eligible: list) -> str | None:
    """The metric domain upstream needs at least one question from, if this subset has none."""
    domain = REQUIRED_DOMAIN.get(family)
    if eligible and domain and result["denominators"][domain] == 0:
        return domain
    return None


# ---- the scorer call --------------------------------------------------------------------

def run_original(fn, eligible: list[dict], model: str) -> tuple:
    count, accuracy, instruction, other = fn(copy.deepcopy(eligible), MODEL=model)
    if count != sum(len(sample["questions"]) for sample in eligible):
        raise ValueError("upstream scorer denominator does not match eligible question count")
    if not all(math.isfinite(float(value)) for value in (accuracy, instruction, other)):
        raise ValueError("upstream scorer returned a nonfinite component")
    return count, float(accuracy), float(instruction), float(other)


def components(values: tuple, family: str) -> dict:
    _, accuracy, instruction, other = values
    return {"accuracy": accuracy, "instruction_following": instruction, "other": other,
            "other_name": OTHER_NAMES.get(family, "unused"),
            "accuracy_name": "description_accuracy" if family == JUDGE else "accuracy"}


def counts_match(result: dict) -> bool:
    denominators, totals = result["denominators"], result["dataset_totals"]
    return totals["samples"] == denominators["samples_scored"] and totals["questions"] == denominators["questions_scored"]


def completion(result: dict) -> None:
    result["complete"] = not result["exclusions"] and not result["missing_questions"]
    result["score"] = result["eligible_subset_score"] if result["complete"] else None
    result["dataset_complete"] = bool(result["complete"] and counts_match(result))
    result["status"] = "complete" if result["complete"] else "partial"


def finish(result: dict, values: tuple, family: str, weight: list, eligible: list) -> dict:
    count, accuracy, instruction, other = values
    result["denominators"]["questions_scored"] = int(count)
    result["denominators"]["samples_scored"] = len(eligible)
    result["components"] = components(values, family)
    # Same operation order as the released evaluate_vlm.py so published values reproduce bit for bit.
    result["eligible_subset_score"] = 100 * other * weight[0] + 100 * accuracy * weight[1] + 100 * instruction * weight[2]
    completion(result)
    return result


def score_eligible(result: dict, fn, eligible: list, ids: list, model: str, family: str, weight: list) -> dict:
    try:
        values = run_original(fn, eligible, model)
    except SCORER_ERRORS as error:
        return exclude(result, {"code": "scorer_error", "reason": f"{type(error).__name__}: {error}", "sample_ids": ids})
    return finish(result, values, family, weight, eligible)


# ---- orchestration ------------------------------------------------------------------------

def empty_result(task: str, requests: list[dict], family: str | None, weight: list, metadata: dict, model: str) -> dict:
    first = requests[0] if requests else {}
    return {
        "task": task, "scope": "selected_samples",
        "scorer": {**metadata, "function": family, "model_argument": model},
        "status": "unscorable", "complete": False, "dataset_complete": False,
        "score": None, "eligible_subset_score": None, "components": None,
        "dataset_totals": {"samples": first.get("task_total_samples"), "questions": first.get("task_total_questions")},
        "weights": dict(zip(("other", "accuracy", "instruction_following"), weight, strict=True)),
        "denominators": {"samples_total": 0, "samples_scored": 0, "questions_expected": 0, "questions_prepared": len(requests),
                         "responses_received": 0, "questions_scored": 0, "judgment": 0, "description": 0,
                         "bounding_box": 0, "comparison_pairs": 0},
        "missing_request_ids": [], "missing_questions": [], "exclusions": [],
    }


def exclude(result: dict, exclusion: dict) -> dict:
    result["exclusions"].append(exclusion)
    return result


def unsupported(result: dict, task: str) -> dict:
    reason = ("Trajectory is catalogued but has no upstream scorer and is skipped by evaluate_vlm.py" if task == "Trajectory"
              else "Task has no registered upstream scorer")
    result["status"] = "unsupported"
    return exclude(result, {"reason": reason, "code": "unsupported_task"})


def score_task(task: str, requests: list[dict], responses: dict[str, str], *, scorer_model: str = "native_pixels") -> dict:
    """Score one task over its complete samples; incomplete or invalid samples are excluded as a unit.

    ``scorer_model`` drives the released scorer's model-name grounding transform;
    the default keeps pixel coordinates.
    """
    module, weights, metadata = load_scorer()
    fn = module.func_mapping.get(task)
    family = getattr(fn, "__name__", None)
    weight = weights.get(task, [0, .8, .2])
    result = empty_result(task, requests, family, weight, metadata, scorer_model)
    if fn is None or family is None:
        return unsupported(result, task)
    if not requests:
        return exclude(result, {"reason": "No prepared requests for task", "code": "no_requests"})
    eligible, ids = eligible_samples(result, requests, responses, family, scorer_model)
    count_domains(result, module, family, eligible)
    domain = undefined_domain(result, family, eligible)
    if domain:
        return exclude(result, {"code": "undefined_component", "sample_ids": ids,
                                 "reason": f"Upstream {family} requires at least one {domain} question; this selected subset has none"})
    return score_eligible(result, fn, eligible, ids, scorer_model, family, weight) if eligible else result


# ---- one model, one condition -----------------------------------------------------------------

def cut_off(record: dict) -> bool:
    return str(record.get("finish_reason", "")).lower() in {"length", "max_tokens"}


def carried_from(record: dict, old: dict) -> bool:
    return record.get("condition") == old["name"] and not cut_off(record)


def model_entry(spec: dict, model_id: str) -> dict | None:
    for entry in spec["models"]:
        if entry["id"] == model_id:
            return entry
    return None


def carried_hash(record: dict, model: dict, question: dict, superseded: list[dict]) -> str | None:
    """The hash a superseded specification implies, if this record came from one and its cap did not bind."""
    for old in superseded:
        old_model = model_entry(old, model["id"])
        if old_model and carried_from(record, old):
            return build(old, old_model, question)[1]
    return None


def matches(spec: dict, model: dict, record: dict, question: dict, superseded: list[dict]) -> bool:
    live = build(spec, model, question)[1]
    return record["protocol_sha256"] in {live, carried_hash(record, model, question, superseded)}


def verified_answers(spec: dict, model: dict, path: Path, expected: dict, superseded: Sequence[dict] = ()) -> tuple[dict, dict]:
    """Answers whose stored request hash matches the live specification, or a superseded one whose cap did not bind."""
    answers: dict[str, str] = {}
    stats: dict[str, Any] = {"mismatched": [], "truncated": 0, "fallbacks": 0, "carried": 0}
    for record in read_jsonl(path):
        question = expected.get(record["id"])
        if question is None or not matches(spec, model, record, question, list(superseded)):
            stats["mismatched"].append(record["id"])
            continue
        answers[record["id"]] = record["answer"]
        stats["truncated"] += cut_off(record)
        stats["fallbacks"] += bool(record.get("lossy_fallback"))
        stats["carried"] += "condition" in record
    return answers, stats


def model_result(spec: dict, model: dict, folder: Path, scored: dict, totals: dict) -> dict:
    dataset_complete = all(t["dataset_complete"] for t in scored.values())
    return {
        "schema_version": 3, "model_id": model["id"], "model": model["model"], "specification_sha256": spec["sha256"],
        "declared": {k: model[k] for k in ("input_transport", "reasoning_effort", "reasoning_parameter", "single_frame_policy", "oversize_fallback")},
        "protocol": spec["protocol"], "variant": "upstream", "scorer": scorer_metadata(),
        "scope": "all available tasks, recorded original-condition responses", "generated_at": time.time(),
        "tasks": scored, "source": str(folder), "dataset_complete": dataset_complete,
        "request_success": {"completed": totals["completed"], "total": totals["total"]},
        "oversize_fallback_requests": totals["fallbacks"], "truncated_answers": totals["truncated"],
        "carried_from_superseded_condition": totals["carried"],
        "protocol_complete": dataset_complete and totals["truncated"] == 0,
        "protocol_complete_rule": "Every question answered and no answer cut off by the completion guard (finish_reason=length).",
        "aggregation": "Each task scored once over its complete samples; no averaging and no overall headline score.",
    }


def score_model(spec: dict, model: dict, *, runs_dir: Path = RUNS, results_dir: Path = ROOT / "results", superseded: Sequence[dict] = ()) -> dict:
    """Score one model's recorded answers for a condition; every answer's request hash is verified first.

    ``superseded`` lists earlier specifications whose answers may be carried
    over when their completion cap did not bind (see scripts/adopt_capped_answers.py).
    """
    folder = Path(runs_dir) / spec["name"] / model["id"]
    results_dir = Path(results_dir)
    scored, totals = {}, {"completed": 0, "total": 0, "truncated": 0, "fallbacks": 0, "carried": 0}
    for task in tasks(spec["dataset_revision"]):
        expected = {q["id"]: q for q in questions(task, spec["dataset_revision"])}
        answers, stats = verified_answers(spec, model, folder / f"{task}.jsonl", expected, superseded)
        if stats["mismatched"]:
            raise ValueError(f"{model['id']} {task}: {len(stats['mismatched'])} answers do not match the specification's requests, e.g. {stats['mismatched'][:5]}")
        scored[task] = score_task(task, list(expected.values()), answers)
        totals["completed"] += len(answers)
        totals["total"] += len(expected)
        totals["truncated"] += stats["truncated"]
        totals["fallbacks"] += stats["fallbacks"]
        totals["carried"] += stats["carried"]
    result = model_result(spec, model, folder, scored, totals)
    results_dir.mkdir(exist_ok=True)
    (results_dir / f"scores-{model['id']}.json").write_text(json.dumps(result, indent=2) + "\n")
    return result
