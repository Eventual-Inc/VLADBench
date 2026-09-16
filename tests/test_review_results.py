import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ReviewResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads(
            (ROOT / "results/rerun.json").read_text()
        )

    def test_complete_three_model_coverage(self):
        self.assertEqual(self.result["dataset"]["tasks"], 28)
        self.assertEqual(self.result["dataset"]["questions_per_model"], 11193)
        self.assertEqual(self.result["dataset"]["responses"], 11193 * len(self.result["models"]))
        self.assertGreaterEqual(len(self.result["models"]), 3)

        expected_tasks = set(self.result["task_order"])
        for model in self.result["models"]:
            self.assertTrue(model["dataset_complete"])
            self.assertEqual(model["responses"], 11193)
            self.assertEqual(set(model["tasks"]), expected_tasks)
            self.assertTrue(
                all(task["dataset_complete"] for task in model["tasks"].values())
            )

    def test_summaries_track_their_score_files(self):
        for model in self.result["models"]:
            scores = json.loads((ROOT / model["source"]).read_text())["tasks"]
            values = [scores[task]["score"] for task in self.result["task_order"]]
            self.assertAlmostEqual(model["summary"]["unweighted_mean_task_score"], sum(values) / len(values))
            self.assertIsNotNone(model["usage"]["cost_usd"], f"{model['id']} has no billed cost")

    def test_browser_asset_matches_json_record(self):
        javascript = (ROOT / "task-review-results.js").read_text()
        prefix = "window.FULL_RESULTS = "
        self.assertTrue(javascript.startswith(prefix))
        self.assertTrue(javascript.endswith(";\n"))
        browser_result = json.loads(javascript[len(prefix) : -2])
        self.assertEqual(browser_result, self.result)


if __name__ == "__main__":
    unittest.main()
