"""Offline scorer regression fixtures; no model calls or image downloads."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest

from vladbench.scoring import ROOT, score_task, scorer_metadata


FIXTURE = json.loads((ROOT / "tests/fixtures/scoring_samples.json").read_text())
FIXTURES = FIXTURE["fixtures"]


def prepared(fixture, answers=None):
    sample = fixture["sample"]
    task = fixture["task"]
    requests = [
        {
            "id": f"{task}:{sample['id']}:{index}", "task": task,
            "sample_id": sample["id"], "question_index": index,
            "sample": copy.deepcopy(sample),
            "task_total_samples": fixture.get("task_total_samples", 1),
            "task_total_questions": fixture.get("task_total_questions", len(sample["questions"])),
        }
        for index in range(len(sample["questions"]))
    ]
    responses = {request["id"]: answer for request, answer in zip(requests, answers if answers is not None else fixture["answers"])}
    return requests, responses


def synthetic(task, references, questions=None, answers=None, sample_id="synthetic"):
    questions = questions or ["image.jpg; Choose ['yes', 'no', 'car', 'true', 'false']." for _ in references]
    return {
        "task": task, "sample": {"id": sample_id, "image_path": "image.jpg", "questions": questions, "reference": references},
        "answers": answers if answers is not None else [str(value) for value in references],
    }


def preserved_module():
    """Independent baseline: execute preserved bytes after the disclosed repair."""
    source = (ROOT / "original/evaluate_utils.py").read_text()
    old = "if ''.join(clean_pred.split(';') in ques_nopath:"
    if source.count(old) != 1:
        raise AssertionError("Baseline source repair changed")
    source = source.replace(old, "if ''.join(clean_pred.split(';')) in ques_nopath:")
    module = types.ModuleType("direct_preserved_baseline")
    exec(compile(source, "baseline", "exec"), module.__dict__)
    return module


class ScoringFixturesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = preserved_module()

    def test_all_28_task_fixtures_match_preserved_scorer(self):
        self.assertEqual({fixture["task"] for fixture in FIXTURES}, set(self.baseline.func_mapping))
        self.assertEqual(len({fixture["family"] for fixture in FIXTURES}), 6)
        for fixture in FIXTURES:
            if True:
                for correct in (True, False):
                    with self.subTest(task=fixture["task"], exact_reference=correct):
                        answers = fixture["answers"] if correct else ["unparseable answer" for _ in fixture["answers"]]
                        requests, responses = prepared(fixture, answers)
                        actual = score_task(fixture["task"], requests, responses)
                        sample = copy.deepcopy(fixture["sample"])
                        sample["prediction"] = answers
                        expected = self.baseline.func_mapping[fixture["task"]]([sample], "native_pixels")
                        self.assertEqual(actual["status"], "complete", actual["exclusions"])
                        self.assertTrue(actual["complete"])
                        self.assertFalse(actual["dataset_complete"])
                        self.assertEqual(actual["denominators"]["questions_scored"], expected[0])
                        for name, value in zip(("accuracy", "instruction_following", "other"), expected[1:]):
                            self.assertAlmostEqual(actual["components"][name], value)
                        expected_score = sum(100 * actual["components"][name] * weight for name, weight in actual["weights"].items())
                        self.assertAlmostEqual(actual["score"], expected_score)

    def test_fixture_answers_do_not_mutate_inputs(self):
        fixture = FIXTURES[0]
        requests, responses = prepared(fixture)
        before = copy.deepcopy((requests, responses))
        score_task(fixture["task"], requests, responses)
        self.assertEqual((requests, responses), before)

    def test_sources_are_preserved_and_upstream_repair_is_disclosed(self):
        manifest = json.loads((ROOT / "original/provenance.json").read_text())
        for filename, digest in manifest["files"].items():
            self.assertEqual(hashlib.sha256((ROOT / "original" / filename).read_bytes()).hexdigest(), digest)
        with self.assertRaises(SyntaxError):
            compile((ROOT / "original/evaluate_utils.py").read_text(), "original", "exec")
        metadata = scorer_metadata()
        self.assertEqual(metadata["source_commit"], "b0dde78ab7d4a7c0a9118a2cb519adaef1118f41")
        self.assertEqual(len(metadata["runtime_patches"]), 1)

    def test_missing_response_excludes_entire_sample(self):
        fixture = next(fixture for fixture in FIXTURES if fixture["task"] == "Vehicle_Cutin")
        requests, responses = prepared(fixture)
        missing = requests[-1]["id"]
        del responses[missing]
        result = score_task("Vehicle_Cutin", requests, responses)
        self.assertFalse(result["complete"])
        self.assertIsNone(result["score"])
        self.assertEqual(result["denominators"]["questions_expected"], 3)
        self.assertEqual(result["denominators"]["responses_received"], 2)
        self.assertEqual(result["denominators"]["questions_scored"], 0)
        self.assertEqual(result["missing_request_ids"], [missing])
        self.assertEqual(result["exclusions"][0]["code"], "incomplete_sample")

    def test_one_question_smoke_test_is_not_a_complete_sample(self):
        fixture = next(fixture for fixture in FIXTURES if fixture["task"] == "Vehicle_Cutin")
        requests, responses = prepared(fixture)
        result = score_task("Vehicle_Cutin", requests[:1], {requests[0]["id"]: responses[requests[0]["id"]]})
        self.assertEqual(result["denominators"]["questions_prepared"], 1)
        self.assertEqual(result["denominators"]["questions_expected"], 3)
        self.assertEqual(len(result["missing_questions"]), 2)
        self.assertFalse(result["complete"])
        self.assertIsNone(result["score"])

    def test_partial_subset_score_has_separate_name(self):
        first = synthetic("Weather", ["yes"], sample_id="complete")
        second = synthetic("Weather", ["yes", "no"], sample_id="incomplete")
        requests_a, responses_a = prepared(first)
        requests_b, responses_b = prepared(second)
        del responses_b[requests_b[1]["id"]]
        result = score_task("Weather", requests_a + requests_b, responses_a | responses_b)
        self.assertFalse(result["complete"])
        self.assertIsNone(result["score"])
        self.assertEqual(result["eligible_subset_score"], 100)
        self.assertEqual(result["denominators"]["questions_expected"], 3)
        self.assertEqual(result["denominators"]["questions_scored"], 1)

    def test_invalid_sample_shapes_are_excluded(self):
        fixture = synthetic("Weather", ["yes", "no"])
        for invalid_sample in (None, {}, {"questions": ["image;q"], "reference": []}, {"questions": "bad", "reference": []}, {"questions": ["image;q"], "reference": [None]}):
            with self.subTest(sample=invalid_sample):
                requests, responses = prepared(fixture)
                for request in requests:
                    request["sample"] = invalid_sample
                result = score_task("Weather", requests, responses)
                self.assertFalse(result["complete"])
                self.assertEqual(result["exclusions"][0]["code"], "invalid_sample")

    def test_blank_and_non_string_responses_are_missing(self):
        fixture = synthetic("Weather", ["yes"])
        requests, responses = prepared(fixture)
        for answer in ("", "  \n", None, 42):
            responses[requests[0]["id"]] = answer
            result = score_task("Weather", requests, responses)
            self.assertFalse(result["complete"])
            self.assertEqual(len(result["missing_request_ids"]), 1)

    def test_paired_relation_partial_credit_and_improvement(self):
        fixture = synthetic("Sign_Sign_Relation", ["1/2", "1/2"], answers=["1", "1/2"])
        requests, responses = prepared(fixture)
        result = score_task(fixture["task"], requests, responses)
        self.assertEqual(result["components"]["accuracy"], .75)
        self.assertEqual(result["components"]["other"], 1)
        self.assertEqual(result["denominators"]["comparison_pairs"], 1)
        self.assertEqual(result["score"], 87.5)

    def test_speed_bounds_and_road_change_halves(self):
        speed = synthetic("Lane_Speed_Relation", ["[0,80]", "[0,80]"], answers=["[0,50]", "[0,80]"])
        change = synthetic("Lane_Change_Relation", [True, True], answers=["False", "True"])
        for fixture, accuracy in ((speed, .75), (change, .5)):
            requests, responses = prepared(fixture)
            result = score_task(fixture["task"], requests, responses)
            self.assertEqual(result["components"]["accuracy"], accuracy)
            self.assertEqual(result["components"]["other"], 1)
        invalid = synthetic("Sign_Lane_Relation", ["1"])
        result = score_task(invalid["task"], *prepared(invalid))
        self.assertEqual(result["exclusions"][0]["code"], "invalid_sample")

    def test_upstream_duplicate_relation_credit_is_not_silently_fixed(self):
        fixture = synthetic("Sign_Sign_Relation", ["1", "1"], answers=["1/1/1", "1/1/1"])
        result = score_task(fixture["task"], *prepared(fixture))
        self.assertEqual(result["components"]["accuracy"], 3)
        self.assertGreater(result["score"], 100)

    def test_judge_partition_and_pure_judgment_sample(self):
        mixed = synthetic("Vehicle_Cutin", ["yes", "no", "car"], answers=["yes", "yes", "car"])
        result = score_task(mixed["task"], *prepared(mixed))
        self.assertEqual(result["denominators"]["judgment"], 2)
        self.assertEqual(result["denominators"]["description"], 1)
        self.assertEqual(result["components"]["accuracy"], 1)
        self.assertEqual(result["components"]["other"], .5)
        self.assertEqual(result["score"], 65)
        only_judgment = synthetic("Key_Obsturction_Detection", ["yes"])
        result = score_task(only_judgment["task"], *prepared(only_judgment))
        self.assertEqual(result["score"], 100)
        self.assertEqual(result["denominators"]["description"], 0)

    def test_undefined_metric_components_are_explicit(self):
        for task in ("Vehicle_Recognition", "Spatial_Temporal_Reasoning"):
            fixture = synthetic(task, ["car"])
            result = score_task(task, *prepared(fixture))
            self.assertIsNone(result["score"])
            self.assertFalse(result["complete"])
            self.assertEqual(result["exclusions"][0]["code"], "undefined_component")

    def test_grounding_without_box_sample_can_join_box_sample(self):
        fixture = next(fixture for fixture in FIXTURES if fixture["task"] == "Vehicle_Recognition")
        no_box = synthetic("Vehicle_Recognition", ["car"], sample_id="no_box")
        req_a, res_a = prepared(fixture)
        req_b, res_b = prepared(no_box)
        result = score_task("Vehicle_Recognition", req_a + req_b, res_a | res_b)
        self.assertTrue(result["complete"])
        self.assertEqual(result["denominators"]["samples_scored"], 2)

    def test_grounding_model_transform_is_explicit(self):
        fixture = synthetic("VRU_Recognition", [[100, 100, 200, 200]], questions=["image;Where is the car located in the image?"], answers=["[50, 50, 100, 100]"])
        fixture["sample"]["dimension"] = [2000, 2000]
        requests, responses = prepared(fixture)
        normalized = score_task(fixture["task"], requests, responses, scorer_model="qwen")
        native = score_task(fixture["task"], requests, responses)
        self.assertEqual(normalized["components"]["other"], 1)
        self.assertLess(native["components"]["other"], .5)
        self.assertEqual(native["scorer"]["model_argument"], "native_pixels")
        for request in requests:
            del request["sample"]["dimension"]
        result = score_task(fixture["task"], requests, responses, scorer_model="qwen")
        self.assertEqual(result["exclusions"][0]["code"], "invalid_sample")

    def test_malformed_model_response_is_reported_as_scorer_failure(self):
        fixture = synthetic("VRU_Recognition", [[10, 10, 20, 20]], questions=["image;Where is the car located in the image?"], answers=["[1.2.3, 2, 3, 4]"])
        result = score_task(fixture["task"], *prepared(fixture))
        self.assertIsNone(result["score"])
        self.assertEqual(result["exclusions"][0]["code"], "scorer_error")

    def test_trajectory_and_unknown_task_are_explicitly_unsupported(self):
        for task in ("Trajectory", "invented"):
            result = score_task(task, [], {})
            self.assertEqual(result["status"], "unsupported")
            self.assertFalse(result["complete"])
            self.assertEqual(result["exclusions"][0]["code"], "unsupported_task")

    def test_released_scorer_contract_is_checked(self):
        from vladbench.scoring import run_original, verified_bytes
        eligible = [{"questions": ["a;b", "c;d"]}]
        with self.assertRaisesRegex(ValueError, "denominator"):
            run_original(lambda samples, MODEL: (1, 1.0, 1.0, 0.0), eligible, "native_pixels")
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            run_original(lambda samples, MODEL: (2, float("nan"), 1.0, 0.0), eligible, "native_pixels")
        self.assertEqual(run_original(lambda samples, MODEL: (2, 0.5, 1, 0), eligible, "native_pixels"), (2, 0.5, 1.0, 0.0))
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            verified_bytes("evaluate_utils.py", {"files": {"evaluate_utils.py": "0" * 64}})

    def test_grounding_reference_checks(self):
        from vladbench.scoring import grounding_error
        located = "img.png; Where is the car located in the image?"
        sample = {"dimension": [1920, 1080]}
        self.assertIsNone(grounding_error("img.png; What color?", "red", sample, "native_pixels"))
        self.assertIn("four finite numbers", grounding_error(located, [1, 2, 3], sample, "native_pixels"))
        self.assertIn("reversed", grounding_error(located, [10, 10, 5, 20], sample, "native_pixels"))
        self.assertIsNone(grounding_error(located, [1, 2, 3, 4], sample, "native_pixels"))
        self.assertIsNone(grounding_error(located, [1, 2, 3, 4], sample, "Qwen"))
        self.assertIn("dimension", grounding_error(located, [1, 2, 3, 4], {}, "Qwen"))

    def test_dataset_completeness_requires_matching_full_counts(self):
        fixture = synthetic("Weather", ["yes"])
        requests, responses = prepared(fixture)
        self.assertTrue(score_task("Weather", requests, responses)["dataset_complete"])
        requests[0]["task_total_questions"] = 2
        self.assertFalse(score_task("Weather", requests, responses)["dataset_complete"])
        del requests[0]["task_total_questions"]
        self.assertFalse(score_task("Weather", requests, responses)["dataset_complete"])


if __name__ == "__main__":
    unittest.main()
