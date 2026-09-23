"""TOTAL, group means, task wins, and the frontier."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

from vladbench.aggregate import Point, TaskScore, Tie, frontier, group_means, task_wins, total

ROOT = Path(__file__).resolve().parents[1]


def load_js(path: Path):
    text = path.read_text()
    return json.loads(text[text.index("=") + 1:].strip().rstrip(";"))


class TotalTests(unittest.TestCase):
    TASKS: dict[str, TaskScore] = {"A": {"score": 90.0, "questions_scored": 300}, "B": {"score": 50.0, "questions_scored": 100}}

    def test_weights_by_question_count(self):
        self.assertAlmostEqual(total(self.TASKS), (90 * 300 + 50 * 100) / 400)

    def test_skip_and_override(self):
        self.assertAlmostEqual(total(self.TASKS, skip={"A"}), 50)
        self.assertAlmostEqual(total(self.TASKS, override={"B": 90.0}), 90)

    def test_no_tasks_is_an_error(self):
        with self.assertRaises(ValueError):
            total(self.TASKS, skip={"A", "B"})

    def test_reproduces_241_of_the_papers_250_group_averages(self):
        published = load_js(ROOT / "task-review-published.js")
        record = json.loads((ROOT / "results/rerun.json").read_text())
        counts = {t: r["questions_scored"] for t, r in record["models"][0]["tasks"].items()}
        within = checked = 0
        for column in published["models"]:
            group: list[str] = []
            for row in published["rows"]:
                if not row["aggregate"]:
                    group.append(row["task"])
                    continue
                if row["source_label"] == "MEAN":
                    tasks = {t: TaskScore(score=next(r for r in published["rows"] if r["task"] == t)["scores"][column["id"]], questions_scored=counts[t]) for t in group}
                    within += abs(group_means(tasks, {"g": group})["g"] - row["scores"][column["id"]]) <= 0.1
                    checked += 1
                group = [] if row["source_label"] == "MEAN" else group
        self.assertEqual((within, checked), (241, 250))

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_site_total_matches(self):
        """modelMean in web/results.js, run in node on the published record, agrees with aggregate.total."""
        source = (ROOT / "web/results.js").read_text()
        found = [re.search(rf"^function {name}\(.*?^}}", source, re.S | re.M) for name in ("composite", "modelMean")]
        assert all(found), "web/results.js no longer defines composite and modelMean"
        functions = "\n".join(m.group(0) for m in found if m)
        script = (f"const state = {{weights: null}};\nconst TASKS = {json.dumps(load_js(ROOT / 'task-review-tasks.js'))};\n{functions}\n"
                  f"const models = {json.dumps(json.loads((ROOT / 'results/rerun.json').read_text())['models'])};\n"
                  "console.log(JSON.stringify(Object.fromEntries(models.map((m) => [m.id, modelMean(m)]))));")
        site = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
        for model in json.loads((ROOT / "results/rerun.json").read_text())["models"]:
            with self.subTest(model=model["id"]):
                self.assertAlmostEqual(site[model["id"]], total(model["tasks"]), places=9)


class WinsAndFrontierTests(unittest.TestCase):
    def test_task_wins_count_sole_leaders_and_report_ties(self):
        wins, ties = task_wins({"a": {"T1": 90, "T2": 50}, "b": {"T1": 80, "T2": 50}}, ["T1", "T2"])
        self.assertEqual(wins, {"a": 1, "b": 0})
        self.assertEqual(ties, [Tie("T2", ("a", "b"))])

    def test_frontier_keeps_models_no_cheaper_model_beats(self):
        points = [Point("cheap", 1, 60), Point("dominated", 5, 55), Point("mid", 10, 70), Point("top", 100, 80), Point("pricier_same", 200, 80)]
        self.assertEqual([p.model_id for p in frontier(points)], ["cheap", "mid", "top", "pricier_same"])


if __name__ == "__main__":
    unittest.main()
