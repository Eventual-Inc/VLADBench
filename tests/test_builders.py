"""The builders behind the published numbers: the box-reading variants and the results record the site reads."""
import importlib.util
import json
from pathlib import Path
import unittest

from vladbench.scoring import load_scorer

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_js(path: Path):
    text = path.read_text()
    return json.loads(text[text.index("=") + 1:].strip().rstrip(";"))


def total(tasks: dict, skip: frozenset = frozenset()) -> float:
    pairs = [(t["score"], t["questions_scored"]) for name, t in tasks.items() if name not in skip]
    return sum(s * n for s, n in pairs) / sum(n for _, n in pairs)


class GridCompositeTests(unittest.TestCase):
    """grid_composite re-marks only box questions, reading each answer on a 0-1000 grid scaled to the frame."""

    @classmethod
    def setUpClass(cls):
        cls.variants = load_script("build_variants")
        cls.box_iou = staticmethod(load_scorer()[0].box_iou)

    def composite(self, answers: list[str], yfirst: bool = False, choice_correct: int = 0, choices: int = 0):
        # One frame of 2000x1000; the gold box covers x 200-600, y 200-400 in pixels.
        gold = [200, 200, 600, 400]
        questions = [{"id": f"b{i}", "kind": "box", "gold": gold, "answers": {"m": [a, 0]}} for i, a in enumerate(answers)]
        questions += [{"id": f"c{i}", "kind": "choice", "gold": "A", "answers": {"m": ["A", int(i < choice_correct)]}} for i in range(choices)]
        model = {"id": "m", "tasks": {"T": {"weights": {"accuracy": 0.5, "other": 0.3, "instruction_following": 0.2},
                                            "components": {"instruction_following": 1.0}}}}
        dims = {q["id"]: (2000, 1000) for q in questions}
        return self.variants.grid_composite(model, "T", {"questions": questions}, dims, yfirst, self.box_iou)

    def test_grid_box_scaled_to_the_frame_is_an_exact_hit(self):
        score, detail = self.composite(["[100, 200, 300, 400]"])
        self.assertAlmostEqual(detail["mean_iou"], 1.0)
        self.assertEqual(detail["box_hits"], 1.0)
        self.assertAlmostEqual(score, 100 * (0.5 * 1 + 0.3 * 1 + 0.2 * 1))

    def test_y_first_answers_are_swapped_before_scaling(self):
        _, detail = self.composite(["[200, 100, 400, 300]"], yfirst=True)
        self.assertAlmostEqual(detail["mean_iou"], 1.0)

    def test_unit_interval_answers_are_read_as_fractions_of_the_grid(self):
        _, detail = self.composite(["[0.1, 0.2, 0.3, 0.4]"])
        self.assertAlmostEqual(detail["mean_iou"], 1.0)

    def test_zero_or_several_boxes_score_nothing(self):
        _, detail = self.composite(["no box here", "[100, 200, 300, 400] or [0, 0, 10, 10]"])
        self.assertEqual(detail["mean_iou"], 0.0)
        self.assertEqual(detail["box_hits"], 0.0)

    def test_choice_questions_keep_their_released_marks(self):
        _, detail = self.composite(["[100, 200, 300, 400]"], choice_correct=1, choices=3)
        self.assertAlmostEqual(detail["accuracy"], (1 + 1) / 4)   # one box hit plus one correct choice, over four questions


class PublishedNumbersTests(unittest.TestCase):
    """Every TOTAL the site shows traces back to the score files."""

    @classmethod
    def setUpClass(cls):
        cls.rerun = json.loads((ROOT / "results/rerun.json").read_text())
        cls.variants = load_js(ROOT / "task-review-variants.js")

    def test_task_scores_match_their_score_files(self):
        for model in self.rerun["models"]:
            scores = json.loads((ROOT / model["source"]).read_text())["tasks"]
            for task, result in model["tasks"].items():
                with self.subTest(model=model["id"], task=task):
                    self.assertAlmostEqual(result["score"], scores[task]["score"], places=9)
                    self.assertEqual(result["questions_scored"], scores[task]["denominators"]["questions_scored"])

    def test_pixel_reading_is_the_leaderboard_total(self):
        for model in self.rerun["models"]:
            with self.subTest(model=model["id"]):
                self.assertAlmostEqual(self.variants["models"][model["id"]]["total"]["pixels"], total(model["tasks"]), places=9)

    def test_no_box_reading_leaves_out_exactly_the_box_tasks(self):
        boxes = frozenset(self.variants["box_tasks"])
        self.assertEqual(len(boxes), 3)
        for model in self.rerun["models"]:
            with self.subTest(model=model["id"]):
                self.assertAlmostEqual(self.variants["models"][model["id"]]["total"]["none"], total(model["tasks"], boxes), places=9)

    def test_pixel_models_are_unchanged_on_their_own_grid(self):
        for model_id, v in self.variants["models"].items():
            if v["convention"] == "pixels":
                with self.subTest(model=model_id):
                    self.assertAlmostEqual(v["total"]["grid"], v["total"]["pixels"], places=9)

    def test_every_scored_model_has_variants(self):
        self.assertEqual(set(self.variants["models"]), {m["id"] for m in self.rerun["models"]})

    def test_task_wins_count_sole_leaders(self):
        builder = load_script("build_review_results")
        models: list[dict] = [{"id": "a", "summary": {}, "tasks": {"T1": {"score": 90}, "T2": {"score": 50}}},
                  {"id": "b", "summary": {}, "tasks": {"T1": {"score": 80}, "T2": {"score": 50}}}]
        tied = builder.task_wins(models, ["T1", "T2"])
        self.assertEqual([m["summary"]["task_wins"] for m in models], [1, 0])
        self.assertEqual(tied, [{"task": "T2", "models": ["a", "b"]}])


if __name__ == "__main__":
    unittest.main()
