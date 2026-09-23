"""The record: completeness guard, and every published number traced to the score files."""
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest

from vladbench.aggregate import total
from vladbench.boxes import BOX_TASKS
from vladbench.record import IncompleteRun, require_complete

ROOT = Path(__file__).resolve().parents[1]


def load_js(path: Path):
    text = path.read_text()
    return json.loads(text[text.index("=") + 1:].strip().rstrip(";"))


class CompletenessTests(unittest.TestCase):
    SCORED_AT = datetime(2026, 9, 20, tzinfo=timezone.utc)
    RESULT = {"generated_at": SCORED_AT.timestamp()}

    def records(self, n, when="2026-09-19T00:00:00+00:00"):
        return [{"id": f"q{i}", "timestamp": when} for i in range(n)]

    def test_complete_run_passes(self):
        require_complete("m", self.RESULT, self.records(11193))

    def test_partial_run_is_refused(self):
        with self.assertRaisesRegex(IncompleteRun, "partial"):
            require_complete("m", self.RESULT, self.records(8790))

    def test_answers_newer_than_the_score_file_are_refused(self):
        with self.assertRaisesRegex(IncompleteRun, "rescore"):
            require_complete("m", self.RESULT, self.records(11193, "2026-09-21T00:00:00+00:00"))


class PublishedNumbersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads((ROOT / "results/rerun.json").read_text())
        cls.variants = load_js(ROOT / "task-review-variants.js")

    def test_task_scores_match_their_score_files(self):
        for model in self.record["models"]:
            scores = json.loads((ROOT / model["source"]).read_text())["tasks"]
            for task, result in model["tasks"].items():
                with self.subTest(model=model["id"], task=task):
                    self.assertAlmostEqual(result["score"], scores[task]["score"], places=9)
                    self.assertEqual(result["questions_scored"], scores[task]["denominators"]["questions_scored"])

    def test_variant_totals(self):
        for model in self.record["models"]:
            v = self.variants["models"][model["id"]]
            with self.subTest(model=model["id"]):
                self.assertAlmostEqual(v["total"]["pixels"], total(model["tasks"]), places=9)
                self.assertAlmostEqual(v["total"]["none"], total(model["tasks"], skip=BOX_TASKS), places=9)
                if v["convention"] == "pixels":
                    self.assertAlmostEqual(v["total"]["grid"], v["total"]["pixels"], places=9)

    def test_every_scored_model_has_variants(self):
        self.assertEqual(set(self.variants["models"]), {m["id"] for m in self.record["models"]})


if __name__ == "__main__":
    unittest.main()
