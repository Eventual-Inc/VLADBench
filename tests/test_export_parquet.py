"""The parquet tables agree with the score files they were exported from."""
import json
from pathlib import Path
import unittest

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "results/dataset"


@unittest.skipUnless((DATASET / "task_scores.parquet").exists(), "run vladbench build first")
class ExportParquetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rerun = json.loads((ROOT / "results/rerun.json").read_text())
        cls.tables = {name: pq.read_table(DATASET / f"{name}.parquet").to_pylist() for name in ["models", "tasks", "questions", "answers", "task_scores"]}

    def test_row_counts_follow_the_results_record(self):
        models = len(self.rerun["models"])
        self.assertEqual(len(self.tables["models"]), models)
        self.assertEqual(len(self.tables["tasks"]), 28)
        self.assertEqual(len(self.tables["questions"]), 11193)
        self.assertEqual(len(self.tables["answers"]), 11193 * models)
        self.assertEqual(len(self.tables["task_scores"]), 28 * models)

    def test_composite_recomputes_from_components_in_released_order(self):
        for row in self.tables["task_scores"]:
            composite = 100 * row["other"] * row["weight_other"] + 100 * row["accuracy"] * row["weight_accuracy"] + 100 * row["instruction_following"] * row["weight_instruction"]
            self.assertAlmostEqual(composite, row["score"], places=9, msg=f"{row['model_id']} {row['task']}")

    def test_every_answer_joins_a_question_and_a_model(self):
        questions = {q["question_id"] for q in self.tables["questions"]}
        models = {m["model_id"] for m in self.tables["models"]}
        for answer in self.tables["answers"]:
            self.assertIn(answer["question_id"], questions)
            self.assertIn(answer["model_id"], models)
        self.assertEqual(len({(a["model_id"], a["question_id"]) for a in self.tables["answers"]}), len(self.tables["answers"]))

    def test_receipted_spend_matches_the_companion(self):
        by_model = {}
        for answer in self.tables["answers"]:
            if answer["cost_usd"] is not None:
                by_model[answer["model_id"]] = by_model.get(answer["model_id"], 0) + answer["cost_usd"]
        for model in self.tables["models"]:
            if model["cost_basis"].startswith("provider receipts"):
                self.assertAlmostEqual(by_model[model["model_id"]], model["cost_usd"], places=6)


class CardTests(unittest.TestCase):
    def test_dataset_card_lists_every_table_and_model(self):
        from vladbench import paths
        from vladbench.card import check_card, render_card
        from vladbench.export import TABLES
        rerun = json.loads((ROOT / "results/rerun.json").read_text())
        card = render_card(rerun, paths.CARD_TEMPLATE.read_text(), repo="Eventual-Inc/VLADBench-reeval", protocol_sha256="0" * 64)
        check_card(card, rerun)
        for table in TABLES:
            self.assertIn(f"config_name: {table}", card)
        self.assertIn(f"{rerun['dataset']['responses']:,}", card)


if __name__ == "__main__":
    unittest.main()
